import argparse
import time

import brain
import guardrail
from config import (
    DB_FILE,
    LOCAL_INBOX,
    LOCAL_OUTBOX,
    SYSTEM_PROMPT_FILE,
    FirmConfig,
    load_config,
    load_prompt,
)
from deliver import ImapDelivery, LocalDelivery
from intake import ImapIntake, Incoming, LocalIntake
from store import Store

ACK_TEMPLATE = (
    "Thank you for your enquiry — it has reached {firm_name} and a member of the team is "
    "looking at it now. We will come back to you shortly.\n\n"
    "If your situation is time-sensitive, please call us on {firm_phone}."
)


def compose_user_message(incoming: Incoming) -> str:
    lines: list[str] = []
    sender = incoming.sender_name or ""
    if incoming.sender_email:
        sender = f"{sender} <{incoming.sender_email}>".strip()
    if sender:
        lines.append(f"From: {sender}")
    if incoming.subject:
        lines.append(f"Subject: {incoming.subject}")
    if lines:
        lines.append("")
    lines.append(incoming.body)
    return "\n".join(lines)


def canned_ack(config: FirmConfig) -> str:
    return ACK_TEMPLATE.format(firm_name=config.firm_name, firm_phone=config.firm_phone)


def process_one(
    incoming: Incoming,
    store: Store,
    config: FirmConfig,
    system_prompt: str,
    delivery: LocalDelivery | ImapDelivery,
) -> str:
    existing = store.conn.execute(
        "SELECT id, status FROM enquiries WHERE message_id = ?", (incoming.message_id,)
    ).fetchone()
    if existing is not None and existing["status"] != "error":
        return f"skip (already processed as {existing['id']})"
    if existing is not None:
        enquiry_id = existing["id"]
    else:
        enquiry_id = store.new_id()
        store.insert_enquiry(
            enquiry_id,
            incoming.message_id,
            incoming.channel,
            incoming.sender_name,
            incoming.sender_email,
            incoming.subject,
            incoming.body,
            incoming.received_at,
        )
    started = time.monotonic()
    result = brain.run_brain(config.brain, compose_user_message(incoming), system_prompt, config.api_model)
    elapsed = time.monotonic() - started
    error = result.get("error")
    if error:
        store.set_status(enquiry_id, "error")
        store.add_touch(enquiry_id, "brain_error", note=str(error)[:300])
        return f"{enquiry_id} ERROR: {str(error)[:120]}"
    card = result.get("card")
    problems = brain.validate_card(card) if isinstance(card, dict) else ["no JSON card in brain output"]
    if not isinstance(card, dict) or problems:
        reasons = ["brain output failed validation"] + problems
        ack = canned_ack(config)
        draft_ref = delivery.deliver_draft(incoming, ack, config, enquiry_id)
        alert_ref = delivery.deliver_alert(incoming, reasons, config, enquiry_id)
        store.record_result(
            enquiry_id, "en", "unclear", "low", "none", False, True, reasons, [],
            "escalated", ack, incoming.body[:80], "review by a person", elapsed,
        )
        store.add_touch(enquiry_id, "acknowledgment", note=f"canned ack ({draft_ref})", body=ack)
        store.add_touch(enquiry_id, "escalation_alert", note=alert_ref)
        return f"{enquiry_id} ESCALATED (invalid card): {problems[0]}"
    bucket = str(card.get("bucket"))
    escalate = bool(card.get("escalate"))
    draft = card.get("draft") if isinstance(card.get("draft"), str) else None
    log_row = card.get("log_row") if isinstance(card.get("log_row"), dict) else {}
    summary = str(log_row.get("summary", incoming.body[:80]))
    next_action = str(log_row.get("next_action", ""))
    reasons = [str(r) for r in (card.get("escalation_reasons") or [])]
    hits = guardrail.scan(draft)
    hit_texts = [hit.as_text() for hit in hits]
    if hits and not escalate:
        ack = canned_ack(config)
        draft_ref = delivery.deliver_draft(incoming, ack, config, enquiry_id)
        alert_ref = delivery.deliver_alert(
            incoming, ["guardrail blocked the draft"] + hit_texts, config, enquiry_id
        )
        store.record_result(
            enquiry_id, str(card.get("language", "en")), bucket, str(card.get("confidence", "low")),
            str(card.get("stream", "none")), bool(card.get("urgent")), True,
            reasons + ["guardrail block"], hit_texts, "escalated", draft, summary,
            "review the blocked draft", elapsed,
        )
        store.add_touch(enquiry_id, "guardrail_block", note="; ".join(hit_texts), body=draft)
        store.add_touch(enquiry_id, "acknowledgment", note=f"canned ack ({draft_ref})", body=ack)
        store.add_touch(enquiry_id, "escalation_alert", note=alert_ref)
        return f"{enquiry_id} GUARDRAIL BLOCK ({hit_texts[0]})"
    if escalate:
        ack = draft or canned_ack(config)
        ack_hits = guardrail.scan(ack)
        if ack_hits:
            hit_texts = [hit.as_text() for hit in ack_hits]
            ack = canned_ack(config)
        draft_ref = delivery.deliver_draft(incoming, ack, config, enquiry_id)
        alert_ref = delivery.deliver_alert(incoming, reasons or ["escalated by the assistant"], config, enquiry_id)
        store.record_result(
            enquiry_id, str(card.get("language", "en")), bucket, str(card.get("confidence", "low")),
            str(card.get("stream", "none")), bool(card.get("urgent")), True, reasons, hit_texts,
            "escalated", ack, summary, next_action or "a person takes this one", elapsed,
        )
        store.add_touch(enquiry_id, "acknowledgment", note=f"ack draft ({draft_ref})", body=ack)
        store.add_touch(enquiry_id, "escalation_alert", note=alert_ref)
        return f"{enquiry_id} ESCALATED: {', '.join(reasons) or 'no reason given'}"
    if bucket == "not_an_enquiry" or not draft:
        store.record_result(
            enquiry_id, str(card.get("language", "en")), bucket, str(card.get("confidence", "medium")),
            str(card.get("stream", "none")), bool(card.get("urgent")), False, reasons, [],
            "archived", draft, summary, next_action or "none", elapsed,
        )
        return f"{enquiry_id} archived ({bucket})"
    draft_ref = delivery.deliver_draft(incoming, draft, config, enquiry_id)
    store.record_result(
        enquiry_id, str(card.get("language", "en")), bucket, str(card.get("confidence", "medium")),
        str(card.get("stream", "none")), bool(card.get("urgent")), False, reasons, [],
        "awaiting_reply", draft, summary, next_action, elapsed,
    )
    store.add_touch(enquiry_id, "first_reply", note=f"draft ready ({draft_ref})", body=draft)
    return f"{enquiry_id} drafted ({bucket}/{card.get('stream')}) in {elapsed:.0f}s"


def run_pass(
    source: LocalIntake | ImapIntake,
    store: Store,
    config: FirmConfig,
    system_prompt: str,
    delivery: LocalDelivery | ImapDelivery,
    limit: int,
) -> int:
    items = source.fetch()
    if limit:
        items = items[:limit]
    for incoming in items:
        print(f"  {process_one(incoming, store, config, system_prompt, delivery)}", flush=True)
    return len(items)


def main() -> None:
    parser = argparse.ArgumentParser(description="Briska enquiry desk service")
    parser.add_argument("--source", choices=("local", "imap"), default="local")
    parser.add_argument("--deliver", choices=("local", "imap"), default="local")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    config = load_config()
    system_prompt = load_prompt(SYSTEM_PROMPT_FILE, config)
    store = Store(DB_FILE)
    source: LocalIntake | ImapIntake = ImapIntake(config) if args.source == "imap" else LocalIntake(LOCAL_INBOX)
    delivery: LocalDelivery | ImapDelivery = ImapDelivery(config) if args.deliver == "imap" else LocalDelivery(LOCAL_OUTBOX)
    mode = f"source={args.source} deliver={args.deliver} brain={config.brain}"
    if args.watch:
        print(f"Enquiry desk service watching ({mode}), every {config.poll_seconds}s. Ctrl+C to stop.")
        try:
            while True:
                count = run_pass(source, store, config, system_prompt, delivery, args.limit)
                if count:
                    print(f"  processed {count}", flush=True)
                time.sleep(config.poll_seconds)
        except KeyboardInterrupt:
            print("Stopped.")
    else:
        print(f"Enquiry desk service, one pass ({mode}).")
        count = run_pass(source, store, config, system_prompt, delivery, args.limit)
        print(f"Done: {count} enquiries processed." if count else "Nothing new.")
    store.close()


if __name__ == "__main__":
    main()
