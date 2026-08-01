# Enquiry desk service (the pilot deploy, runnable today)

The architecture.md service, built for real: intake → dedupe → brain → guardrail → draft →
log → report. Stdlib only, no venv, no pip. The brain is an adapter: `cli` runs on the Claude
subscription today, `api` flips to `claude-haiku-4-5` the day a spend-capped key exists. Same
prompt, same contract, one config value.

The prompts load from [../system-prompt.md](../system-prompt.md) and
[../followup-prompt.md](../followup-prompt.md) at startup, placeholders filled from
`firm-config.json`. The service can never drift from the tested prompt; any prompt change
still goes through the full eval sweep first (repo rule).

## Run it

```powershell
$env:PYTHONUTF8 = "1"
python run.py
```

One pass, local mode: reads `.eml`/`.txt` files from `inbox/`, writes reply drafts to
`outbox/drafts/`, escalation alerts to `outbox/escalations/`, log rows to `state/enquiries.db`.
Processed files move to `inbox/processed/`. All three folders are gitignored.

Flags:

- `--watch` — poll forever (every `poll_seconds` from config)
- `--source imap` — poll a real mailbox instead of the folder (needs `mailbox.user` in
  firm-config.json and `IMAP_APP_PASSWORD` in the environment; never put the password in a file)
- `--deliver imap` — IMAP-APPEND drafts into the mailbox's Drafts folder, threaded onto the
  original message, and send escalation alerts to `approver_email` over SMTP
- `--limit N` — cap a pass at N enquiries

The pilot shape is `python run.py --source imap --deliver imap --watch` on a VPS. The demo
shape is local in, local out.

## The guardrail filter

[guardrail.py](guardrail.py) is the deterministic last word: any draft containing verdict
language, a fee amount, or application advice (EN + ZH) is blocked, replaced with the canned
acknowledgment, and escalated with the hits listed. The model never overrides it.

```powershell
python test_guardrail.py
```

39 cases pin the behavior, hedged phrasings ("whether you qualify") included. Any change to
the pattern lists reruns this file first.

## What one enquiry produces

- A row in `state/enquiries.db` (`enquiries` + `touches` tables), deduped by Message-ID; a
  crash mid-run can never draft twice, and brain errors mark the row for retry next pass.
- A reply draft: `.eml` in `outbox/drafts/` (local) or a threaded Gmail draft (imap).
- On escalation: an acknowledgment-only draft plus an alert to the approver with reasons.
- Malformed brain output never reaches the firm: it validates against the workflow.md contract
  and failures escalate with the canned acknowledgment.

## The weekly report

```powershell
python report.py --firm "Sample Firm"
```

Renders `state/weekly-report-YYYY-MM-DD.html` from the log: handled / qualified / drafted /
escalated counts, median time to draft, bucket and stream breakdowns, the escalation list, any
guardrail blocks, the full log table. This is the contractual weekly deliverable from
[spec.md](../spec.md), generated from real rows, not samples.

## Not in here yet

- Follow-up scheduling (day 3/7/14 chases): the prompt and evals exist, the trigger loop is next.
- The v1.1 instant acknowledgment auto-send: a flag on the autonomy ladder, off by design.
- healthchecks.io ping + systemd unit: added when this lands on a VPS.
