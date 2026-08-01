import re
from dataclasses import dataclass

HEDGE_WINDOW = 48

SENTENCE_SPLIT = re.compile(r"[.。!?！？\n]")
HEDGE_TOKENS = re.compile(
    r"\b(?:whether|if|may|might|could|confirm[s]?|check[s]?|assess(?:es)?)\b|是否|能否|可能|或許|或许",
    re.IGNORECASE,
)

VERDICT_PATTERNS = [
    re.compile(r"\byou(?:'re| are| would| will| do| certainly| definitely| clearly)* +(?:definitely |certainly |clearly |likely |very likely )?qualif(?:y|ies)", re.IGNORECASE),
    re.compile(r"\byou (?:do not|don't|won't|will not|cannot|can't) qualify", re.IGNORECASE),
    re.compile(r"\byou(?:'re| are)?(?: definitely| certainly| clearly| likely)?(?: not)? eligible\b", re.IGNORECASE),
    re.compile(r"\byou meet (?:the|all|every) (?:requirement|criteri|threshold)", re.IGNORECASE),
    re.compile(r"\byour application (?:will|would) (?:be approved|succeed|go through|be refused|fail)", re.IGNORECASE),
    re.compile(r"\b(?:guaranteed?|no problem getting|definitely get|will definitely)\b[^.。!?！？\n]{0,40}\b(?:visa|approval|approved|pass|permit)", re.IGNORECASE),
    re.compile(r"\b(?:visa|approval|application|success)\b[^.。!?！？\n]{0,40}\b(?:is |are )?guaranteed\b", re.IGNORECASE),
    re.compile(r"\b100%\s?(?:success|approval|guaranteed)", re.IGNORECASE),
    re.compile(r"(?:你|您)(?:(?!是否|能否|可能)[^。！？\n]){0,12}符合(?:資格|资格|要求|條件|条件)"),
    re.compile(r"(?:一定|肯定|絕對|绝对)(?:可以|能|會獲批|会获批|符合)"),
    re.compile(r"保證(?:獲批|获批|成功|通過|通过)|保证(?:获批|獲批|成功|通過|通过)|包批"),
]

FEE_PATTERNS = [
    re.compile(r"(?:HK\$|HKD|US\$|USD|RMB|CNY|£|€)\s?\d[\d,]*(?:\.\d+)?", re.IGNORECASE),
    re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?"),
    re.compile(r"(?:港幣|港元|人民幣|人民币)\s?\d[\d,]*"),
    re.compile(r"\d[\d,]*\s?(?:港幣|港元|元)"),
    re.compile(r"\bour fees? (?:is|are|start|begin)", re.IGNORECASE),
    re.compile(r"收費是|收费是|費用是|费用是|費用為|费用为"),
]

ADVICE_VERB = r"(?:you should|you ought to|you need to|you must|we advise|i advise|we recommend|i recommend|we suggest|i suggest|my advice|our advice|it would be best to|your best (?:option|route|bet) is to)"
ADVICE_ACTION = r"(?:appl(?:y|ying|ication)|submit|lodge|file|extend|renew|surrender|leave hong kong|exit hong kong|visa run|overstay)"

ADVICE_PATTERNS = [
    re.compile(rf"{ADVICE_VERB}\b[^.。!?！？\n]{{0,60}}\b{ADVICE_ACTION}", re.IGNORECASE),
    re.compile(r"(?:建議|建议|應該|应该|最好)(?:(?!諮詢|咨询|預約|预约)[^。！？\n]){0,20}(?:申請|申请|遞交|递交|續簽|续签|離境|离境)"),
]


@dataclass
class Hit:
    category: str
    match: str

    def as_text(self) -> str:
        return f"{self.category}: “{self.match}”"


def _hedged(draft: str, start: int) -> bool:
    window = draft[max(0, start - HEDGE_WINDOW):start]
    same_sentence = SENTENCE_SPLIT.split(window)[-1]
    return HEDGE_TOKENS.search(same_sentence) is not None


def scan(draft: str | None) -> list[Hit]:
    if not draft:
        return []
    hits: list[Hit] = []
    for pattern in VERDICT_PATTERNS:
        for match in pattern.finditer(draft):
            if not _hedged(draft, match.start()):
                hits.append(Hit("verdict", match.group(0).strip()))
    for pattern in FEE_PATTERNS:
        for match in pattern.finditer(draft):
            hits.append(Hit("fee", match.group(0).strip()))
    for pattern in ADVICE_PATTERNS:
        for match in pattern.finditer(draft):
            hits.append(Hit("advice", match.group(0).strip()))
    return hits
