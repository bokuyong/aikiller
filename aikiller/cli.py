"""aikiller CLI — 탐지 · 다듬기 · LLM 프롬프트 생성."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from dataclasses import asdict

from . import parsers
from .detect import analyze, Report
from .humanize import humanize, build_llm_prompt

_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _COLOR else s


DIM, BOLD = "2", "1"
RED, YELLOW, GREEN, CYAN = "31", "33", "32", "36"

_BAND_COLOR = {"high": RED, "medium": YELLOW, "low": GREEN}
_BAND_LABEL = {"high": "높음", "medium": "중간", "low": "낮음"}
_CONF_LABEL = {
    "insufficient": "판정 불가", "low": "낮음", "normal": "보통",
}


def _read_input(path: str) -> str:
    if path == "-":
        return parsers.normalize(sys.stdin.read())
    if not os.path.exists(path):
        # 경로가 아니면 텍스트 자체로 취급
        return parsers.normalize(path)
    return parsers.parse_file(path)


def _bar(value: float, width: int = 28) -> str:
    filled = int(round(value / 100 * width))
    return "█" * filled + "·" * (width - filled)


def _print_report(r: Report, show_sentences: bool) -> None:
    color = _BAND_COLOR.get(r.band, CYAN)
    print()
    print(f"  {_c(BOLD, 'AI 문체 점수')}  {_c(color, f'{r.score:>5.1f}')} / 100   "
          f"{_c(color, _BAND_LABEL.get(r.band, r.band))}")
    print(f"  {_c(DIM, _bar(r.score))}")
    conf = _CONF_LABEL.get(r.confidence, r.confidence)
    meta = f"{r.n_chars}자 · {r.n_sentences}문장 · 장르 {r.genre} · 신뢰도 {conf}"
    print(f"  {_c(DIM, meta)}")

    if r.confidence == "insufficient":
        print()
        for n in r.notes:
            print(f"  {_c(YELLOW, '!')} {n}")
        return

    print()
    print(f"  {_c(BOLD, '근거')}")
    if not r.signals:
        print(f"  {_c(DIM, '유의미한 AI 문체 신호가 없습니다.')}")
    for s in r.signals[:10]:
        tag = _c(GREEN, "실측") if s.calibrated else _c(DIM, "추정")
        mark = "●" if s.strength > 0.66 else ("◐" if s.strength > 0.33 else "○")
        print(f"   {mark} [{s.layer}/{tag}] {s.label}")
        print(f"       {_c(DIM, s.detail)}")

    if show_sentences:
        hot = [s for s in r.sentences if s.score > 25]
        if hot:
            print()
            print(f"  {_c(BOLD, '문장별 하이라이트')} {_c(DIM, '(25점 초과)')}")
            for s in sorted(hot, key=lambda x: -x.score)[:12]:
                col = RED if s.score > 60 else YELLOW
                ids = ",".join(dict.fromkeys(s.hit_ids))
                body = s.text.strip()
                if len(body) > 70:
                    body = body[:70] + "…"
                print(f"   {_c(col, f'{s.score:>5.1f}')}  {body}")
                if ids:
                    print(f"          {_c(DIM, ids)}")

    print()
    print(f"  {_c(BOLD, '계층')}  "
          f"L1 캘리브레이션 z={r.layers['l1_calibrated_z']:+.2f}  ·  "
          f"L2 패턴밀도={r.layers['l2_pattern_density']:.2f}  ·  "
          f"L3 리듬={r.layers['l3_rhythm']:.2f}")
    print()
    for n in r.notes:
        print(f"  {_c(YELLOW, '!')} {_c(DIM, n)}")
    print()


def cmd_detect(args: argparse.Namespace) -> int:
    text = _read_input(args.input)
    r = analyze(text, genre=args.genre)
    if args.json:
        print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_report(r, show_sentences=not args.no_sentences)
    return 0


def cmd_humanize(args: argparse.Namespace) -> int:
    text = _read_input(args.input)
    res = humanize(text, level=args.level, genre=args.genre)

    if args.json:
        print(json.dumps({
            "text": res.text, "level": res.level,
            "change_rate": res.change_rate, "aborted": res.aborted,
            "before_score": res.before_score, "after_score": res.after_score,
            "improved": res.improved,
            "changes": [asdict(c) for c in res.changes],
            "warnings": res.warnings,
        }, ensure_ascii=False, indent=2))
        return 0

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(res.text)

    if args.diff:
        print()
        diff = difflib.unified_diff(
            res.original.split("\n"), res.text.split("\n"),
            fromfile="원문", tofile="다듬기", lineterm="", n=1,
        )
        for line in diff:
            if line.startswith("+") and not line.startswith("+++"):
                print(_c(GREEN, line))
            elif line.startswith("-") and not line.startswith("---"):
                print(_c(RED, line))
            elif line.startswith("@@"):
                print(_c(CYAN, line))
            else:
                print(_c(DIM, line))
    elif not args.output:
        print()
        print(res.text)

    print()
    imp = res.improved
    imp_s = f"  개선 {_c(GREEN, f'-{imp}')}" if imp and imp > 0 else ""
    print(f"  {_c(DIM, '강도')} {res.level}  ·  "
          f"{_c(DIM, '변경률')} {res.change_rate:.1%}  ·  "
          f"{_c(DIM, '점수')} {res.before_score} → {res.after_score}{imp_s}")
    if res.before_layers and res.after_layers:
        print()
        print(f"  {_c(BOLD, '계층별 변화')}")
        for key, label in (
            ("l1_calibrated_z", "L1 캘리브레이션 지표"),
            ("l2_pattern_density", "L2 패턴 밀도"),
            ("l3_rhythm", "L3 리듬"),
        ):
            b, a = res.before_layers[key], res.after_layers[key]
            delta = a - b
            col = GREEN if delta < -0.02 else (RED if delta > 0.02 else DIM)
            print(f"   {label:<22} {b:>+6.2f} → {a:>+6.2f}  {_c(col, f'{delta:+.2f}')}")

    if res.changes:
        print()
        print(f"  {_c(BOLD, '적용된 규칙')}")
        for c in res.changes:
            print(f"   {c.pattern_id} ×{c.count}  {c.name}")
            print(f"      {_c(DIM, repr(c.before))} → {_c(GREEN, repr(c.after))}")
    for w in res.warnings:
        print(f"  {_c(YELLOW, '!')} {w}")
    if args.output:
        print(f"  {_c(DIM, '저장:')} {args.output}")
    print()
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    text = _read_input(args.input)
    print(build_llm_prompt(text, genre=args.genre))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .web import serve
    return serve(host=args.host, port=args.port, open_browser=not args.no_open)


def cmd_clip(args: argparse.Namespace) -> int:
    """클립보드 내용을 바로 검사한다 (macOS pbpaste / Linux xclip)."""
    import shutil
    import subprocess

    for cmd in (["pbpaste"], ["xclip", "-selection", "clipboard", "-o"],
                ["wl-paste"]):
        if shutil.which(cmd[0]):
            text = subprocess.run(cmd, capture_output=True, text=True).stdout
            break
    else:
        print("클립보드를 읽을 도구가 없습니다 (pbpaste / xclip / wl-paste).",
              file=sys.stderr)
        return 2
    if not text.strip():
        print("클립보드가 비어 있습니다.", file=sys.stderr)
        return 1
    r = analyze(parsers.normalize(text), genre=args.genre)
    if args.json:
        print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_report(r, show_sentences=True)
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    from . import history
    if args.clear:
        print(f"  {history.clear()}건 삭제")
        return 0
    st = history.stats()
    if not st["enabled"]:
        print("  기록이 꺼져 있습니다 (AIKILLER_NO_HISTORY).")
        return 0
    print()
    print(f"  {st['count']}건 · 평균 {st.get('avg_score', '—')}점")
    print(f"  {_c(DIM, st['path'])}")
    print()
    for row in history.recent(args.limit):
        sc = f"{row.score:.0f}" if row.score is not None else "—"
        col = _BAND_COLOR.get(row.band or "", DIM)
        print(f"  {_c(col, f'{sc:>4}')}  {row.preview[:64]}")
    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="aikiller",
        description="한국어 AI 문체 탐지 + 다듬기. 탐지와 다듬기가 같은 패턴 레지스트리를 씁니다.",
    )
    sub = ap.add_subparsers(dest="cmd")

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("input", help="파일 경로, '-'(stdin), 또는 텍스트 자체")
        p.add_argument("--genre", default="essay",
                       choices=["essay", "report", "column", "blog", "abstract"],
                       help="기준선 장르 (기본 essay)")
        p.add_argument("--json", action="store_true", help="JSON 출력")

    p_d = sub.add_parser("detect", aliases=["검사"],
                         help="AI 문체 점수와 근거를 낸다")
    common(p_d)
    p_d.add_argument("--no-sentences", action="store_true", help="문장별 하이라이트 숨김")
    p_d.set_defaults(func=cmd_detect)

    p_h = sub.add_parser("humanize", aliases=["polish", "다듬기"],
                         help="탐지된 구간만 규칙으로 다듬는다")
    common(p_h)
    p_h.add_argument("--level", default="moderate",
                     choices=["safe", "moderate", "aggressive"], help="다듬기 강도")
    p_h.add_argument("--diff", action="store_true", help="원문 대비 diff 출력")
    p_h.add_argument("-o", "--output", help="결과를 파일로 저장")
    p_h.set_defaults(func=cmd_humanize)

    p_p = sub.add_parser("prompt", help="규칙으로 못 고치는 것용 LLM 다듬기 프롬프트 생성")
    common(p_p)
    p_p.set_defaults(func=cmd_prompt)

    p_s = sub.add_parser("serve", help="웹 UI를 띄운다 (인자 없이 실행해도 이게 뜬다)")
    p_s.add_argument("--host", default="127.0.0.1")
    p_s.add_argument("--port", type=int, default=8000)
    p_s.add_argument("--no-open", action="store_true", help="브라우저를 열지 않는다")
    p_s.set_defaults(func=cmd_serve)

    p_c = sub.add_parser("clip", help="클립보드 내용을 바로 검사한다")
    p_c.add_argument("--genre", default="essay",
                     choices=["essay", "report", "column", "blog", "abstract"])
    p_c.add_argument("--json", action="store_true")
    p_c.set_defaults(func=cmd_clip)

    p_h = sub.add_parser("history", help="로컬 분석 기록")
    p_h.add_argument("--limit", type=int, default=20)
    p_h.add_argument("--clear", action="store_true", help="전부 지운다")
    p_h.set_defaults(func=cmd_history)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    # 인자 없이 실행하면 가장 흔한 용도(웹 UI)로 바로 간다.
    if not (argv if argv is not None else sys.argv[1:]):
        argv = ["serve"]
    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except parsers.ParseError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
