#!/usr/bin/env python3
"""융합 가중치 실측 피팅 + L3 기준선 재측정.

이 스크립트가 이 프로젝트의 핵심 자산이다. detect.py의 WEIGHTS는 추정값이고,
이 스크립트를 돌려야 `fusion_calibrated: true`가 된다.

코퍼스 규약
-----------
    data/corpus/human/*.txt   사람이 쓴 글. **2022년 11월 이전 텍스트만.**
                              (ChatGPT 공개 이후 웹 텍스트는 오염됐다고 본다)
    data/corpus/ai/*.txt      LLM이 쓴 글. 모델·프롬프트·온도를 섞어야 한다.

    파일명에 장르를 넣으면 장르별로 분리 집계한다:  essay__001.txt

산출
----
    data/fusion_weights.json          L1~L4 로지스틱 가중치 (_fitted: true)
    data/l3_baseline.json             L3 지표의 사람 코퍼스 실측 평균·표준편차

사용:
    python3 scripts/calibrate.py
    python3 scripts/calibrate.py --epochs 4000 --lr 0.2
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aikiller import detect as D  # noqa: E402
from aikiller import metrics as M  # noqa: E402
from aikiller import patterns as P  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CORPUS = os.path.join(ROOT, "data", "corpus")
OUT_WEIGHTS = os.path.join(ROOT, "data", "fusion_weights.json")
OUT_BASELINE = os.path.join(ROOT, "data", "l3_baseline.json")

# L3 재측정 대상 — detect.py 가 지금 휴리스틱 임계값으로 쓰고 있는 것들.
# 사람 코퍼스로 실측하면 그 임계값을 z 기반으로 바꿀 수 있다.
L3_METRICS = ("ending_diversity", "declarative_ratio")

MIN_DOCS_PER_CLASS = 20
MIN_CHARS = D.MIN_CHARS_SCORE


def genre_of(path: str) -> str:
    name = os.path.basename(path)
    return name.split("__")[0] if "__" in name else "essay"


def load_corpus(label: str) -> list[tuple[str, str]]:
    """[(text, genre)] — 너무 짧은 문서는 버린다."""
    out = []
    skipped = 0
    for path in sorted(glob.glob(os.path.join(CORPUS, label, "*.txt"))):
        with open(path, encoding="utf-8") as f:
            text = f.read().strip()
        if len(text) < MIN_CHARS:
            skipped += 1
            continue
        out.append((text, genre_of(path)))
    if skipped:
        print(f"  {label}: {skipped}건이 {MIN_CHARS}자 미만이라 제외됨")
    return out


def features(text: str, genre: str) -> list[float]:
    """detect.py와 **동일한** 계층 계산. 여기서 갈라지면 피팅이 무의미해진다.

    analyze() 가 맨 앞에서 하는 개행 정규화를 여기서도 해야 CRLF 입력에서
    값이 갈리지 않는다.
    """
    text = text.replace("\r\n", "\n")
    raw = M.compute(text)
    hits = P.find_hits(text)
    l1, _ = D._layer1(raw, genre)
    l2, _, _ = D._layer2(text, hits)
    l3, _ = D._layer3(text, raw)
    l4, _ = D._layer_human(text)
    return [l1, l2, l3, l4]


def fit_logistic(X, y, epochs: int, lr: float, l2_reg: float = 1e-3):
    """표준 라이브러리만으로 로지스틱 회귀(전배치 경사하강)."""
    n_feat = len(X[0])
    w = [0.0] * n_feat
    b = 0.0
    n = len(X)
    for epoch in range(epochs):
        gw = [0.0] * n_feat
        gb = 0.0
        loss = 0.0
        for xi, yi in zip(X, y):
            z = sum(wj * xj for wj, xj in zip(w, xi)) + b
            p = min(max(D._sigmoid(z), 1e-9), 1 - 1e-9)
            loss -= yi * math.log(p) + (1 - yi) * math.log(1 - p)
            err = p - yi
            for j in range(n_feat):
                gw[j] += err * xi[j]
            gb += err
        for j in range(n_feat):
            w[j] -= lr * (gw[j] / n + l2_reg * w[j])
        b -= lr * (gb / n)
        if epoch % max(1, epochs // 5) == 0:
            print(f"    epoch {epoch:>5}  loss={loss / n:.4f}  "
                  f"w={[round(v, 3) for v in w]}  b={b:.3f}")
    return w, b


def recalibrate_l3(human_docs) -> dict:
    """사람 코퍼스로 L3 지표의 평균·표준편차를 실측한다."""
    by_genre: dict = {}
    for text, genre in human_docs:
        raw = M.compute(text)
        bucket = by_genre.setdefault(genre, {})
        for k in L3_METRICS:
            if k in raw:
                bucket.setdefault(k, []).append(float(raw[k]))

    genres = {}
    for genre, metrics in by_genre.items():
        cells = {}
        for k, vals in metrics.items():
            if len(vals) < MIN_DOCS_PER_CLASS:
                continue
            cells[k] = {
                "mean": round(statistics.fmean(vals), 5),
                "stdev": round(statistics.pstdev(vals), 5),
                "n": len(vals),
                "_placeholder": False,
            }
        if cells:
            genres[genre] = cells
    return {
        "version": "calibrated",
        "source": f"data/corpus/human ({len(human_docs)} docs)",
        "note": "사람 코퍼스 실측. detect.py 의 L3 휴리스틱 임계값을 대체할 재료다.",
        "genres": genres,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--epochs", type=int, default=3000)
    ap.add_argument("--lr", type=float, default=0.3)
    ap.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않는다")
    args = ap.parse_args(argv)

    print("코퍼스 로딩")
    human = load_corpus("human")
    ai = load_corpus("ai")
    print(f"  사람 {len(human)}건 · AI {len(ai)}건")

    if len(human) < MIN_DOCS_PER_CLASS or len(ai) < MIN_DOCS_PER_CLASS:
        print()
        print(f"중단: 클래스당 최소 {MIN_DOCS_PER_CLASS}건이 필요합니다.")
        print("  data/corpus/human/  — 2022년 11월 이전 사람 글")
        print("  data/corpus/ai/     — 여러 모델·프롬프트로 생성한 AI 글")
        print()
        print("적은 데이터로 피팅하면 과적합된 가중치가 '실측'으로 둔갑합니다.")
        return 1

    print("\n특징 추출")
    X, y = [], []
    for text, genre in human:
        X.append(features(text, genre))
        y.append(0)
    for text, genre in ai:
        X.append(features(text, genre))
        y.append(1)
    for name, idx in (("L1", 0), ("L2", 1), ("L3", 2), ("L4", 3)):
        h = [x[idx] for x, t in zip(X, y) if t == 0]
        a = [x[idx] for x, t in zip(X, y) if t == 1]
        gap = abs(statistics.fmean(a) - statistics.fmean(h))
        print(f"  {name}: 사람 {statistics.fmean(h):+.3f} vs "
              f"AI {statistics.fmean(a):+.3f}  (분리도 {gap:.3f})")

    print("\n로지스틱 피팅")
    w, b = fit_logistic(X, y, args.epochs, args.lr)

    weights = {
        "l1_calibrated_z": round(w[0], 4),
        "l2_pattern_density": round(w[1], 4),
        "l3_rhythm": round(w[2], 4),
        "l4_human_evidence": round(w[3], 4),
        "bias": round(b, 4),
        "_fitted": True,
        "_n_human": len(human),
        "_n_ai": len(ai),
    }
    print(f"\n  가중치: {json.dumps(weights, ensure_ascii=False)}")

    baseline = recalibrate_l3(human)
    n_cells = sum(len(v) for v in baseline["genres"].values())
    print(f"  L3 기준선: 장르 {len(baseline['genres'])}개 · 셀 {n_cells}개 실측")

    if args.dry_run:
        print("\n--dry-run: 저장하지 않음")
        return 0

    os.makedirs(os.path.dirname(OUT_WEIGHTS), exist_ok=True)
    with open(OUT_WEIGHTS, "w", encoding="utf-8") as f:
        json.dump(weights, f, ensure_ascii=False, indent=2)
    with open(OUT_BASELINE, "w", encoding="utf-8") as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)
    print(f"\n저장: {OUT_WEIGHTS}")
    print(f"저장: {OUT_BASELINE}")
    print("\n이제 detect.analyze()가 fusion_calibrated=True를 반환합니다.")
    print("다음: python3 scripts/eval.py  로 TPR@FPR=1% 를 확인하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
