---
name: concise
description: "Cuts a draft down to what its reader needs. Use when a reply, email, Slack message, GitHub issue, PR description, status update, or memo runs longer than the request it answers, and when asked to 'make this shorter', 'cut this down', 'this is too long', 'trim this', or 'get to the point'. Removes whole sentences and sections the reader didn't need: restated requests, background they already have, the writer's process, rejected alternatives, verification detail, speculation, and summaries. Runs first in writing-pipeline, and sets the length the later passes must not inflate."
---

# Concise

Length is a cost the reader pays. The usual cause of an overlong draft isn't wordy sentences. The writer knows fifty things and puts in forty of them, when the reader asked one question and needed three facts to act on the answer.

This skill cuts content, not grammar. It removes whole sentences, paragraphs, and sections. What remains stays in complete, ordinary sentences. Squeezing the survivors into fragments ("Fixed. Tests pass. Shipping Friday.") trades one machine tell for another.

## How to run it

**1. Name the reader and their question.** Who reads this, and what did they ask or need to know? A teammate asking "is there an ETA?" needs the ETA. A reviewer opening a PR needs to know what changed and how to check it. A support team getting a policy memo needs what changes, for whom, and from when. Write the question down in a few words before cutting anything.

**2. Make the first sentence answer it.** If the answer is in the third paragraph, move it up. For a reply, the answer is the reply; everything after it has to pass step 3.

**3. Keep a sentence only if the reader would miss it.** For each sentence after the answer, ask: if this were gone, would the reader act differently, believe something wrong, or have to come back and ask? If not, cut it. Material that passes this test includes what the reader has to do, when something will happen, what changed for them, and a reason when the reader will be asked to accept a cost.

**4. Match the length to the request.** A one-line question gets a few lines back. A quick email reply fits in two or three sentences. A bug report holds the problem, how to reproduce it, and expected versus actual behavior. Add the cause only if it's known. When the draft is several times longer than the request that prompted it, that's the signal to cut harder.

## What to cut

These are the usual sources of extra length. Each is a candidate; step 3 decides.

- **The request, restated.** "Thanks for reaching out about rescheduling our 1:1." The reader knows what they asked.
- **Background the reader already has.** Explaining to the reporting team what the reporting module does.
- **The writer's process.** What you tried, in what order, and what you looked at along the way. The reader needs where things stand.
- **Alternatives you considered and rejected.** Keep one only if the reader is likely to suggest it.
- **Verification detail.** Test counts, benchmark numbers, which edge cases you checked. Keep these when the reader is reviewing the work. Cut them when the reader just needs to know it works.
- **Speculation.** "It may be related to several factors" adds nothing. Either say what's known or say the cause isn't known yet.
- **Summaries of what was just said.** "To summarize," and any closing paragraph that restates the opening.
- **Structure a short message doesn't need.** Headers, bold labels, and bullet lists on something that would be three sentences of prose. A five-sentence Slack reply doesn't need a "Root cause" heading.
- **Stacked courtesies.** One friendly opener or closer is human. Three in a row ("Thanks so much! I completely understand. Happy to be flexible!") is padding.

## What to keep

- **Anything the reader has to act on.** When a cut reply loses "I'll move the invite," the reader no longer knows who's doing it. Cutting must never drop an action, a date, an owner, or a decision.
- **Detail when the detail is the job.** An incident write-up, a spec, a reference doc, or a PR description for a reviewer exists to carry specifics. The test in step 3 still applies, but most sentences in those documents pass it.
- **A definition the reader needs.** If a term survived the cut and the reader won't know it, it gets defined. The cut comes first, so only the terms that matter get defined.
- **A post or essay about how something was done.** There, the process is the content.
- **Complete sentences.** Keep each surviving sentence whole.

## Output

Return the cut version and a short list of what you removed, by category ("removed the restated request, the debugging steps, and the test results"), so the author can restore anything they wanted. If the draft is already the right length, say so and change nothing.

## Where this sits

`writing-pipeline` runs this first, before `cold-reader-docs`, `clear-prose`, and `avoid-ai-writing`. There's no point clarifying a sentence that's about to be cut.

The later passes add words: the cold-reader pass defines terms and the clarity pass unpacks compressed phrases. Both are needed, and together they can turn a 40-word reply into a 200-word one. The length after this pass is the budget. Later passes can spend a little of it on definitions and plain wording. They don't bring back material this pass removed.

`test-corpus.md` in this directory is the regression fixture: Part 1 should be cut, Part 2 should come back essentially unchanged.
