# ai-writing

Claude Code plugins that make AI-written documents better: clearer to a reader who wasn't there, and free of the patterns that mark text as machine-written.

The marketplace ships one plugin today, `writing-quality`. Its skills also work in claude.ai and through the Skills API.

## What's in `writing-quality`

Five skills, a hook, and an output style.

| Skill | What it does |
|---|---|
| `writing-pipeline` | The entry point. Runs the four checks below in order, then a full re-read, and defines when a document is done. |
| `concise` | Cuts a draft to what its reader needs. Puts the answer first, then removes whole sentences and sections the reader wouldn't miss: restated requests, background they already have, the writer's process, rejected alternatives, recaps. It cuts content, never grammar, and never drops an action, date, owner, or decision. |
| `cold-reader-docs` | Makes a document stand on its own for someone who wasn't in the conversation that produced it. Catches terms used before they're defined, pointers like "the approach we discussed," and shorthand the writer coined while working. |
| `clear-prose` | Sentence-level clarity. Checks that the actor is the subject and the action is the verb, that things are called what the reader would call them, and that each paragraph leads with its point. |
| `avoid-ai-writing` | Finds and removes AI writing patterns: tiered vocabulary, formatting habits, and the structural tics that survive a vocabulary cleanup. Has `detect`, `rewrite`, and `edit` modes, context profiles (blog, docs, internal memo, LinkedIn, and others), and optional voice profiles. |

The order matters. `concise` runs first so nothing later polishes a sentence that's about to be cut, and its result sets the length budget: the cold-reader and clarity passes add words when they define terms and unpack phrases, and without a budget they'll turn a short reply into a long one. Those two passes write new sentences, and new sentences can bring new AI patterns, so the `avoid-ai-writing` pass runs last, on the text that will actually ship.

The skills are editing tools, not detectors. Humans produce every one of these patterns too, especially under deadline or in a second language. Treat a flag as a reason to look at a sentence, not as proof of who wrote it.

### The hook

After Claude writes or edits a prose file (`.md`, `.txt`, `.rst`, and similar, over 600 bytes), the hook reminds it to run `writing-pipeline`. It does the same after `gh pr create` with a hand-written body. File reminders fire once per file per session. The hook never blocks a write, and it stays quiet on source code and on instruction files like `CLAUDE.md`.

The hook is a small Python script that uses only the standard library. It runs with any `python3` (3.8 or later) on your `PATH`, or with [uv](https://docs.astral.sh/uv/) if you have uv and no system Python. With neither, it does nothing: you lose the reminder, and nothing errors. The skills themselves are plain Markdown and need no Python at all.

To turn it off for a session:

```sh
export AI_WRITING_PIPELINE_HOOK=0
```

### The output style

`Clear reports` applies the `concise` and `clear-prose` rules to Claude's own status updates and end-of-task summaries, which the skills and the hook can't reach. It's opt-in: choose it from `/output-style` or `/config`. It keeps Claude Code's normal coding instructions and adds the reporting rules on top.

## Install

### Claude Code

```
/plugin marketplace add akalsey/ai-writing
/plugin install writing-quality@ai-writing
```

The skills trigger on their own when a task matches ("make this clearer," "remove the AI-isms," "turn this into a doc"). You can also invoke them directly, for example `/writing-quality:avoid-ai-writing detect` on a draft.

### claude.ai and the Skills API

Each skill is also packaged as a standalone `.skill` file, which you can upload at **claude.ai → Settings → Capabilities → Skills** or pass to the Skills API. Download them from a tagged release once one is published, or build them yourself (see below). The hook and the output style are Claude Code features and aren't part of the `.skill` bundles.

## Building and testing

You need `make` and Python 3.11 or later.

The scripts declare their dependencies inline, in the [PEP 723](https://peps.python.org/pep-0723/) format that [uv](https://docs.astral.sh/uv/) reads, so with uv installed there's nothing else to set up. Without uv, the Makefile falls back to `python3`, and you install the two dependencies yourself:

```sh
python3 -m venv .venv
.venv/bin/pip install pyyaml pytest
make validate test PYTHON=.venv/bin/python
```

`PYTHON` works the same way for every target. The commands below assume uv or an activated environment.

```sh
make              # package every changed skill into dist/
make clear-prose  # package one skill by name
make validate     # check skill frontmatter, and that marketplace.json matches each plugin.json
make test         # run the hook tests
make list         # list each skill with its plugin
```

Builds are deterministic: an unchanged skill rebuilds byte-for-byte identical. Set `SOURCE_DATE_EPOCH` to control the timestamp.

The skills themselves are tested against calibration corpora. `avoid-ai-writing`, `clear-prose`, and `concise` each ship a `test-corpus.md`. Part 1 holds passages that should be flagged or cut, with a table of the expected results. Part 2 holds text that sits close to the rules without breaking them, and nothing in Part 2 should be flagged or cut. Run the skill against both parts after changing any rule. A rule that fires on Part 2 needs narrowing, even if it catches real cases in Part 1.

## Contributing

Read `CLAUDE.md` before changing anything. It covers the conventions the validator can't check, in particular:

- **Bump the plugin version in the same commit as any change under `plugins/`**, in both `plugin.json` and `.claude-plugin/marketplace.json`. Claude Code updates plugins by version, so a change without a bump never reaches people who already installed it.
- **Keep skill frontmatter to the six fields claude.ai accepts**: `name`, `description`, `license`, `allowed-tools`, `metadata`, `compatibility`. `make validate` fails on anything else.

New rules need a Part 1 passage and an expected-flags row in the corpus, and they need to leave Part 2 clean.

## Credits

`avoid-ai-writing` draws on Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing), Simon Willison's [LLM cliché highlighter](https://tools.simonwillison.net/llm-cliche-highlighter), and ideas from [blader/humanizer](https://github.com/blader/humanizer), [Aboudjem/humanizer-skill](https://github.com/Aboudjem/humanizer-skill), and [brandonwise/humanizer](https://github.com/brandonwise/humanizer). The rules are written fresh for this project; each one that started from another project's idea credits it where it appears.

`clear-prose` is built on Joseph M. Williams and Joseph Bizup's *Style: The Basics of Clarity and Grace*. It also draws on Zonder Labs' [Why is AI Slop so Frustrating to Read?](https://zonderlabs.com/slop), which found that clarity faults, not vocabulary, are what make AI writing hard to read.

## License

MIT. See [LICENSE](LICENSE).
