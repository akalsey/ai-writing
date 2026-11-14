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


# --- document and page tools -----------------------------------------------

PROSE = (
    "The export failed for large accounts because the view built the whole file in memory. "
    "Accounts above ten thousand rows hit the load balancer's timeout and got an error. "
    "The export now streams rows as it reads them, so the first byte arrives quickly. "
    "A fifty-thousand-row export finishes in thirteen seconds instead of timing out. "
    "Nothing changed for small accounts, and scheduled reports still work as before. "
    "One question is still open: the largest export was slower per row than expected. "
    "Someone should check it against the staging database before the release goes out. "
    "The pull request is waiting on review, and it ships with the next deploy once approved. "
)


def docs_update(sid: str, doc: str, node: str, text: str) -> dict:
    """Shaped like the Claude Docs connector's update call."""
    return {
        "session_id": sid,
        "tool_name": "mcp__claude_ai_Claude_Docs__update",
        "tool_input": {
            "container": {"kind": "project", "id": doc},
            "ref": {"object": "node", "id": node},
            "payload": {"ops": [{"op": "replace", "with": {"from": {"content": text}}}]},
        },
    }


def test_document_tool_writing_prose_reminds() -> None:
    text = context_of(run_hook(docs_update(session(), "doc-1", "n1", PROSE)))
    assert "writing-pipeline" in text
    assert "concise" in text


def test_any_connector_write_with_prose_reminds() -> None:
    payload = {
        "session_id": session(),
        "tool_name": "mcp__notion__create_page",
        "tool_input": {"parent": {"page_id": "p1"}, "title": "Status", "body": PROSE},
    }
    assert "writing-pipeline" in context_of(run_hook(payload))


def test_document_tool_reminds_once_per_document() -> None:
    sid = session()
    assert run_hook(docs_update(sid, "doc-1", "n1", PROSE))
    assert run_hook(docs_update(sid, "doc-1", "n2", PROSE)) == ""
    assert run_hook(docs_update(sid, "doc-2", "n1", PROSE))


@pytest.mark.parametrize(
    "tool_input",
    [
        {"container": {"id": "d"}, "payload": {"content": "A short note."}},
        {"container": {"id": "d"}, "payload": {"content": "def f(x):\n    return {x: [1, 2, 3]}\n" * 40}},
        {"container": {"id": "d"}, "payload": {"rows": [{"id": i, "status": "ok"} for i in range(200)]}},
    ],
)
def test_document_tool_without_prose_is_silent(tool_input: dict) -> None:
    payload = {"session_id": session(), "tool_name": "mcp__claude_ai_Claude_Docs__update", "tool_input": tool_input}
    assert run_hook(payload) == ""


def test_read_only_connector_tool_is_silent() -> None:
    payload = {"session_id": session(), "tool_name": "mcp__claude_ai_Slack__slack_search_public", "tool_input": {"query": PROSE}}
    assert run_hook(payload) == ""


def test_artifact_publishing_markdown_reminds(tmp_path: Path) -> None:
    page = tmp_path / "report.md"
    page.write_text(PROSE)
    payload = {"session_id": session(), "tool_name": "Artifact", "tool_input": {"file_path": str(page)}}
    assert "writing-pipeline" in context_of(run_hook(payload))


def test_artifact_publishing_a_prose_page_reminds(tmp_path: Path) -> None:
    page = tmp_path / "report.html"
    page.write_text(f"<html><head><style>p {{color: red}}</style></head><body><h1>Status</h1><p>{PROSE}</p></body></html>")
    payload = {"session_id": session(), "tool_name": "Artifact", "tool_input": {"file_path": str(page)}}
    assert "writing-pipeline" in context_of(run_hook(payload))


def test_artifact_publishing_an_app_is_silent(tmp_path: Path) -> None:
    page = tmp_path / "dashboard.html"
    script = "const data = [1, 2, 3]; function render() { return data.map(x => x * 2); }\n" * 60
    page.write_text(f"<html><body><h1>Dashboard</h1><div id=app></div><script>{script}</script></body></html>")
    payload = {"session_id": session(), "tool_name": "Artifact", "tool_input": {"file_path": str(page)}}
    assert run_hook(payload) == ""


def test_artifact_read_is_silent(tmp_path: Path) -> None:
    page = tmp_path / "report.md"
    page.write_text(PROSE)
    payload = {"session_id": session(), "tool_name": "Artifact", "tool_input": {"action": "read", "file_path": str(page)}}
    assert run_hook(payload) == ""


def test_document_reminder_respects_disable_switch() -> None:
    out = run_hook(docs_update(session(), "doc-1", "n1", PROSE), env={"AI_WRITING_PIPELINE_HOOK": "0"})
    assert out == ""


def test_hooks_json_watches_artifact_and_connector_writes() -> None:
    import re

    config = json.loads((HOOKS / "hooks.json").read_text())
    matchers = [entry["matcher"] for entry in config["hooks"]["PostToolUse"]]

    def matched(tool: str) -> bool:
        return any(re.fullmatch(m, tool) for m in matchers)

    assert matched("Artifact")
    assert matched("mcp__claude_ai_Claude_Docs__update")
    assert matched("mcp__claude_ai_Claude_Docs__batch")
    assert matched("mcp__notion__create_page")
    assert not matched("mcp__claude_ai_Slack__slack_search_public")
    assert not matched("mcp__claude_ai_Granola__get_meetings")


@pytest.mark.parametrize(
    "tool",
    [
        "mcp__claude_ai_Slack__slack_send_message",  # already sent; a rewrite would mean re-sending
        "mcp__claude_ai_Gmail__reply",
        "mcp__claude_ai_Support_MCP__desk_reply",
        "mcp__github__add_comment",
        "mcp__claude_ai_Gmail__get_draft",  # reads that contain a write verb
        "mcp__claude_ai_Gmail__list_drafts",
    ],
)
def test_sending_and_reading_tools_are_silent(tool: str) -> None:
    payload = {"session_id": session(), "tool_name": tool, "tool_input": {"body": PROSE}}
    assert run_hook(payload) == ""


def test_camel_case_write_tool_reminds() -> None:
    payload = {"session_id": session(), "tool_name": "mcp__notion__createPage", "tool_input": {"body": PROSE}}
    assert "writing-pipeline" in context_of(run_hook(payload))


def test_different_tools_on_one_document_remind_once() -> None:
    sid = session()
    first = docs_update(sid, "doc-1", "n1", PROSE)
    first["tool_name"] = "mcp__claude_ai_Claude_Docs__batch"
    assert run_hook(first)
    assert run_hook(docs_update(sid, "doc-1", "n2", PROSE)) == ""


def test_each_new_document_without_an_id_reminds() -> None:
    sid = session()
    for title in ("Q3 plan", "Hiring update"):
        payload = {
            "session_id": sid,
            "tool_name": "mcp__claude_ai_Claude_Docs__batch",
            "tool_input": {"container": {"kind": "project", "create": {"name": title, "doc": {"markdown": title + ". " + PROSE}}}},
        }
        assert run_hook(payload), title


def test_link_urls_in_the_body_are_not_document_ids() -> None:
    sid = session()
    for page in ("p1", "p2"):
        payload = {
            "session_id": sid,
            "tool_name": "mcp__notion__update_page",
            "tool_input": {"page_id": page, "children": [{"text": PROSE, "link": {"url": "https://example.com/spec"}}]},
        }
        assert run_hook(payload), page


def test_artifact_with_a_large_head_still_reminds(tmp_path: Path) -> None:
    page = tmp_path / "report.html"
    css = "/* font */ @font-face { src: url(data:font/woff2;base64," + "A" * 400_000 + "); }"
    page.write_text(f"<html><head><style>{css}</style></head><body><p>{PROSE}</p></body></html>")
    payload = {"session_id": session(), "tool_name": "Artifact", "tool_input": {"file_path": str(page)}}
    assert "writing-pipeline" in context_of(run_hook(payload))


def test_script_and_hooks_json_agree_on_write_tools() -> None:
    """The verb list lives in both places; this keeps them from drifting."""
    import importlib.util
    import re

    spec = importlib.util.spec_from_file_location("prose_check", HOOKS / "prose_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = json.loads((HOOKS / "hooks.json").read_text())
    matcher = next(e["matcher"] for e in config["hooks"]["PostToolUse"] if "mcp__" in e["matcher"])
    # Every tool the script treats as a write has to reach it through hooks.json.
    # The script also drops reads that hooks.json lets through (get_draft).
    for tool in (
        "mcp__s__create_page", "mcp__s__update", "mcp__s__batch", "mcp__s__create_draft",
        "mcp__s__createPage", "mcp__s__updateDoc", "mcp__s__saveNote", "mcp__s__publish_post",
        "mcp__s__slack_send_message", "mcp__s__reply", "mcp__s__get_draft", "mcp__s__search",
    ):
        if module.writes_document(tool):
            assert re.fullmatch(matcher, tool), tool


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
