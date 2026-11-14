# Calibration corpus

Fixture for `concise`. Run the skill against each passage and compare against the expected table. Part 1 should come back substantially shorter with nothing the reader needs lost. Part 2 should come back essentially unchanged.

Each passage says who it's for and what prompted it, because length can only be judged against the request.

## Part 1 — should be cut

**1.** Reply to Marcus, who emailed: "Could you review my launch plan by Wednesday?"

> Hi Marcus,
>
> Thank you for sending over the launch plan and for thinking of me as a reviewer. I know how much work goes into a document like this, and I'm glad to help however I can.
>
> I've checked my schedule for the week, and I'll be able to review the plan by Wednesday as you requested. I'll plan to read through it carefully and leave my comments directly in the document so they're easy to find.
>
> In short: yes, I can have my review done by Wednesday. If you need it any sooner, or if there's a particular section you'd like me to focus on, just let me know and I'll do my best to accommodate.
>
> Best,
> Jo

**2.** Slack reply to a teammate who asked: "Is staging unblocked yet?"

> So I dug into this for most of the morning. First I checked whether the deploy pipeline itself was healthy, and it was. Then I looked at the staging database and noticed the migration lock from Friday's failed deploy was never released. I tried releasing it through the admin tool, but that timed out, so I connected directly and cleared the lock row by hand. After that I re-ran the stuck migration, which completed in about four minutes, and then redeployed the current main branch. Everything came up healthy and the smoke tests pass. So yes, staging is unblocked now. Let me know if you see anything weird!

**3.** GitHub issue for the team's tracker.

> **Summary**
> This ticket covers an issue with password reset emails.
>
> **Background**
> Password reset emails are sent when a user clicks "Forgot password" on the login page. They are an important part of account recovery.
>
> **Problem**
> Password reset emails sent to Outlook.com addresses arrive 20 to 40 minutes late. Gmail and other providers receive them within seconds.
>
> **Steps to reproduce**
> 1. Request a password reset for an Outlook.com address.
> 2. Note the time the email arrives.
>
> **Expected:** the email arrives within a minute.
> **Actual:** it arrives 20 to 40 minutes later.
>
> **Possible causes**
> This could be caused by a number of factors, including sender reputation, rate limiting on Microsoft's side, our email provider's routing, or DNS configuration. More investigation is needed.
>
> **Impact**
> Users with Outlook.com addresses may have a frustrating experience when trying to reset their passwords.
>
> **Next steps**
> Investigate and fix.

**4.** Memo to all staff from the office manager.

> Subject: Update regarding office access
>
> Hi everyone,
>
> The purpose of this memo is to share an important update about office access that will affect everyone who works from the office.
>
> As many of you know, we've been reviewing our building security procedures over the past few months as part of an ongoing effort to keep everyone safe. As a result of that review, we've decided to make a change.
>
> Starting March 3, the front door will require a badge at all hours, not just after 6pm. If you don't have a badge yet, pick one up from the front desk before then.
>
> To summarize, badges will be required at the front door at all times starting March 3, so please make sure you have yours.
>
> Thanks for your cooperation and understanding!

**5.** Reply to a colleague who asked in chat: "Which region is the new cache cluster in?"

> ## Answer
> The new cache cluster is in **us-east-2**.
>
> ## Details
> - It was provisioned last Tuesday.
> - It replaces the old cluster in us-east-1.
>
> ## Notes
> Let me know if you have other questions about the cluster setup.

### Expected results

| Passage | Should keep | Should cut |
|---|---|---|
| 1 | Yes, by Wednesday; comments in the doc | the thanks paragraph, the restated request, the "in short" summary, the stacked offers |
| 2 | Yes, unblocked; one clause on what was wrong (a stale migration lock) if anything | the morning's step-by-step debugging |
| 3 | problem, repro, expected/actual; "cause not known yet" | Summary, Background, the list of possible causes, Impact, Next steps |
| 4 | badge required at all hours from March 3; pick one up at the front desk | the purpose statement, the review backstory, the summary, the stacked thanks |
| 5 | us-east-2 | the headers and bullets; the provisioning date and the old cluster unless asked |

Cutting must never drop an action, a date, an owner, or a decision. A result that loses "comments in the doc," "March 3," or "front desk" is a failure even if it's shorter.

## Part 2 — should not be cut

Nothing below should lose more than a word or two. Each passage is already the length its reader needs.

**6.** Reply to the email in passage 1.

> Yes, I'll have comments in the doc by Wednesday.

**7.** Section of an incident write-up for the engineering org.

> Checkout failed for 18% of orders between 09:12 and 09:47 UTC. The 09:10 release changed the tax service client to retry on every 5xx, and the tax service was already shedding load from a partner's batch job, so retries multiplied its traffic about fourfold and it stopped responding. Orders whose tax lookup failed were rejected at payment. We rolled back at 09:44 and checkout recovered by 09:47. The client now retries only on connection errors, with a cap of two, and the tax service has a per-caller rate limit so one client can't take it down for everyone.

**8.** PR description for the reviewers of a change to invoice rounding.

> Rounds each line item to the cent before summing, instead of rounding the total. Fixes invoices that were off by a cent when they had three or more discounted lines.
>
> To check: `make test` covers it. `test_invoice_rounding` has the three cases from the bug report, all of which failed before this change. I also re-ran last month's 41,000 invoices through both versions; 312 totals change, all by one cent, and every changed one matches what the customer's card was actually charged.

**9.** Issue for a tracker read by the whole company, including support and finance.

> The dunning job (the nightly task that emails customers whose payment failed) sent no emails on May 9 or 10. About 140 customers with failed payments weren't notified and may lose service on the 15th without warning. To reproduce: filter failed payments for May 9–10 and check "last reminder sent." Expected: a date. Actual: empty.

**10.** Reply to a teammate who asked: "Can you take the Friday on-call shift?"

> Sure, I'll take it. Thanks for asking early.

### False-positive traps in Part 2

- An already-short reply (6). Compressing it further into "Yes, Wed." is a failure.
- Dense, necessary detail where every sentence carries a fact the reader uses (7).
- Verification detail kept because the reader is a reviewer (8).
- A definition the reader needs, in a short issue (9).
- One friendly line in a short reply (10). One courtesy isn't padding.
