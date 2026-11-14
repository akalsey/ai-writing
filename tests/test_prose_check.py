#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest>=8"]
# ///
"""Tests for the writing-quality PostToolUse hook.

Each test pipes a payload to the hook script the same way Claude Code does and
checks stdout. Silence means the hook filtered the event out.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent / "plugins/writing-quality/hooks"
LAUNCHER = HOOKS / "run.sh"


def run_hook(payload: dict, env: dict | None = None) -> str:
    """Run the hook the way hooks.json does: `sh run.sh`, payload on stdin."""
    result = subprocess.run(
        ["/bin/sh", str(LAUNCHER)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def path_with(tmp_path: Path, **links: str) -> str:
    """A PATH holding only the named executables, symlinked from real ones."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, target in links.items():
        (bin_dir / name).symlink_to(target)
    return str(bin_dir)


def context_of(stdout: str) -> str:
    return json.loads(stdout)["hookSpecificOutput"]["additionalContext"]


def session() -> str:
    return f"test-{uuid.uuid4()}"


@pytest.fixture
def memo(tmp_path: Path) -> Path:
    path = tmp_path / "memo.md"
    path.write_text("A real paragraph of prose. " * 40)
    return path


def bash(command: str, sid: str | None = None) -> dict:
    return {
        "session_id": sid or session(),
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


# --- prose file writes -------------------------------------------------------


def test_prose_write_reminds_with_every_check(memo: Path) -> None:
    out = run_hook({"session_id": session(), "tool_name": "Write", "tool_input": {"file_path": str(memo)}})
    text = context_of(out)
    for skill in ("writing-pipeline", "concise", "cold-reader-docs", "clear-prose", "avoid-ai-writing"):
        assert skill in text


def test_prose_write_reminds_once_per_session(memo: Path) -> None:
    payload = {"session_id": session(), "tool_name": "Edit", "tool_input": {"file_path": str(memo)}}
    assert run_hook(payload)
    assert run_hook(payload) == ""


def test_small_file_is_silent(tmp_path: Path) -> None:
    small = tmp_path / "note.md"
    small.write_text("short")
    assert run_hook({"session_id": session(), "tool_name": "Write", "tool_input": {"file_path": str(small)}}) == ""


def test_source_file_is_silent(tmp_path: Path) -> None:
    src = tmp_path / "main.py"
    src.write_text("x = 1\n" * 200)
    assert run_hook({"session_id": session(), "tool_name": "Write", "tool_input": {"file_path": str(src)}}) == ""


# --- pull request bodies -----------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        'gh pr create --title "Fix retries" --body "$(cat <<EOF\nBody text\nEOF\n)"',
        "gh pr create -t 'Fix' -b 'Body text'",
        "gh pr create --fill --body-file /tmp/pr.md",
        "cd repo && gh pr create -F body.md",
        "cd repo; gh pr create -F body.md",
        'gh pr create --title "Fix; retype | cleanup" --body "Body text"',
        "gh pr create --body=\"Body text\"",
        "gh pr create --title \"Don't retry\" --body-file - <<'EOF'\nIt's a body.\nEOF",
    ],
)
def test_pr_create_with_body_reminds(command: str) -> None:
    text = context_of(run_hook(bash(command)))
    assert "pull request" in text
    assert "concise" in text
    assert "clear-prose" in text
    assert "gh pr edit" in text


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create --fill",  # body comes from commits, not written prose
        "gh pr edit 12 --body-file /tmp/pr.md",  # the fix itself; reminding again would loop
        'git commit -m "Fix retries"',
        "gh pr view 12",
        "ls -la",
        "echo 'gh pr create --body x'",  # mentioned, not run
        "gh pr create --fill && echo --body",  # body flag belongs to another command
    ],
)
def test_other_bash_is_silent(command: str) -> None:
    assert run_hook(bash(command)) == ""


# --- launcher -----------------------------------------------------------------


def test_hooks_json_runs_the_launcher_through_sh() -> None:
    config = json.loads((HOOKS / "hooks.json").read_text())
    commands = {h["command"] for entry in config["hooks"]["PostToolUse"] for h in entry["hooks"]}
    assert commands == {'sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh"'}


def test_launcher_works_with_python3_and_no_uv(memo: Path, tmp_path: Path) -> None:
    env = {"PATH": path_with(tmp_path, python3=sys.executable)}
    out = run_hook({"session_id": session(), "tool_name": "Write", "tool_input": {"file_path": str(memo)}}, env)
    assert "writing-pipeline" in context_of(out)


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_launcher_falls_back_to_uv_without_python3(memo: Path, tmp_path: Path) -> None:
    env = {"PATH": path_with(tmp_path, uv=shutil.which("uv"))}
    out = run_hook({"session_id": session(), "tool_name": "Write", "tool_input": {"file_path": str(memo)}}, env)
    assert "writing-pipeline" in context_of(out)


def test_launcher_skips_a_python3_that_cannot_run(memo: Path, tmp_path: Path) -> None:
    # macOS without the command line tools ships a /usr/bin/python3 stub that
    # exists on PATH but fails when run. The launcher must not pass that on.
    stub = tmp_path / "python3-stub"
    stub.write_text("#!/bin/sh\nexit 1\n")
    stub.chmod(0o755)
    env = {"PATH": path_with(tmp_path, python3=str(stub))}
    out = run_hook({"session_id": session(), "tool_name": "Write", "tool_input": {"file_path": str(memo)}}, env)
    assert out == ""


def test_launcher_is_silent_with_no_interpreter(memo: Path, tmp_path: Path) -> None:
    env = {"PATH": path_with(tmp_path)}
    out = run_hook({"session_id": session(), "tool_name": "Write", "tool_input": {"file_path": str(memo)}}, env)
    assert out == ""


def test_pr_reminder_respects_disable_switch() -> None:
    out = run_hook(bash("gh pr create -b 'Body'"), env={"AI_WRITING_PIPELINE_HOOK": "0"})
    assert out == ""


def test_malformed_bash_payload_is_silent() -> None:
    assert run_hook({"session_id": session(), "tool_name": "Bash", "tool_input": {"command": 7}}) == ""


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
