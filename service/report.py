import argparse
import html
import json
import sqlite3
import statistics
from datetime import datetime, timedelta
from pathlib import Path

from config import DB_FILE
from store import Store

BUCKET_LABELS = {
    "qualified": "Qualified",
    "unclear": "Unclear",
    "no_fit": "No fit",
    "existing_client": "Existing client",
    "not_an_enquiry": "Not an enquiry",
}

STREAM_LABELS = {
    "ttps_a": "TTPS Cat A",
    "ttps_bc": "TTPS Cat B/C",
    "qmas": "QMAS",
    "gep": "Employment (GEP)",
    "dependant": "Dependant",
    "other": "Other",
    "none": "—",
}

STATUS_LABELS = {
    "awaiting_reply": "Awaiting reply",
    "escalated": "Escalated",
    "archived": "Archived",
    "error": "Retrying",
}

PAGE_TOP = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Weekly enquiry report — {firm}</title>
<style>
  :root {{
    --bg:#09090b; --bg-2:#18181b; --border:#27272a; --text:#e4e4e7; --text-2:#a1a1aa;
    --text-3:#71717a; --emerald:#10b981; --amber:#f59e0b; --red:#f87171; --sky:#38bdf8;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    font-size:16px; line-height:1.6; }}
  .wrap {{ max-width:920px; margin:0 auto; padding:40px 24px 80px; }}
  h1 {{ font-size:1.7rem; margin:0 0 4px; letter-spacing:-0.02em; }}
  h2 {{ font-size:1.15rem; margin:38px 0 14px; }}
  .sub {{ color:var(--text-2); margin:0 0 8px; }}
  .badge {{ display:inline-block; font-size:0.72rem; font-weight:600; letter-spacing:0.08em;
    text-transform:uppercase; color:var(--emerald); border:1px solid var(--emerald);
    border-radius:999px; padding:3px 12px; margin-bottom:18px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:22px 0; }}
  .card {{ border:1px solid var(--border); background:var(--bg-2); border-radius:12px; padding:16px 18px; }}
  .card .n {{ font-size:1.9rem; font-weight:700; line-height:1.1; }}
  .card .l {{ font-size:0.8rem; color:var(--text-3); margin-top:4px; }}
  .card.green .n {{ color:var(--emerald); }}
  .card.amber .n {{ color:var(--amber); }}
  .card.red .n {{ color:var(--red); }}
  .card.sky .n {{ color:var(--sky); }}
  table {{ width:100%; border-collapse:collapse; font-size:0.88rem; }}
  th, td {{ text-align:left; padding:9px 10px; border-bottom:1px solid var(--border); vertical-align:top; }}
  th {{ color:var(--text-3); font-size:0.7rem; text-transform:uppercase; letter-spacing:0.06em; }}
  tr:last-child td {{ border-bottom:none; }}
  .pill {{ display:inline-block; font-size:0.7rem; font-weight:600; padding:2px 9px;
    border-radius:999px; border:1px solid var(--border); color:var(--text-2); white-space:nowrap; }}
  .pill.esc {{ color:var(--red); border-color:var(--red); }}
  .pill.wait {{ color:var(--sky); border-color:var(--sky); }}
  .pill.arch {{ color:var(--text-3); }}
  .muted {{ color:var(--text-3); }}
  .scroll {{ overflow-x:auto; border:1px solid var(--border); border-radius:12px; background:var(--bg-2); }}
  .scroll table {{ min-width:680px; }}
  .foot {{ margin-top:40px; color:var(--text-3); font-size:0.8rem; border-top:1px solid var(--border); padding-top:16px; }}
</style>
</head>
<body>
<div class="wrap">
<span class="badge">Generated from the live enquiry log</span>
<h1>Weekly enquiry report</h1>
<p class="sub">{firm} · {start} to {end} · prepared by the Briska enquiry desk</p>
"""

PAGE_BOTTOM = """<div class="foot">Every number on this page is a query over the enquiry log
(SQLite on the service box). Raw enquiry text is purged after 30 days; the log keeps summaries,
buckets, timestamps and outcomes. Generated {generated}.</div>
</div>
</body>
</html>
"""


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def fmt_minutes(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    return "<1 min" if seconds < 60 else f"{seconds / 60:.0f} min"


def count_rows(rows: list[sqlite3.Row], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = str(row[key] or "—")
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def breakdown_table(counts: dict[str, int], labels: dict[str, str], total: int) -> str:
    lines = ["<table><tr><th>Category</th><th>Count</th><th>Share</th></tr>"]
    for key, count in counts.items():
        share = f"{100 * count / total:.0f}%" if total else "0%"
        lines.append(f"<tr><td>{esc(labels.get(key, key))}</td><td>{count}</td><td class='muted'>{share}</td></tr>")
    lines.append("</table>")
    return "\n".join(lines)


def render(store: Store, days: int, firm: str) -> str:
    end = datetime.now()
    start = end - timedelta(days=days)
    rows = store.enquiries_since(start.isoformat(timespec="seconds"))
    processed = [r for r in rows if r["status"] != "error"]
    real_enquiries = [r for r in processed if r["bucket"] != "not_an_enquiry"]
    escalated = [r for r in processed if r["status"] == "escalated"]
    drafted = [r for r in processed if r["draft"]]
    qualified = [r for r in processed if r["bucket"] == "qualified"]
    blocked = [r for r in processed if json.loads(r["guardrail_hits"] or "[]")]
    response_times = [r["response_seconds"] for r in drafted if r["response_seconds"] is not None]
    median_response = statistics.median(response_times) if response_times else None

    parts = [PAGE_TOP.format(firm=esc(firm), start=start.strftime("%d %b"), end=end.strftime("%d %b %Y"))]
    parts.append('<div class="cards">')
    parts.append(f'<div class="card"><div class="n">{len(processed)}</div><div class="l">Enquiries handled</div></div>')
    parts.append(f'<div class="card green"><div class="n">{len(qualified)}</div><div class="l">Qualified leads</div></div>')
    parts.append(f'<div class="card sky"><div class="n">{len(drafted)}</div><div class="l">Replies drafted</div></div>')
    parts.append(f'<div class="card amber"><div class="n">{len(escalated)}</div><div class="l">Routed to a person</div></div>')
    parts.append(f'<div class="card green"><div class="n">{fmt_minutes(median_response)}</div><div class="l">Median time to draft</div></div>')
    parts.append("</div>")

    if real_enquiries:
        parts.append("<h2>Where enquiries landed</h2>")
        parts.append(breakdown_table(count_rows(processed, "bucket"), BUCKET_LABELS, len(processed)))
        parts.append("<h2>Visa streams</h2>")
        parts.append(breakdown_table(count_rows(real_enquiries, "stream"), STREAM_LABELS, len(real_enquiries)))

    if escalated:
        parts.append("<h2>Escalations — each one reached a person</h2>")
        parts.append('<div class="scroll"><table><tr><th>When</th><th>From</th><th>Why</th><th>Summary</th></tr>')
        for row in escalated:
            reasons = ", ".join(json.loads(row["escalation_reasons"] or "[]")) or "—"
            sender = row["sender_name"] or row["sender_email"] or "—"
            parts.append(
                f"<tr><td class='muted'>{esc(str(row['received_at'])[5:16])}</td>"
                f"<td>{esc(sender)}</td><td>{esc(reasons)}</td><td>{esc(row['summary'])}</td></tr>"
            )
        parts.append("</table></div>")

    if blocked:
        parts.append("<h2>Guardrail blocks — drafts stopped before anyone saw them</h2>")
        parts.append("<table><tr><th>When</th><th>What was blocked</th></tr>")
        for row in blocked:
            hits = "; ".join(json.loads(row["guardrail_hits"] or "[]"))
            parts.append(f"<tr><td class='muted'>{esc(str(row['received_at'])[5:16])}</td><td>{esc(hits)}</td></tr>")
        parts.append("</table>")

    parts.append("<h2>The full log</h2>")
    parts.append('<div class="scroll"><table><tr><th>When</th><th>From</th><th>Bucket</th><th>Stream</th><th>Status</th><th>Next action</th></tr>')
    for row in processed:
        status = str(row["status"])
        pill = "esc" if status == "escalated" else ("wait" if status == "awaiting_reply" else "arch")
        sender = row["sender_name"] or row["sender_email"] or "—"
        parts.append(
            f"<tr><td class='muted'>{esc(str(row['received_at'])[5:16])}</td><td>{esc(sender)}</td>"
            f"<td>{esc(BUCKET_LABELS.get(str(row['bucket']), row['bucket']))}</td>"
            f"<td>{esc(STREAM_LABELS.get(str(row['stream']), row['stream']))}</td>"
            f"<td><span class='pill {pill}'>{esc(STATUS_LABELS.get(status, status))}</span></td>"
            f"<td class='muted'>{esc(row['next_action'] or '—')}</td></tr>"
        )
    parts.append("</table></div>")
    parts.append(PAGE_BOTTOM.format(generated=end.strftime("%d %b %Y, %H:%M")))
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Weekly digest from the enquiry log")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--firm", default="[Firm]")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    store = Store(DB_FILE)
    page = render(store, args.days, args.firm)
    out = Path(args.out) if args.out else DB_FILE.parent / f"weekly-report-{datetime.now().strftime('%Y-%m-%d')}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    store.close()
    print(f"Report written: {out}")


if __name__ == "__main__":
    main()
