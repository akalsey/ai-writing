# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A Claude Code plugin marketplace for tools that improve AI writing, plus a build system that packages each skill as a standalone `.skill` bundle. The content is Markdown with YAML frontmatter — the "program" is the prose. `make validate` checks the frontmatter and marketplace contracts; it cannot check whether the writing rules are any good. That's done by running the skills against text.


## Layout

```
.claude-plugin/marketplace.json     # catalog; lists every plugin
plugins/
  writing-quality/                  # always-run checks
    .claude-plugin/plugin.json
    hooks/hooks.json                # PostToolUse -> prose_check.py
    hooks/run.sh                    # launcher: python3, else uv, else silent
    hooks/prose_check.py
    output-styles/clear-reports.md  # opt-in; Claude Code only
    skills/avoid-ai-writing/        # SKILL.md + test-corpus.md
    skills/clear-prose/             # SKILL.md + test-corpus.md
    skills/concise/                 # SKILL.md + test-corpus.md
    skills/cold-reader-docs/
    skills/writing-pipeline/        # orders the other four
tests/test_prose_check.py           # hook tests (uv script, pytest)
build.py                            # validate + package (uv script, PEP 723)
Makefile                            # on-demand build front end
dist/                               # generated .skill bundles (gitignored)
```

The marketplace is scoped to "improving AI writing" broadly, not just to the one plugin it ships today. Detection and watermark-removal plugins are planned as siblings under `plugins/`, so keep anything shared generic enough to survive that.

### Where a new skill goes

`writing-quality` holds what runs on every document. A skill that runs only in some cases (matching one person's voice, detecting machine text) belongs in its own plugin, so people can install it or not. That's the split: cadence of use, not subject matter.

Everything here is distributed, so nothing in a skill may be specific to one person or organization. Examples, test passages, and names are invented, and the corpora deliberately range across domains. A personal voice skill built on top of `avoid-ai-writing` lives outside this repo.

If a skill in one plugin depends on a skill in another, it refers to the sibling **by skill name, never by path**. The install path differs across all three distribution routes, so a hardcoded path breaks at least two of them. It also has to handle the sibling being absent, rather than silently skipping the step.

### Adding a skill

Create `plugins/<plugin>/skills/<name>/SKILL.md`. Nothing else registers it; `build.py` discovers by globbing.

Two invariants the validator enforces:

- **Skill names are unique repo-wide**, not per plugin. Bundles are `dist/<skill>.skill` and Makefile targets are bare skill names, neither of which is scoped by plugin, so a collision would silently overwrite.
- **The directory name is authoritative.** It sets the `/command` and becomes the root entry inside the archive. Frontmatter `name` should match; a mismatch warns.

Don't nest a `.claude-plugin/plugin.json` inside a skill directory. The plugin root is `plugins/<plugin>/`, and a nested manifest makes the skill load as a *separate* plugin (`<name>@skills-dir`) instead of part of its own.

Adding or editing a skill is a shipped change: bump the plugin version in the same commit. See [Versioning](#versioning-bump-on-every-shipped-edit).

## Build and distribute

```fish
make                    # package every changed skill into dist/
make clear-prose        # package one skill by name
make validate           # skills against the spec + marketplace against disk
make flat               # flat zips (SKILL.md at the root) for Grok, into dist/flat/
make test               # hook and build tests
make list               # each skill with its plugin
make clean              # remove dist/
./build.py version      # plugin versions; --expect X asserts they all match
```

`build.py` is the implementation; the Makefile adds change detection and generates one rule per skill directory. Call `build.py` directly for anything the Makefile doesn't cover (`./build.py package --out /some/dir`).

A `.skill` file is a zip whose single top-level entry is the skill directory — the format [`package_skill.py`](https://github.com/anthropics/skills) produces, accepted by claude.ai skill uploads (Settings → Capabilities → Skills) and the Skills API. `make flat` (`build.py package --format flat`) builds a second format: `dist/flat/<skill>.zip` with `SKILL.md` at the archive root rather than inside a skill directory. That's the layout Grok's skill upload expects, per third-party guides; it hasn't been confirmed against xAI documentation, so if a Grok upload fails, check the layout first. Releases attach both formats.

Skill text has to stay tool-neutral so the same files work in Grok and other Agent Skills clients: no Claude Code tool names ("the Edit tool"), no slash commands, no hook references in the instructions themselves.

Builds are deterministic: fixed zip timestamps and sorted entries, so an unchanged skill rebuilds byte-identical. Override the timestamp with `SOURCE_DATE_EPOCH`.

`make validate` also cross-checks `marketplace.json` against disk: every listed plugin must have a `plugin.json` whose `name` and `version` agree with the catalog entry, and a plugin on disk that isn't listed warns.

## Versioning: bump on every shipped edit

**Any change to a plugin's shipped content requires bumping that plugin's version, in two files, in the same commit as the change.** Not at release time — at edit time. This is the rule that gets forgotten, because editing a `SKILL.md` doesn't feel like shipping a new version.

Shipped content is anything under `plugins/<name>/`: a `SKILL.md`, a supporting file like `test-corpus.md`, `hooks.json`, or the hook script. Change any of it and update both:

1. `plugins/<name>/.claude-plugin/plugin.json` → `version`
2. the matching entry in `.claude-plugin/marketplace.json` → `version`

Bump only the plugins you touched.

`make validate` fails if the two files disagree, so a half-done bump gets caught. Nothing catches a bump you skipped entirely — that's on you, and the cost is that people who already installed the plugin keep running stale content, since Claude Code updates plugins by version.

| Change | Bump |
|---|---|
| Rule wording, a new vocabulary entry, a fixed typo | patch (`0.1.0` → `0.1.1`) |
| New skill, new capability, edited `description` triggers, changed hook behavior | minor (`0.1.0` → `0.2.0`) |
| Renamed or removed a skill, restructured a plugin, anything that breaks an existing install | major (`0.1.0` → `1.0.0`) |

**Don't bump for repo infrastructure.** Edits to `build.py`, the `Makefile`, `CLAUDE.md`, `.gitignore`, or `.github/workflows/` change nothing that anyone installs. `metadata.version` in `marketplace.json` tracks the catalog itself — bump it when adding or removing a plugin, not when a skill's prose changes.

## Releasing

CI lives in `.github/workflows/`. `validate.yml` runs `make validate`, builds, and asserts the build is byte-reproducible on every push and PR. `release.yml` fires on a `v*` tag.

```fish
./build.py version --expect 0.2.0   # confirm manifests agree BEFORE tagging
git tag v0.2.0; and git push origin v0.2.0
```

The release job gates on that same check, so a tag that disagrees with the manifests fails instead of publishing bundles whose declared version contradicts the release name.

A tag names one version, but plugins version independently, so the tag can only match if every plugin is on the same number. When they drift apart, either bring them level before tagging or release the plugins on separate tags.

Releases exist for the claude.ai and Skills API route only. **Claude Code users never need them** — `/plugin install` reads `plugins/` straight from the repo, so `dist/` stays gitignored and no `.skill` file is ever committed. Release archives pin `SOURCE_DATE_EPOCH` to the tagged commit, so anyone can rebuild the published bytes.

**Marketplace sources are repo-root-relative** (`./plugins/writing-quality`). This repo deliberately does not set `metadata.pluginRoot` — the docs don't say what it's relative to, and guessing wrong breaks installs silently rather than failing loudly.

### Frontmatter is restricted to six fields

`name`, `description`, `license`, `allowed-tools`, `metadata`, `compatibility`. Claude Code accepts more (`argument-hint`, `disable-model-invocation`, `paths`), but claude.ai uploads and the Skills API reject unknown keys outright, and `build.py validate` fails the build. Anything Claude Code-specific has to stay out of these files for the `.skill` route to keep working.

The `description` is the dispatch surface — it decides whether a skill fires, and carries trigger phrasings deliberately ("remove AI-isms," "turn this into a doc"). Adding a capability without adding its trigger phrase means the skill won't be invoked for it. `avoid-ai-writing` sits at 980 of the 1024-character cap, so new triggers there have to displace old ones.

## The hook

`writing-quality` bundles a `PostToolUse` hook on `Write|Edit|MultiEdit|NotebookEdit`, on `Bash`, and on `Artifact` plus connector tools whose names say they write a document (`mcp__<server>__…create|update|batch|draft|edit|save|…`). It emits `additionalContext` reminding Claude to run `writing-pipeline`. The skill documents the procedure; the hook is what makes it happen on documents nobody thought to check.

For file writes, it fires only on prose-looking files, once per file per session, and only above 600 bytes. For `Bash`, it fires only when a command runs `gh pr create` with `--body`, `-b`, `--body-file`, or `-F`. A bare `--fill` copies commit messages and is skipped. So is `gh pr edit`, because that's how Claude applies the fix, and reminding on the fix would loop. For `Artifact` and connector writes, it doesn't know each connector's payload shape and doesn't try to. It gathers every string in the tool input longer than 80 characters (for `Artifact`, the published file's visible text) and fires when that text looks like prose: over 600 bytes, at least four sentence endings, and at least 85% letters and spaces, which keeps code, JSON, and tables out. It dedups per document per connector server, preferring a whole-document id (`document_id`, `page_id`, `url`, `container.id`, searched only in the top two levels so a link inside the body doesn't count) over a section id, so filling a document section by section reminds once. A new document with no id yet is keyed by its text. In the script, the first verb in the tool name decides: `create_page` and `updateDoc` write, `get_draft` reads. `hooks.json` prefilters on the same write verbs, and a test keeps the two in agreement.

Sending tools (`send`, `reply`, `post`, `comment`) are deliberately not watched. The hook runs after the call, so by then the message is gone, and a reminder to fix and write it back would mean sending it twice. Drafts are watched, so a draft-then-send flow gets the reminder at the draft. This exists because a session that wrote its deliverables through the Claude Docs connector never got a reminder, and the pipeline didn't run.

The PR reminder fires after the PR exists, since a PostToolUse hook can't see the body before it's sent; the reminder tells Claude to update the body with `gh pr edit`. Those filters exist because a hook that nags on every source file gets turned off, which is worse than no hook. It never blocks a write, and any unexpected failure exits 0 silently — breaking someone's edit is a worse outcome than missing a reminder. `AI_WRITING_PIPELINE_HOOK=0` disables it.

`hooks.json` runs `sh hooks/run.sh`, not the Python script. The script is stdlib-only and runs on Python 3.8+, so the launcher uses `python3` when it's on `PATH` and falls back to `uv run` only when it isn't. Most people installing a plugin don't have uv, and a hook that needs it would error after every write for them. With neither interpreter, the launcher exits 0 and says nothing. Keep the script stdlib-only and 3.8-compatible; a dependency would break the `python3` path.

Test it by piping a payload to the script directly rather than by triggering real writes:

```fish
echo '{"session_id":"t1","tool_name":"Write","tool_input":{"file_path":"/tmp/memo.md"}}' \
  | plugins/writing-quality/hooks/prose_check.py
```

Silence means filtered out. Check the file exists and clears 600 bytes before assuming the filter logic is wrong.

`make test` runs `tests/test_prose_check.py`, which pipes payloads the same way and covers both triggers and the filters. CI runs it. Add a case there for any change to what the hook matches.

## The output style

`output-styles/clear-reports.md` applies the `clear-prose` rules to Claude's own chat messages: status updates and end-of-task reports, which none of the skills or the hook can reach. It's opt-in: pick it from the `/output-style` menu or `/config`. It deliberately does not set `force-for-plugin`: installing a writing plugin shouldn't silently change how Claude talks in every session. `keep-coding-instructions: true` keeps Claude Code's normal behavior and adds the style on top.

Output styles are a Claude Code feature, so this file never goes into a `.skill` bundle. If you change a rule in `clear-prose`, check whether the style states the same rule and update it to match.

## How the skills relate

`writing-pipeline` is the entry point: the `concise` length cut first, then the cold-reader audit, then the `clear-prose` pass, then the AI-ism pass, then a re-read. The order is load-bearing and the skill explains why: the cut removes text nothing else should spend effort on, the cold-reader and clarity passes both write new sentences, and new sentences carry new machine tells, so running the surface pass earlier means editing text that's about to be replaced.

`concise` exists because the cold-reader and clarity passes only add. In testing, the pipeline without it grew a Slack reply to "is there an ETA?" from 141 words to 203. The word count after the cut is a budget the re-read step checks against. If you change either expanding pass, re-run a context-heavy drafting task (a short reply written after a long working session) and confirm the final isn't longer than the cut version. `concise` cuts content, never grammar: compressing survivors into fragments is a machine tell that `avoid-ai-writing` flags, so the two must not fight.

Two limits on `concise` came from the author, not from testing, and both are deliberate. It never removes a request: "fewer requests" in *Writing for Busy Readers* means merging duplicates and making implicit asks explicit, not choosing which of the author's questions survive. And it never adds formatting to a draft that has none, because the skill can't know where the text will be pasted; it may add a little Markdown only when the draft is already Markdown.

`clear-prose` and `cold-reader-docs` share a boundary. Labels the writer coined while doing the work ("the clone," "the knobs") belong to `cold-reader-docs`; `clear-prose` handles names that are wrong for the reader even when nothing was coined (inflated category nouns, invented compounds, verbs with a budget). `clear-prose` defers to the cold-reader pass for coinages, so keep that pointer if either file moves.

## Testing changes to `concise`

`plugins/writing-quality/skills/concise/test-corpus.md`: Part 1 should come back substantially shorter without losing an action, date, owner, or decision. Part 2 should come back essentially unchanged. Part 2's traps are the over-cut failures: compressing an already-short reply, stripping necessary detail from an incident write-up, dropping verification a reviewer needs, removing a needed definition, and treating one courtesy as padding.

The skill's job only shows up when the writer knows more than the reader needs, so the corpus alone isn't enough.

The length ceilings in step 5 behave like targets: in testing, every run landed within a few words of whatever ceiling was set. With a 150-word ceiling, team status updates came out at 153–163 words. At 100, they came out at 100–104. So set a ceiling at the length you want, not at a generous upper bound, and re-run a status update written after a long debugging session whenever you change one. Before the ceilings existed, `concise` had nothing to measure a request with no stated length against, and the same reports came out at 244–298 words. Editing someone else's bloated draft passed even before this skill existed. Also test drafting after a long working session, where the failure actually happens.

## Testing changes to `clear-prose`

`plugins/writing-quality/skills/clear-prose/test-corpus.md` works the same way as the `avoid-ai-writing` corpus below: Part 1 should trip each fault once, Part 2 should pass untouched. Its passages are deliberately different sentences from the SKILL.md examples, so a pass shows the rule generalized. Keep it that way when adding examples to either file. Passive voice, established nominalizations, and standard technical compounds are the false positives this skill is most likely to produce, and Part 2 exists to catch them.

## Testing changes to `avoid-ai-writing`

`plugins/writing-quality/skills/avoid-ai-writing/test-corpus.md` is the regression fixture. Run the skill in `detect` mode against it after changing or adding any rule.

- **Part 1** trips a named set of patterns and ships an expected-flags table mapping each numbered passage to the rule and section it should hit. A missed flag means the rule is too narrow or buried where it doesn't get read.
- **Part 2 is the one that matters.** It's human prose sitting deliberately close to the rules without tripping them. Every flag raised there is a false positive. The skill's stated risk posture is over-flagging, so a rule that fires on Part 2 gets narrowed or context-gated even if it catches real cases in Part 1. Revert and rewrite with the exclusion built in.
- Passage 3 is the dedup test: three rules cover overlapping spans in twelve words, and the detection heuristic says to attribute the span to the longest-covering pattern and drop the rest. Reporting three hits there is a counting bug, not three findings.

New rules are where false positives enter. Run both halves after every rule change, and add a Part 1 passage plus an expected-flags row for any rule you add.

## Structural conventions in `avoid-ai-writing`

The file is large and its sections carry load-bearing structure. When editing:

- **Vocabulary is tiered** (1 = always flag, 2 = flag in clusters of 2+ per paragraph, 3 = flag by density). Put new words in the right tier rather than defaulting to Tier 1.
- **Severity tiers** (P0 credibility killers / P1 obvious AI smell / P2 polish) exist so quick passes can run P0+P1 only. A new rule needs a P-tier entry.
- **Context profiles** (`linkedin`, `blog`, `technical-blog`, `investor-email`, `docs`, `casual`, `internal-memo`) each have a row-by-rule tolerance matrix. A new rule that isn't in the matrix applies at full strength everywhere by default — state that intentionally or add the row.
- **`internal-memo` inverts the cadence advice** that the rest of the file gives. The general rhythm rules are calibrated for blog prose; applied to a memo they manufacture the fragment-heavy shape that now reads as machine-written. Where the general rule and the `internal-memo` section conflict, the section wins.
- **The Cut / Ration / Keep bands** under "Assistant rhetorical tics" are the structural rules that survive a vocabulary cleanup. The **Keep** band exists specifically to stop an aggressive pass from stripping real voice — don't add rules that contradict it without reconciling.
- **Density thresholds need the dedup rule.** These patterns nest, so every count in the file ("one Cut-band instance per 400 words," "30% of sections," "three same-cardinality announcements") assumes each span is counted once.

## Editing the skills themselves

Every edit in this section is a shipped change. Bump the plugin version in the same commit — see [Versioning](#versioning-bump-on-every-shipped-edit).

These files are prose about how to write prose, which makes them a live target for their own rules. `avoid-ai-writing`'s self-reference escape hatch exempts quoted examples and code blocks, but not the surrounding authorial prose — the skill files should pass their own audit. Rules are written with their rationale and usually a before/after pair; match that shape when adding one.

Provenance is cited inline where a rule was adapted from an outside source (Wikipedia's Signs of AI writing, Simon Willison's cliché highlighter, `blader/humanizer`, `Aboudjem/humanizer-skill`, `brandonwise/humanizer`). Keep the attribution when you move or rewrite a rule.
