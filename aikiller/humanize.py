"""AI 티 제거(다듬기) 엔진.

탐지기와 같은 patterns.py 레지스트리를 쓴다. 탐지된 것만 고치고,
탐지되지 않은 구간은 건드리지 않는다.

4대 안전장치
------------
1. 보호 구간   코드블록·인라인코드·직접인용("...")·URL·숫자표는 마스킹 후 복원.
2. risk 등급   safe / moderate / aggressive. 사용자가 고른 등급 이하만 적용.
3. 변경률 게이트  기본 30% 초과 경고, 50% 초과 시 중단(원문 반환).
4. 의미 불변   규칙은 전부 문법적 치환이다. 사실·수치·고유명사를 만들거나 지우지 않는다.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

from . import patterns as P
from .detect import analyze

WARN_CHANGE_RATE = 0.30
ABORT_CHANGE_RATE = 0.50

# 마스킹 대상 — 이 안은 절대 수정하지 않는다.
_PROTECT_PATTERNS = [
    re.compile(r"```.*?```", re.S),            # 펜스 코드블록
    re.compile(r"`[^`\n]+`"),                  # 인라인 코드
    re.compile(r"https?://\S+"),               # URL
    re.compile(r"[\"“][^\"”\n]{2,200}[\"”]"),  # 직접 인용
    re.compile(r"^\s*>.*$", re.M),             # 인용 블록
]

_MASK = "\x00AIK{}\x00"
_MASK_RE = re.compile(r"\x00AIK(\d+)\x00")


def _mask(text: str) -> tuple[str, list[str]]:
    store: list[str] = []

    def _repl(m: re.Match) -> str:
        store.append(m.group(0))
        return _MASK.format(len(store) - 1)

    out = text
    for pat in _PROTECT_PATTERNS:
        out = pat.sub(_repl, out)
    return out, store


def _unmask(text: str, store: list[str]) -> str:
    def _repl(m: re.Match) -> str:
        idx = int(m.group(1))
        return store[idx] if 0 <= idx < len(store) else m.group(0)

    return _MASK_RE.sub(_repl, text)


def change_rate(before: str, after: str) -> float:
    """문자 단위 변경률. 0.0(무변경) ~ 1.0(전면 재작성)."""
    if not before:
        return 0.0
    sm = difflib.SequenceMatcher(None, before, after, autojunk=False)
    return 1.0 - sm.ratio()


@dataclass
class HumanizeResult:
    text: str
    original: str
    changes: list[P.Change]
    change_rate: float
    level: str
    aborted: bool
    warnings: list[str] = field(default_factory=list)
    before_score: float | None = None
    after_score: float | None = None
    before_layers: dict | None = None
    after_layers: dict | None = None

    @property
    def improved(self) -> float | None:
        if self.before_score is None or self.after_score is None:
            return None
        return round(self.before_score - self.after_score, 1)


def humanize(
    text: str,
    level: str = "moderate",
    genre: str = "essay",
    score_before_after: bool = True,
) -> HumanizeResult:
    """규칙 기반 다듬기. LLM 호출 없이 결정적으로 동작한다."""
    original = text
    warnings: list[str] = []

    masked, store = _mask(text)
    rewritten, changes = P.apply_rewrites(masked, max_risk=level)
    # 치환 후 남는 이중 공백·문장부호 앞 공백 정리
    rewritten = re.sub(r"[ \t]{2,}", " ", rewritten)
    rewritten = re.sub(r"\s+([,.!?])", r"\1", rewritten)
    rewritten = re.sub(r"(?m)^[ \t]+$", "", rewritten)
    out = _unmask(rewritten, store)

    rate = change_rate(original, out)
    aborted = False
    if rate > ABORT_CHANGE_RATE:
        warnings.append(
            f"변경률 {rate:.0%}가 중단 임계값 {ABORT_CHANGE_RATE:.0%}를 넘었습니다. "
            "원문을 그대로 반환합니다 — 규칙이 과적용됐을 가능성이 큽니다."
        )
        out, changes, aborted = original, [], True
        rate = 0.0
    elif rate > WARN_CHANGE_RATE:
        warnings.append(f"변경률 {rate:.0%} — 원문 대조를 권장합니다.")

    before_score = after_score = None
    before_layers = after_layers = None
    if score_before_after:
        rb = analyze(original, genre=genre)
        ra = analyze(out, genre=genre)
        before_score, after_score = rb.score, ra.score
        before_layers, after_layers = rb.layers, ra.layers
        # 미피팅 가중치에서는 총점이 시그모이드 상단에 붙어 거의 안 움직인다.
        # 계층별 변화가 실제 개선을 보여 주므로 함께 노출한다.

    return HumanizeResult(
        text=out, original=original, changes=changes, change_rate=round(rate, 4),
        level=level, aborted=aborted, warnings=warnings,
        before_score=before_score, after_score=after_score,
        before_layers=before_layers, after_layers=after_layers,
    )


# ---------------------------------------------------------------------------
# LLM 보조 경로 — 규칙으로 못 고치는 것(리듬·무생물 주어·문단 구조)용
# ---------------------------------------------------------------------------

LLM_SYSTEM = """당신은 한국어 문장 교정자입니다. 주어진 글의 **내용은 한 글자도 바꾸지 말고**
문체·리듬·표현만 자연스러운 한국어로 고치세요.

절대 규칙
1. 사실·수치·고유명사·직접 인용은 100% 보존합니다.
2. 없던 주장을 추가하지 않습니다. 있던 주장을 삭제하지 않습니다.
3. 글의 장르와 경어법(-다/-습니다)을 원문 그대로 유지합니다.
4. 아래 '지적된 구간'만 고칩니다. 지적되지 않은 문장은 그대로 두세요.
5. 결과 텍스트만 출력합니다. 설명·머리말·코드펜스를 붙이지 마세요."""


def build_llm_prompt(text: str, genre: str = "essay", max_signals: int = 12) -> str:
    """탐지 결과를 근거로 LLM 다듬기 프롬프트를 만든다.

    규칙 엔진이 못 고치는 패턴(repl=None)을 우선 지적한다.
    """
    report = analyze(text, genre=genre)
    detect_only = [
        s for s in report.signals
        if s.layer in ("L2", "L3")
        and (s.layer == "L3" or not P.PATTERNS_BY_ID[s.key].rewritable)
    ][:max_signals]

    lines = [
        f"## 진단 (AI 문체 점수 {report.score}/100, 등급 {report.band})",
        "",
        "### 지적된 구간 — 이것만 고치세요",
    ]
    if detect_only:
        for s in detect_only:
            hint = (
                P.PATTERNS_BY_ID[s.key].hint
                if s.layer == "L2" and s.key in P.PATTERNS_BY_ID else s.detail
            )
            lines.append(f"- **{s.label}** ({s.detail})")
            if hint:
                lines.append(f"  - 처방: {hint}")
    else:
        lines.append("- 규칙으로 못 고치는 패턴은 없습니다. 리듬만 다듬으세요.")

    hot = sorted(report.sentences, key=lambda s: -s.score)[:5]
    hot = [s for s in hot if s.score > 30]
    if hot:
        lines += ["", "### 점수가 높은 문장 (우선 손볼 것)"]
        for s in hot:
            lines.append(f"- ({s.score:.0f}점) {s.text.strip()}")

    lines += ["", "### 원문", "", text]
    return "\n".join(lines)
