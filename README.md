# Briska enquiry desk

An AI enquiry desk for Hong Kong immigration firms: it answers, qualifies and books the
enquiries a firm receives, in minutes, in the enquirer's language, with a human approving
everything before it goes out. This repo is the working system behind [briska.ai](https://briska.ai),
minus the client-specific configuration.

**Live demo:** the hosted version lets you type an enquiry and watch the triage, the draft
and the safety filter work in real time. Link on [briska.ai](https://briska.ai).

## Why this exists

Small immigration firms lose enquiries to slow replies: the market norm is a day or two, and
leads go cold in hours. An AI assistant can answer in minutes, but a licensed firm cannot let
a language model freestyle in writing. It must never call eligibility, quote a fee, or give
application advice in a first reply. The engineering problem is holding both of those at once.

## The pipeline

```
 enquiry (email / form / WhatsApp / WeChat)
    │
    ▼
 BRAIN — one model call (claude-haiku-4-5)
 returns a fixed JSON contract: bucket, stream,
 urgency, language, escalation flags, draft reply
    │            invalid JSON → safe acknowledgment + escalate
    ▼
 GUARDRAIL — deterministic, no AI
 regex + phrase rules for verdicts, fees and advice,
 English and Chinese, with hedging detection
    │            any hit → block draft, swap in canned
    │            acknowledgment, escalate to a person
    ▼
 HUMAN — drafts wait for approval; sensitive cases
 (overstay, complaints, deadlines...) skip the queue
    │
    ▼
 LOG + REPORT — SQLite log, weekly one-page report
```

The design rule behind everything: **the model never gets the last word.** The final check on
every draft is plain pattern matching that no prompt injection can talk its way past. And every
failure mode degrades to the same safe floor: a polite holding reply and a human taking over.

## What's in here

| Path | What |
| --- | --- |
| `service/` | The production pipeline: mailbox intake, dedupe, brain, guardrail, drafting, SQLite log, weekly report. Stdlib only. |
| `api/` + the HTML pages | The hosted demo: static pages plus two serverless functions running the same prompts and the same guardrail. |
| `prompts/` | The system prompt and follow-up prompt, placeholders unfilled. |
| `evals/` | The 26-case triage suite, the 8-case follow-up suite, and the full scorecard of every run, fails included. |
| `service/test_guardrail.py` | 39 pinned tests on the safety filter, hedged phrasings in English and Chinese included. |
| `tests/` | Pipeline smoke tests (mock brain, zero API calls). Run in CI. |

## The testing discipline

No prompt version ships without a full scored sweep: all 26 triage cases plus the 8 follow-up
cases, graded against a written rubric with zero tolerance on missed escalations. One missed
escalation fails the run.

[`evals/scorecard.md`](evals/scorecard.md) is the honest history: run 8 includes a hard fail
(a boundary case where the model dropped the JSON contract and gave direct immigration advice)
and the fix that followed. The guardrail exists precisely because that class of failure is a
when, not an if.

## Run it locally

Python 3.10+, no dependencies.

```
python dev.py --mock
```

Opens the demo on http://127.0.0.1:8765 with a canned brain: every flow works, including a
draft that trips the guardrail, with zero API calls. For live drafting:

```
set ANTHROPIC_API_KEY=sk-ant-...   # spend-capped key
python dev.py
```

Guardrail tests: `python service/test_guardrail.py`. Smoke tests: `python tests/smoke.py`.

## Deploy

The repo root is a Vercel project: static pages plus Python functions in `api/`. Set
`ANTHROPIC_API_KEY` (required), `DEMO_KEY` (optional access gate) and `DEMO_MODEL` (optional,
defaults to `claude-haiku-4-5`) as environment variables. The demo backend is stateless and
stores nothing: visitor-typed enquiries live in the visitor's own browser storage.

Abuse limits are built in: input length cap, per-IP and global rate limits, and the spend cap
on the key as the backstop.

## What this is and isn't

This is a working pilot system with one vertical worked end to end, built solo alongside a
consulting day job. It is deliberately boring where boring wins: stdlib Python, SQLite, one
model call per enquiry, no framework. The interesting parts are the control layer: the output
contract, the deterministic guardrail, the escalation ladder and the eval gate.

Built by [Jules Le Breton](https://www.linkedin.com/in/jules-le-breton/) ·
[briska.ai](https://briska.ai)
