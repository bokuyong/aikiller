"""aikiller — 한국어 AI 문체 탐지 + 다듬기 통합 엔진."""

from .detect import analyze, Report
from .humanize import humanize, build_llm_prompt, HumanizeResult
from .patterns import PATTERNS, find_hits, apply_rewrites

__version__ = "0.1.0"
__all__ = [
    "analyze", "Report", "humanize", "build_llm_prompt", "HumanizeResult",
    "PATTERNS", "find_hits", "apply_rewrites", "__version__",
]
