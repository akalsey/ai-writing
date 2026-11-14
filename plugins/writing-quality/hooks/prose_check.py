#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""PostToolUse hook: remind Claude to run the writing pipeline on prose.

Fires after Write/Edit on a document that looks like a prose deliverable, once
per file per session, and after a Bash call that opens a pull request with a
hand-written body. Emits additionalContext rather than blocking, so a write is
never rejected because of this hook.

Disable for a session with AI_WRITING_PIPELINE_HOOK=0.

Any unexpected failure exits 0 silently. A hook that breaks the user's edit is
worse than a hook that misses a reminder.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import sys
import tempfile
from pathlib import Path

PROSE_SUFFIXES = {".md", ".markdown", ".mdx", ".txt", ".rst", ".adoc", ".org"}

# Directories that never hold a prose deliverable.
SKIP_DIR_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "target",
    "vendor",
    "site-packages",
    "__pycache__",
    ".next",
    ".cache",
    "coverage",
}

# Instruction and config files that happen to be Markdown. These are read by
# tools, not by people, so the cold-reader and voice checks don't apply.
SKIP_NAMES = {
    "CLAUDE.md",
    "AGENTS.md",
    "GEMINI.md",
    "LICENSE.md",
    "CODEOWNERS",
}

# Below this, the write is a tweak rather than a draft worth auditing.
MIN_BYTES = 600

CHECKS = (
    "the concise pass first (cut what the reader doesn't need), then the "
    "cold-reader-docs audit (so a reader outside this conversation can "
    "follow it), then the clear-prose pass (so each sentence says who did what, "
    "in words the reader would use), then the avoid-ai-writing pass (to strip "
    "machine tells), then a full re-read."
)

REMINDER = (
    "This edit touched a prose document. Before treating it as finished, run the "
    f"writing-pipeline skill on it: {CHECKS} Skip this only if the file is not a "
    "deliverable, and say so if you skip it."
)

PR_REMINDER = (
    "That command opened a pull request with a body written in this session. A "
    f"pull request description is a prose deliverable: run the writing-pipeline "
    f"skill on the body, {CHECKS} If the body changes, update the pull request "
    "with `gh pr edit <number> --body-file <file>`."
)

# Flags that put hand-written text in the PR body. `--fill` alone copies commit
# messages, which the pipeline doesn't cover.
PR_BODY_FLAGS = {"--body", "-b", "--body-file", "-F"}

# Tokens that end one shell command and start the next.
COMMAND_SEPARATORS = {"&&", "||", "|", ";", "&"}


def target_path(payload: dict) -> Path | None:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    return Path(raw) if isinstance(raw, str) and raw else None


def is_prose(path: Path) -> bool:
    if path.suffix.lower() not in PROSE_SUFFIXES:
        return False
    if path.name in SKIP_NAMES:
        return False
    return not any(part in SKIP_DIR_PARTS for part in path.parts)


def opens_pr_with_body(command: str) -> bool:
    """True if any command in the shell line is `gh pr create` with a body flag.

    The whole line is tokenized once, so separators inside quoted titles and
    bodies stay inside their argument. A command that merely mentions
    `gh pr create` inside a quoted string (an echo, a grep) is one token and
    doesn't match. If an unbalanced quote (an apostrophe in an unquoted
    heredoc) defeats shlex, whitespace tokens are good enough to find the flags.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    for i in range(len(tokens) - 2):
        if tokens[i : i + 3] != ["gh", "pr", "create"]:
            continue
        for token in tokens[i + 3 :]:
            if token in COMMAND_SEPARATORS:
                break
            if token.split("=", 1)[0] in PR_BODY_FLAGS:
                return True
    return False


def bash_command(payload: dict) -> str | None:
    if payload.get("tool_name") != "Bash":
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    return command if isinstance(command, str) else None


def emit(context: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": context,
            }
        },
        sys.stdout,
    )


def already_reminded(session_id: str, path: Path) -> bool:
    """Record this file for the session. True if it was already recorded.

    One reminder per file per session. Re-firing on every edit of the same
    document turns the hook into noise, and noise gets it turned off.
    """
    if not session_id:
        return False
    state_dir = Path(tempfile.gettempdir()) / "ai-writing-pipeline-hook"
    key = hashlib.sha256(str(path).encode()).hexdigest()[:32]
    marker = state_dir / session_id.replace("/", "_") / key
    if marker.exists():
        return True
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    return False


def main() -> int:
    if os.environ.get("AI_WRITING_PIPELINE_HOOK") == "0":
        return 0

    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0

    command = bash_command(payload)
    if command is not None:
        if opens_pr_with_body(command):
            emit(PR_REMINDER)
        return 0

    path = target_path(payload)
    if path is None or not is_prose(path):
        return 0

    try:
        if path.stat().st_size < MIN_BYTES:
            return 0
    except OSError:
        return 0

    if already_reminded(str(payload.get("session_id") or ""), path):
        return 0

    emit(REMINDER)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        raise SystemExit(0)
