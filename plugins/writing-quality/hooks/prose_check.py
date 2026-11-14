#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.8"
# dependencies = []
# ///
"""PostToolUse hook: remind Claude to run the writing pipeline on prose.

Fires after Write/Edit on a document that looks like a prose deliverable, once
per file per session; after a Bash call that opens a pull request with a
hand-written body; and after a connector or Artifact call that writes prose to a
document or page, once per document per session. Emits additionalContext rather than blocking, so a write is
never rejected because of this hook.

Disable for a session with AI_WRITING_PIPELINE_HOOK=0.

Any unexpected failure exits 0 silently. A hook that breaks the user's edit is
worse than a hook that misses a reminder.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import sys
import tempfile
from html.parser import HTMLParser
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

# Tools whose file_path is a file the session just wrote.
FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

DOC_REMINDER = (
    "That call wrote prose to a document or page. If it's a deliverable, run the "
    f"writing-pipeline skill on the text: {CHECKS} If the text changes, write it "
    "back with the same tool."
)

# Connector tools are named mcp__<server>__<tool>. The first verb in the tool
# part decides whether it writes a document: create_page and updateDoc write,
# get_draft and list_drafts read. Sending verbs (send, reply, post, comment)
# don't count: once a message is sent, the pipeline can't help, and a "fix it"
# reminder would mean sending it twice. hooks.json prefilters on the same
# write verbs; this list is the one that decides.
WRITE_VERBS = {"create", "update", "write", "batch", "draft", "publish", "edit", "append", "insert", "save"}
READ_VERBS = {"get", "list", "search", "read", "find", "query", "fetch", "view", "show", "download"}

# Enough of a published page to judge it. Artifacts can be megabytes, and
# the prose test only needs a few hundred bytes of sentences.
MAX_PAGE_BYTES = 256_000

# A sentence end: a letter, then terminal punctuation, then space or the end.
SENTENCE_END = re.compile(r"[a-z][.!?](?:\s|$)")

# String leaves shorter than this are ids, titles, and enum values, not text.
MIN_LEAF = 80

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


def looks_like_prose(text: str) -> bool:
    """Long enough to be a draft, with sentences, and mostly words.

    The letter ratio keeps out code, JSON, and tables, which are long and can
    contain sentence-like punctuation but are mostly symbols and digits.
    """
    if len(text) < MIN_BYTES:
        return False
    sample = text[:20_000]
    if len(SENTENCE_END.findall(sample)) < 4:
        return False
    wordish = sum(c.isalpha() or c.isspace() for c in sample)
    return wordish / len(sample) >= 0.85


def walk(value: object, key: str = ""):
    """Yield (key, string) for every string in a nested dict/list payload."""
    if isinstance(value, str):
        yield key, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from walk(v, str(k))
    elif isinstance(value, list):
        for item in value:
            yield from walk(item, key)


def writes_document(tool_name: str) -> bool:
    if not tool_name.startswith("mcp__") or tool_name.count("__") < 2:
        return False
    tool = tool_name.rsplit("__", 1)[1]
    for word in re.findall(r"[A-Za-z][a-z]*", tool):
        word = word.lower()
        if word in WRITE_VERBS:
            return True
        if word in READ_VERBS:
            return False
    return False


# Identifiers for a whole document, in preference order. Only the top two
# levels of the input are searched, so a link's url inside the body isn't
# mistaken for the document's.
DOCUMENT_ID_KEYS = ("document_id", "doc_id", "page_id", "file_path", "url")


def document_id(tool_input: dict) -> str:
    levels = [tool_input] + [v for v in tool_input.values() if isinstance(v, dict)]
    for name in DOCUMENT_ID_KEYS:
        for level in levels:
            if isinstance(level.get(name), str) and level[name]:
                return level[name]
    container = tool_input.get("container")
    if isinstance(container, dict) and isinstance(container.get("id"), str):
        return container["id"]
    return ""


class _TextOnly(HTMLParser):
    """Collects visible text, skipping script and style."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)


def page_text(path: Path) -> str:
    with path.open(errors="ignore") as f:
        raw = f.read(16 * MAX_PAGE_BYTES)
    if path.suffix.lower() not in (".html", ".htm"):
        return raw[:MAX_PAGE_BYTES]
    # Drop script and style before capping: an inlined font or library in the
    # head can be larger than the whole cap.
    raw = SCRIPT_OR_STYLE.sub(" ", raw)[:MAX_PAGE_BYTES]
    parser = _TextOnly()
    parser.feed(raw)
    return " ".join(" ".join(parser.parts).split())


def document_call(payload: dict):
    """(dedup key, text) for a connector or Artifact call that writes a document, else None.

    Keys use the connector's server, not the tool, so a batch and an update on
    the same document share one. A new document has no id yet; its key comes
    from its text, so each new document gets its own reminder.
    """
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return None
    if tool_name == "Artifact":
        path = target_path(payload)
        if tool_input.get("action", "publish") != "publish" or path is None:
            return None
        return f"Artifact:{path}", lambda: page_text(path)
    if not writes_document(tool_name):
        return None
    server = tool_name.rsplit("__", 1)[0]
    text = "\n\n".join(v for _, v in walk(tool_input) if len(v) >= MIN_LEAF)
    doc = document_id(tool_input) or "new:" + hashlib.sha256(text[:300].encode()).hexdigest()[:16]
    return f"{server}:{doc}", lambda: text


def _marker(session_id: str, target: str) -> Path:
    state_dir = Path(tempfile.gettempdir()) / "ai-writing-pipeline-hook"
    key = hashlib.sha256(target.encode()).hexdigest()[:32]
    return state_dir / session_id.replace("/", "_") / key


def already_reminded(session_id: str, target: str) -> bool:
    """True if this file or document already got its reminder this session.

    One reminder per target per session. Re-firing on every edit of the same
    document turns the hook into noise, and noise gets it turned off.
    """
    return bool(session_id) and _marker(session_id, target).exists()


def mark_reminded(session_id: str, target: str) -> None:
    if session_id:
        marker = _marker(session_id, target)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()


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

    session_id = str(payload.get("session_id") or "")

    document = document_call(payload)
    if document is not None:
        target, text = document
        try:
            if not already_reminded(session_id, target) and looks_like_prose(text()):
                mark_reminded(session_id, target)
                emit(DOC_REMINDER)
        except OSError:
            pass
        return 0

    if payload.get("tool_name") not in FILE_TOOLS:
        return 0

    path = target_path(payload)
    if path is None or not is_prose(path):
        return 0

    try:
        if path.stat().st_size < MIN_BYTES:
            return 0
    except OSError:
        return 0

    if already_reminded(session_id, str(path)):
        return 0
    mark_reminded(session_id, str(path))

    emit(REMINDER)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        raise SystemExit(0)
