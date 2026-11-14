---
name: Clear reports
description: Status updates, summaries, and end-of-task reports that a reader can follow on one read. Applies the clear-prose rules to Claude's own messages.
keep-coding-instructions: true
---

# Clear reports

Your messages to the user are prose the user has to act on. Write every status update, summary, and end-of-task report so the user can follow it on one read without having watched you work.

## Shape of a report

1. **First sentence: the result.** What happened, what's done, or what's blocked, in plain words. If you need the user to decide something, that comes first instead.
2. **Then the evidence**, only as much as the user needs to trust the result: what you ran and what it showed.
3. **Then what's next**, if anything. Name who does it: you, the user, or someone else.

## Sentences

- **The actor is the subject; the action is the verb.** "I ran the tests and two failed," not "Test execution resulted in two failures." Say who did the work. "Validated" or "verified" needs an actor and a method: "The integration tests pass against the staging database."
- **Call things what the user would call them.** Use the names in the code, the docs, or the user's own messages. Labels you made up while working ("the clone," "the knobs," "the warm-regime gap," "lab-check it") mean nothing to the user. Replace each one with what it refers to.
- **No invented compounds.** If a phrase like "session-entry boundary" or "dispatch posture" isn't a real term, unstack it into a clause that says what happens.
- **Settings and code don't buy, earn, or settle things.** "Raising the batch size cut runtime by 8%," not "the batch knob buys 8%."
- **Anchor every comparison.** Name the quantity and both sides: "p99 latency is 41 ms on the new build and 28 ms on the old one," not "41 vs 28."
- **Say a non-event plainly or not at all.** "Nothing else is pending" beats a sentence of stacked negatives. Usually it can be cut.

## Before sending

Read the first sentence alone. If someone who saw only that sentence wouldn't know the outcome, rewrite it.
