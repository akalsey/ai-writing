#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Validate and package the skills in this repo as distributable .skill files.

A .skill file is a zip archive whose single top-level entry is the skill
directory, matching package_skill.py from anthropics/skills. The resulting
file uploads to claude.ai (Settings > Capabilities > Skills) and the Skills API.

Usage:
    ./build.py list
    ./build.py validate [skill ...]
    ./build.py package  [skill ...]   [--out DIR]
    ./build.py clean

With no skill names, validate and package operate on every skill.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent
PLUGINS_DIR = REPO / "plugins"
MARKETPLACE = REPO / ".claude-plugin" / "marketplace.json"
DIST_DIR = REPO / "dist"

# Mirrors the exclusion set in anthropics/skills package_skill.py.
EXCLUDE_DIRS = {"__pycache__", "node_modules", ".git"}
EXCLUDE_GLOBS = {"*.pyc"}
EXCLUDE_FILES = {".DS_Store"}
ROOT_EXCLUDE_DIRS = {"evals"}  # excluded only directly under the skill root

# Agent Skills spec: the six fields accepted by claude.ai uploads, the Skills
# API, and Claude Code alike. Anything else fails validation on those paths.
ALLOWED_KEYS = {
    "name",
    "description",
    "license",
    "allowed-tools",
    "metadata",
    "compatibility",
}
MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_COMPATIBILITY = 500

# Fixed mtime so repeated builds of unchanged sources are byte-identical.
# Override with SOURCE_DATE_EPOCH.
DEFAULT_ZIP_DATE = (2020, 1, 1, 0, 0, 0)


def zip_date() -> tuple[int, int, int, int, int, int]:
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if not epoch:
        return DEFAULT_ZIP_DATE
    return time.gmtime(int(epoch))[:6]


def discover_plugins() -> list[Path]:
    if not PLUGINS_DIR.is_dir():
        return []
    return sorted(
        p for p in PLUGINS_DIR.iterdir() if (p / ".claude-plugin" / "plugin.json").is_file()
    )


def discover() -> list[Path]:
    """Every skill directory across every plugin, sorted by skill name.

    Skill names must be unique repo-wide: they name the .skill bundle in dist/
    and the Makefile target, neither of which is scoped by plugin.
    """
    skills = [
        skill
        for plugin in discover_plugins()
        for skill in (plugin / "skills").glob("*/SKILL.md")
    ]
    return sorted((s.parent for s in skills), key=lambda p: p.name)


def resolve(names: list[str]) -> list[Path]:
    everything = discover()
    if not names:
        return everything
    by_name = {p.name: p for p in everything}
    chosen, missing = [], []
    for name in names:
        # Accept a bare name, a path, or a dist filename.
        key = Path(name).name.removesuffix(".skill")
        if key in by_name:
            chosen.append(by_name[key])
        else:
            missing.append(name)
    if missing:
        known = ", ".join(sorted(by_name)) or "(none)"
        die(f"unknown skill(s): {', '.join(missing)}\n   known skills: {known}")
    return chosen


def die(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_frontmatter(skill_md: Path) -> dict:
    """Return the parsed frontmatter, raising ValueError on any spec violation."""
    content = skill_md.read_text(encoding="utf-8")
    if not content.startswith("---"):
        raise ValueError("no YAML frontmatter (file must begin with '---')")
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        raise ValueError("frontmatter is not closed with '---'")
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a YAML mapping")

    unexpected = set(data) - ALLOWED_KEYS
    if unexpected:
        raise ValueError(
            f"unexpected frontmatter key(s): {', '.join(sorted(unexpected))}. "
            f"Allowed: {', '.join(sorted(ALLOWED_KEYS))}"
        )

    name = data.get("name")
    if name is None:
        raise ValueError("missing required field 'name'")
    if not isinstance(name, str):
        raise ValueError(f"'name' must be a string, got {type(name).__name__}")
    name = name.strip()
    if not re.fullmatch(r"[a-z0-9-]+", name):
        raise ValueError(f"name {name!r} must be kebab-case (a-z, 0-9, hyphen)")
    if name.startswith("-") or name.endswith("-") or "--" in name:
        raise ValueError(f"name {name!r} cannot lead/trail a hyphen or double one")
    if len(name) > MAX_NAME:
        raise ValueError(f"name is {len(name)} chars, max is {MAX_NAME}")

    description = data.get("description")
    if description is None:
        raise ValueError("missing required field 'description'")
    if not isinstance(description, str):
        raise ValueError(
            f"'description' must be a string, got {type(description).__name__}"
        )
    if "<" in description or ">" in description:
        raise ValueError("description cannot contain angle brackets (< or >)")
    if len(description) > MAX_DESCRIPTION:
        raise ValueError(
            f"description is {len(description)} chars, max is {MAX_DESCRIPTION}"
        )

    compatibility = data.get("compatibility")
    if compatibility is not None:
        if not isinstance(compatibility, str):
            raise ValueError("'compatibility' must be a string")
        if len(compatibility) > MAX_COMPATIBILITY:
            raise ValueError(
                f"compatibility is {len(compatibility)} chars, "
                f"max is {MAX_COMPATIBILITY}"
            )
    return data


def validate_skill(skill: Path) -> list[str]:
    """Validate one skill. Returns warnings; raises ValueError on hard failures."""
    data = parse_frontmatter(skill / "SKILL.md")
    warnings = []

    # The directory name is what Claude Code uses for the command in personal and
    # project skills, and it becomes the archive root. A mismatch means the skill
    # answers to a different name depending on how it was installed.
    if data["name"] != skill.name:
        warnings.append(
            f"frontmatter name {data['name']!r} != directory name {skill.name!r}; "
            f"the packaged archive and the /command will use {skill.name!r}"
        )

    length = len(data["description"])
    if length > MAX_DESCRIPTION * 0.9:
        warnings.append(
            f"description is {length}/{MAX_DESCRIPTION} chars — close to the cap "
            f"that claude.ai uploads and the Skills API enforce"
        )
    return warnings


def should_exclude(rel: Path) -> bool:
    parts = rel.parts
    if any(part in EXCLUDE_DIRS for part in parts):
        return True
    # rel is relative to the skill's parent, so parts[0] is the skill directory
    # and parts[1] is its first level of children.
    if len(parts) > 1 and parts[1] in ROOT_EXCLUDE_DIRS:
        return True
    if rel.name in EXCLUDE_FILES:
        return True
    return any(fnmatch.fnmatch(rel.name, pat) for pat in EXCLUDE_GLOBS)


def package_skill(skill: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{skill.name}.skill"
    date = zip_date()

    members = []
    for path in sorted(skill.rglob("*")):
        if not path.is_file():
            continue
        arcname = path.relative_to(skill.parent)
        if should_exclude(arcname):
            continue
        members.append((path, arcname))

    tmp = target.with_suffix(".skill.tmp")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for path, arcname in members:
                info = zipfile.ZipInfo(str(arcname), date_time=date)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                zf.writestr(info, path.read_bytes())
        tmp.replace(target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    size = target.stat().st_size
    rel = target.relative_to(REPO) if target.is_relative_to(REPO) else target
    print(f"  {rel}  ({len(members)} files, {size:,} bytes)")
    return target


def validate_marketplace() -> tuple[list[str], list[str]]:
    """Cross-check marketplace.json against what's actually on disk."""
    errors, warnings = [], []
    if not MARKETPLACE.is_file():
        return [f"{MARKETPLACE.relative_to(REPO)} not found"], []
    try:
        catalog = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"marketplace.json is not valid JSON: {exc}"], []

    for field in ("name", "owner", "plugins"):
        if field not in catalog:
            errors.append(f"marketplace.json is missing required field {field!r}")
    if errors:
        return errors, warnings

    # Sources are relative to the repo root, not to .claude-plugin/. This repo
    # deliberately avoids metadata.pluginRoot: the docs don't say what it's
    # relative to, and a wrong guess breaks installs rather than failing loudly.
    if "pluginRoot" in catalog.get("metadata", {}):
        warnings.append(
            "metadata.pluginRoot is set; its base path is undocumented, so "
            "on-disk checks here may disagree with how Claude Code resolves it"
        )

    listed = set()
    for entry in catalog["plugins"]:
        name = entry.get("name", "<unnamed>")
        listed.add(name)
        source = entry.get("source")
        if not isinstance(source, str):
            warnings.append(f"{name}: non-path source, skipping on-disk check")
            continue
        plugin_dir = (REPO / source).resolve()
        manifest = plugin_dir / ".claude-plugin" / "plugin.json"
        if not manifest.is_file():
            errors.append(f"{name}: no plugin.json at {source}")
            continue
        try:
            plugin = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{name}: plugin.json is not valid JSON: {exc}")
            continue
        if plugin.get("name") != name:
            errors.append(
                f"{name}: marketplace entry disagrees with plugin.json name "
                f"{plugin.get('name')!r}"
            )
        # A stale version in one file is invisible until someone installs the
        # plugin and gets a version string that doesn't match the release.
        listed_version = entry.get("version")
        if listed_version is not None and listed_version != plugin.get("version"):
            errors.append(
                f"{name}: marketplace says version {listed_version!r}, "
                f"plugin.json says {plugin.get('version')!r}"
            )

    on_disk = {p.name for p in discover_plugins()}
    for orphan in sorted(on_disk - listed):
        warnings.append(f"plugin {orphan!r} exists on disk but isn't in marketplace.json")
    return errors, warnings


def plugin_versions() -> dict[str, str | None]:
    versions = {}
    for plugin in discover_plugins():
        manifest = plugin / ".claude-plugin" / "plugin.json"
        try:
            versions[plugin.name] = json.loads(
                manifest.read_text(encoding="utf-8")
            ).get("version")
        except (OSError, json.JSONDecodeError):
            versions[plugin.name] = None
    return versions


def cmd_version(args: argparse.Namespace) -> int:
    """Report plugin versions, or assert they all match an expected one.

    The release workflow calls this with the git tag, so a tag that disagrees
    with the manifests fails the build instead of shipping a mislabeled release.
    """
    versions = plugin_versions()
    if not versions:
        die("no plugins found")

    # removeprefix, not lstrip: lstrip("v") would strip every leading "v",
    # diverging from the release workflow's ${tag#v}, which strips exactly one.
    expected = args.expect.removeprefix("v") if args.expect else None
    mismatched = False
    for name, version in sorted(versions.items()):
        note = ""
        if expected is not None and version != expected:
            note = f"  <- expected {expected}"
            mismatched = True
        print(f"{name:<20} {version or '(none)'}{note}")

    if mismatched:
        print(
            f"\nerror: plugin versions disagree with {args.expect!r}. "
            f"Update plugin.json and marketplace.json, or retag.",
            file=sys.stderr,
        )
        return 1
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    skills = discover()
    if not skills:
        print(f"no skills found under {PLUGINS_DIR.relative_to(REPO)}/")
        return 0
    name_w = max(len(s.name) for s in skills)
    plugin_w = max(len(s.parent.parent.name) for s in skills)
    for skill in skills:
        try:
            data = parse_frontmatter(skill / "SKILL.md")
            summary = data["description"].split(". ")[0].rstrip(".")
            if len(summary) > 62:
                summary = summary[:59] + "..."
        except ValueError as exc:
            summary = f"INVALID: {exc}"
        plugin = skill.parent.parent.name
        print(f"{plugin:<{plugin_w}}  {skill.name:<{name_w}}  {summary}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    failed = 0

    # A duplicate name would make two skills compete for one dist/<name>.skill
    # and one Makefile target, and the loser would be silently overwritten.
    seen: dict[str, Path] = {}
    for skill in discover():
        if skill.name in seen:
            print(
                f"FAIL  duplicate skill name {skill.name!r}: "
                f"{seen[skill.name].relative_to(REPO)} and {skill.relative_to(REPO)}"
            )
            failed += 1
        seen[skill.name] = skill

    errors, warnings = validate_marketplace()
    for error in errors:
        print(f"FAIL  marketplace: {error}")
        failed += 1
    for warning in warnings:
        print(f"      warning: marketplace: {warning}")
    if not errors:
        print("ok    marketplace")

    for skill in resolve(args.skills):
        try:
            skill_warnings = validate_skill(skill)
        except ValueError as exc:
            print(f"FAIL  {skill.name}: {exc}")
            failed += 1
            continue
        print(f"ok    {skill.name}")
        for warning in skill_warnings:
            print(f"      warning: {warning}")
    return 1 if failed else 0


def cmd_package(args: argparse.Namespace) -> int:
    out_dir = Path(args.out).resolve() if args.out else DIST_DIR
    skills = resolve(args.skills)

    failed = 0
    for skill in skills:
        try:
            warnings = validate_skill(skill)
        except ValueError as exc:
            print(f"FAIL  {skill.name}: {exc}", file=sys.stderr)
            failed += 1
            continue
        for warning in warnings:
            print(f"warning: {skill.name}: {warning}", file=sys.stderr)
        print(f"packaging {skill.name}")
        package_skill(skill, out_dir)

    if failed:
        print(
            f"\n{failed} skill(s) failed validation and were not packaged.",
            file=sys.stderr,
        )
        return 1
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    if not DIST_DIR.exists():
        return 0
    removed = 0
    for pattern in ("*.skill", "*.tmp", "SHA256SUMS"):
        for path in sorted(DIST_DIR.glob(pattern)):
            path.unlink()
            removed += 1
    if not any(DIST_DIR.iterdir()):
        DIST_DIR.rmdir()
    print(f"removed {removed} file(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="build.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list the skills in this repo").set_defaults(
        func=cmd_list
    )

    p_validate = sub.add_parser("validate", help="check skills against the spec")
    p_validate.add_argument("skills", nargs="*", help="skill names (default: all)")
    p_validate.set_defaults(func=cmd_validate)

    p_package = sub.add_parser("package", help="build .skill files")
    p_package.add_argument("skills", nargs="*", help="skill names (default: all)")
    p_package.add_argument("--out", help=f"output directory (default: {DIST_DIR.name}/)")
    p_package.set_defaults(func=cmd_package)

    p_version = sub.add_parser("version", help="show or assert plugin versions")
    p_version.add_argument(
        "--expect",
        help="fail unless every plugin declares this version (leading 'v' optional)",
    )
    p_version.set_defaults(func=cmd_version)

    sub.add_parser("clean", help="remove built .skill files").set_defaults(
        func=cmd_clean
    )

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
