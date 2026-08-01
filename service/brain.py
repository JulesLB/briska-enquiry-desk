import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

CLI_TIMEOUT_SECONDS = 180
API_TIMEOUT_SECONDS = 60
API_URL = "https://api.anthropic.com/v1/messages"

BUCKETS = {"qualified", "unclear", "no_fit", "existing_client", "not_an_enquiry"}
STREAMS = {"ttps_a", "ttps_bc", "qmas", "gep", "dependant", "other", "none"}
CONFIDENCES = {"high", "medium", "low"}
LANGUAGES = {"en", "zh-hans", "zh-hant"}


def strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*\n", "", stripped)
        stripped = re.sub(r"\n```\s*$", "", stripped)
    return stripped.strip()


def first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_card(result_text: str) -> dict[str, object] | None:
    fenced = re.search(r"```(?:json)?\s*\n(.*?)\n```", result_text, re.DOTALL)
    candidates = [strip_fences(result_text)]
    if fenced:
        candidates.append(fenced.group(1))
    obj = first_json_object(result_text)
    if obj:
        candidates.append(obj)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def validate_card(card: dict[str, object]) -> list[str]:
    problems: list[str] = []
    if str(card.get("bucket")) not in BUCKETS:
        problems.append(f"bad bucket: {card.get('bucket')!r}")
    if str(card.get("confidence")) not in CONFIDENCES:
        problems.append(f"bad confidence: {card.get('confidence')!r}")
    if str(card.get("stream")) not in STREAMS:
        problems.append(f"bad stream: {card.get('stream')!r}")
    if str(card.get("language")) not in LANGUAGES:
        problems.append(f"bad language: {card.get('language')!r}")
    if not isinstance(card.get("escalate"), bool):
        problems.append("escalate is not a bool")
    if not isinstance(card.get("urgent"), bool):
        problems.append("urgent is not a bool")
    draft = card.get("draft")
    if draft is not None and not isinstance(draft, str):
        problems.append("draft is neither string nor null")
    log_row = card.get("log_row")
    if not isinstance(log_row, dict):
        problems.append("log_row missing")
    return problems


def resolve_claude() -> str | None:
    override = os.environ.get("CLAUDE_BIN")
    if override:
        candidate = Path(override.strip().strip('"'))
        if candidate.exists():
            return str(candidate)
        return shutil.which(override)
    return shutil.which("claude")


def claude_command() -> list[str]:
    path = resolve_claude()
    if path is None:
        raise FileNotFoundError("Claude Code CLI not found on PATH and CLAUDE_BIN not set")
    if path.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", path]
    if path.lower().endswith(".ps1"):
        return ["powershell", "-ExecutionPolicy", "Bypass", "-File", path]
    return [path]


def run_cli(user_message: str, system_prompt: str) -> dict[str, object]:
    try:
        base = claude_command()
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    cmd = base + ["-p", user_message, "--append-system-prompt", system_prompt, "--output-format", "json"]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=CLI_TIMEOUT_SECONDS,
            cwd=Path.home(),
        )
    except subprocess.TimeoutExpired:
        return {"error": f"brain timed out after {CLI_TIMEOUT_SECONDS}s"}
    if completed.returncode != 0:
        try:
            outer = json.loads(completed.stdout)
            detail = str(outer.get("result", "")) or completed.stdout
        except json.JSONDecodeError:
            detail = completed.stderr or completed.stdout
        return {"error": detail.strip()[:2000]}
    try:
        outer = json.loads(completed.stdout)
        result_text = str(outer.get("result", ""))
    except json.JSONDecodeError:
        result_text = completed.stdout
    card = parse_card(result_text)
    if card is None:
        return {"raw": result_text.strip()}
    return {"card": card}


def run_api(user_message: str, system_prompt: str, model: str) -> dict[str, object]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY is not set; use brain 'cli' or set the key"}
    payload = {
        "model": model,
        "max_tokens": 1500,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        return {"error": f"API {exc.code}: {detail}"}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"error": f"API unreachable: {exc}"}
    blocks = body.get("content", [])
    result_text = "".join(str(b.get("text", "")) for b in blocks if b.get("type") == "text")
    card = parse_card(result_text)
    if card is None:
        return {"raw": result_text.strip()}
    return {"card": card}


def run_brain(kind: str, user_message: str, system_prompt: str, api_model: str) -> dict[str, object]:
    if kind == "api":
        return run_api(user_message, system_prompt, api_model)
    return run_cli(user_message, system_prompt)
