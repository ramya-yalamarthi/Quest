# Demo Story: Capacity Planning / Quota Increase Workflow

A walkthrough script for demoing the **Suggested Workflow** feature without
implying anything was auto-executed.

## Setup

A P2 case comes in: *"Pods stuck pending — NodePool quota exhausted, need
capacity increase."* The AI pipeline classifies it under Provisioning /
scheduling and routes it to the on-call specialist.

## What the AI note shows

1. **AI INSIGHTS — SUPPORT ANALYSIS** — composite confidence with the
   evidence/routing/diagnosis/recommendation breakdown.
2. **TEAM ASSIGNMENT** — the assigned engineer, why they were picked
   (specialty match, shift/on-call availability), and their track record
   (tickets solved, avg resolution time).
3. **DIAGNOSIS** — probable cause ("NodePool quota exhausted") grounded in
   similar resolved tickets.
4. **RECOMMENDATION** — hot fix / ultimate fix steps.
5. **SUGGESTED WORKFLOW — NOT executed — requires manager approval**:
   *"Increase NodePool/instance-type quota or capacity allocation."*

## The point to make live

Walk through point 5 specifically and call out the **"NOT executed"** label.
The AI flags *that* a capacity/quota change would likely resolve this — it
does not call any API, does not change any quota, and does not touch
Dataverse. The only state change so far is the note itself.

A manager reviewing the case sees the suggestion, agrees it's warranted, and
approves it through whatever change-management process already exists
(ticket comment, Slack approval, a real Power Automate "approve and execute"
flow if one gets built later). The AI's job here is triage and recommendation,
not unattended infrastructure changes.

## Why this matters for the audience

- It directly answers the "are we letting an AI touch production capacity?"
  question before anyone asks it — the answer is no, not yet, and the UI
  makes that explicit every time.
- It sets up the natural next milestone: a real Power Automate flow that
  takes manager approval and performs the quota change, with the orchestrator
  only ever proposing, never executing. That's a deliberate, separate piece
  of work — not something to wire up silently.

## What NOT to claim in the demo

- Don't say "the AI increased the quota" — it suggested it.
- Don't demo this against a real production NodePool; use a test/staging case
  so nobody mistakes the suggestion for an action.
