#!/usr/bin/env python3
"""탐지 성능 평가 — accuracy가 아니라 TPR@FPR을 본다.

왜 accuracy가 아닌가
--------------------
상용 도구들이 광고하는 "정확도 98%"는 자체 테스트셋(in-domain) 기준이라
실사용 성능을 말해 주지 않는다. 실제로 의미 있는 숫자는 하나다:

    사람 글 100건 중 1건만 오탐하는 지점에서, AI 글을 몇 % 잡는가
    = TPR @ FPR = 1%

교육기관·인사팀에 납품한다면 오탐 1건이 사람 인생 문제가 된다.
그래서 이 스크립트는 FPR을 먼저 고정하고 TPR을 보고한다.

추가로 다음을 쪼개서 본다:
  * 길이 구간별 — 짧은 글은 원리적으로 탐지 불가. 그 경계를 확인한다.
  * 장르별      — 격식체 산문(보고서·논문)은 AI와 표면 특징이 겹친다.
  * 적대적      — 다듬기 통과본. 방패를 통과한 텍스트를 얼마나 잡는가.

코퍼스
------
    data/corpus/human/*.txt        사람 글
    data/corpus/ai/*.txt           AI 글
    data/corpus/adversarial/*.txt  다듬기/패러프레이즈를 거친 AI 글 (선택)

사용:
    python3 scripts/eval.py
    python3 scripts/eval.py --fpr 0.01 0.05 --json out/eval.json
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aikiller.detect import analyze  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CORPUS = os.path.join(ROOT, "data", "corpus")

LENGTH_BUCKETS = ((0, 150), (150, 400), (400, 1000), (1000, 10**9))


def genre_of(path: str) -> str:
    name = os.path.basename(path)
    return name.split("__")[0] if "__" in name else "essay"


def load(label: str):
    rows = []
    for path in sorted(glob.glob(os.path.join(CORPUS, label, "*.txt"))):
        with open(path, encoding="utf-8") as f:
            text = f.read().strip()
        if text:
            rows.append({"path": path, "text": text, "genre": genre_of(path)})
    return rows


def score_all(rows):
    for r in rows:
        rep = analyze(r["text"], genre=r["genre"])
        r["score"] = rep.score
        r["n_chars"] = rep.n_chars
    return rows


def threshold_at_fpr(human_scores, target_fpr: float) -> float:
    """사람 글의 오탐률이 target_fpr 이하가 되는 최소 임계값."""
    if not human_scores:
        return 50.0
    ordered = sorted(human_scores, reverse=True)
    n_allowed = int(len(ordered) * target_fpr)
    if n_allowed >= len(ordered):
        return 0.0
    # n_allowed 건까지만 임계값을 넘도록 — 그 다음 값보다 아주 조금 위
    return ordered[n_allowed] + 1e-9


def tpr_at(ai_scores, threshold: float) -> float:
    if not ai_scores:
        return 0.0
    return sum(1 for s in ai_scores if s >= threshold) / len(ai_scores)


def auroc(human_scores, ai_scores) -> float:
    """Mann-Whitney U 기반 AUROC. 동점은 0.5로 센다."""
    if not human_scores or not ai_scores:
        return 0.5
    wins = 0.0
    for a in ai_scores:
        for h in human_scores:
            if a > h:
                wins += 1
            elif a == h:
                wins += 0.5
    return wins / (len(ai_scores) * len(human_scores))


def summarize(name: str, human, ai, fprs) -> dict:
    hs = [r["score"] for r in human]
    as_ = [r["score"] for r in ai]
    out = {
        "name": name,
        "n_human": len(hs),
        "n_ai": len(as_),
        "auroc": round(auroc(hs, as_), 4),
        "mean_human": round(statistics.fmean(hs), 1) if hs else None,
        "mean_ai": round(statistics.fmean(as_), 1) if as_ else None,
        "operating_points": [],
    }
    for fpr in fprs:
        th = threshold_at_fpr(hs, fpr)
        out["operating_points"].append({
            "target_fpr": fpr,
            "threshold": round(th, 2),
            "tpr": round(tpr_at(as_, th), 4),
        })
    return out


def print_block(res: dict) -> None:
    print(f"\n  {res['name']}  (사람 {res['n_human']} · AI {res['n_ai']})")
    if not res["n_human"] or not res["n_ai"]:
        print("    표본 부족 — 건너뜀")
        return
    print(f"    AUROC {res['auroc']:.4f}   평균점수 사람 {res['mean_human']} / AI {res['mean_ai']}")
    for op in res["operating_points"]:
        print(f"    TPR @ FPR={op['target_fpr']:.0%}  =  {op['tpr']:.1%}"
              f"   (임계값 {op['threshold']:.1f})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--fpr", type=float, nargs="+", default=[0.01, 0.05, 0.10])
    ap.add_argument("--json", help="결과를 JSON으로 저장할 경로")
    args = ap.parse_args(argv)

    human = load("human")
    ai = load("ai")
    adv = load("adversarial")

    if not human or not ai:
        print("코퍼스가 비어 있습니다.")
        print(f"  {CORPUS}/human/*.txt")
        print(f"  {CORPUS}/ai/*.txt")
        print("\n먼저 코퍼스를 채우고 scripts/calibrate.py를 돌리세요.")
        return 1

    print(f"채점 중… 사람 {len(human)} · AI {len(ai)}"
          + (f" · 적대적 {len(adv)}" if adv else ""))
    score_all(human)
    score_all(ai)
    if adv:
        score_all(adv)

    results = {"overall": summarize("전체", human, ai, args.fpr), "slices": []}
    print_block(results["overall"])

    print("\n  ── 길이 구간별 " + "─" * 30)
    for lo, hi in LENGTH_BUCKETS:
        h = [r for r in human if lo <= r["n_chars"] < hi]
        a = [r for r in ai if lo <= r["n_chars"] < hi]
        label = f"{lo}~{hi if hi < 10**9 else '∞'}자"
        res = summarize(label, h, a, args.fpr)
        results["slices"].append(res)
        print_block(res)

    genres = sorted({r["genre"] for r in human} | {r["genre"] for r in ai})
    if len(genres) > 1:
        print("\n  ── 장르별 " + "─" * 34)
        for g in genres:
            res = summarize(
                f"장르 {g}",
                [r for r in human if r["genre"] == g],
                [r for r in ai if r["genre"] == g],
                args.fpr,
            )
            results["slices"].append(res)
            print_block(res)

    if adv:
        print("\n  ── 적대적 (다듬기/패러프레이즈 통과본) " + "─" * 10)
        res = summarize("적대적", human, adv, args.fpr)
        results["slices"].append(res)
        print_block(res)
        base_tpr = results["overall"]["operating_points"][0]["tpr"]
        adv_tpr = res["operating_points"][0]["tpr"]
        drop = base_tpr - adv_tpr
        print(f"\n    ▶ 방패 통과 시 TPR@1% 하락폭: {drop:+.1%}"
              f"  ({base_tpr:.1%} → {adv_tpr:.1%})")
        print("      이 숫자가 이 사업의 실제 난이도입니다.")

    print()
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"  저장: {args.json}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
