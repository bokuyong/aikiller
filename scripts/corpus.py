#!/usr/bin/env python3
"""코퍼스 구축 도구 — 수집 · 생성 · 적대적 샘플 · 통계.

캘리브레이션의 재료를 만드는 도구다. 전체 공수의 70%가 여기에 들어간다.

서브커맨드
----------
    import      로컬 파일/디렉터리를 코퍼스로 정규화해 넣는다 (hwp/docx/pdf/txt)
    wiki        한국어 위키백과 덤프(.xml.bz2)에서 사람 글을 추출한다
    generate    LLM API로 AI 글을 생성한다 (주제를 사람 코퍼스와 맞춘다)
    adversarial 기존 AI 코퍼스를 다듬기로 통과시켜 적대적 샘플을 만든다
    stats       코퍼스 현황을 본다

오염 방지 원칙
--------------
사람 글은 **2022년 11월 이전** 텍스트만 신뢰한다. ChatGPT 공개 이후의 웹
텍스트는 AI가 섞였다고 봐야 한다. `wiki` 서브커맨드는 덤프 파일명·메타의
날짜를 확인해 경고한다. `import`는 `--attest-pre-2022` 없이는 human 라벨을
거부한다 — 사람이 직접 확인했다는 기록을 남기게 하려는 것이다.

표준 라이브러리만 쓴다. LLM 호출도 urllib로 한다.
"""

from __future__ import annotations

import argparse
import bz2
import glob
import hashlib
import json
import os
import random
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aikiller import parsers  # noqa: E402
from aikiller.humanize import humanize  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CORPUS = os.path.join(ROOT, "data", "corpus")
LABELS = ("human", "ai", "adversarial")
GENRES = ("essay", "report", "column", "blog", "abstract")

MIN_CHARS = 400      # 캘리브레이션에 쓸 최소 분량
MAX_CHARS = 6000     # 이보다 길면 자른다 (문단 경계 기준)


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------

def corpus_dir(label: str) -> str:
    d = os.path.join(CORPUS, label)
    os.makedirs(d, exist_ok=True)
    return d


def doc_id(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def existing_ids(label: str) -> set[str]:
    out = set()
    for p in glob.glob(os.path.join(corpus_dir(label), "*.txt")):
        name = os.path.basename(p)
        if "__" in name:
            out.add(name.rsplit("__", 1)[-1].removesuffix(".txt"))
    return out


def truncate(text: str) -> str:
    """MAX_CHARS를 넘으면 문단 경계에서 자른다."""
    if len(text) <= MAX_CHARS:
        return text
    parts = text.split("\n\n")
    out: list[str] = []
    total = 0
    for p in parts:
        if total + len(p) > MAX_CHARS and out:
            break
        out.append(p)
        total += len(p) + 2
    return "\n\n".join(out) if out else text[:MAX_CHARS]


def save(label: str, genre: str, text: str, seen: set[str]) -> bool:
    """중복·분량 검사를 통과하면 저장한다. 저장했으면 True."""
    text = parsers.normalize(truncate(text))
    if len(text) < MIN_CHARS:
        return False
    did = doc_id(text)
    if did in seen:
        return False
    seen.add(did)
    path = os.path.join(corpus_dir(label), f"{genre}__{did}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return True


# ---------------------------------------------------------------------------
# import — 로컬 파일 수집
# ---------------------------------------------------------------------------

def cmd_import(args: argparse.Namespace) -> int:
    if args.label == "human" and not args.attest_pre_2022:
        print("거부: human 라벨에는 --attest-pre-2022 가 필요합니다.")
        print()
        print("  ChatGPT 공개(2022-11) 이후 웹 텍스트는 AI가 섞였다고 봐야 합니다.")
        print("  오염된 사람 코퍼스로 캘리브레이션하면 탐지기가 조용히 망가집니다.")
        print("  출처가 2022년 11월 이전임을 확인했다면 플래그를 붙이세요.")
        return 1

    paths: list[str] = []
    for target in args.paths:
        if os.path.isdir(target):
            for ext in parsers.SUPPORTED:
                paths.extend(glob.glob(os.path.join(target, "**", f"*{ext}"),
                                       recursive=True))
        else:
            paths.append(target)

    seen = existing_ids(args.label)
    saved = skipped = failed = 0
    for p in sorted(set(paths)):
        try:
            text = parsers.parse_file(p)
        except (parsers.ParseError, OSError) as e:
            print(f"  실패 {os.path.basename(p)}: {e}")
            failed += 1
            continue
        if save(args.label, args.genre, text, seen):
            saved += 1
        else:
            skipped += 1

    print(f"\n{args.label}/{args.genre}: 저장 {saved} · 건너뜀 {skipped}"
          f"(중복 또는 {MIN_CHARS}자 미만) · 실패 {failed}")
    return 0


# ---------------------------------------------------------------------------
# wiki — 한국어 위키백과 덤프 추출
# ---------------------------------------------------------------------------

_WIKI_STRIP = [
    (re.compile(r"<ref[^>]*>.*?</ref>", re.S), ""),
    (re.compile(r"<ref[^>]*/>"), ""),
    (re.compile(r"<!--.*?-->", re.S), ""),
    (re.compile(r"\{\{[^{}]*\}\}"), ""),          # 템플릿 (1단계)
    (re.compile(r"\[\[(?:파일|File|Image|분류|Category):[^\]]*\]\]"), ""),
    (re.compile(r"\[\[[^\]|]*\|([^\]]*)\]\]"), r"\1"),   # [[문서|표시]] -> 표시
    (re.compile(r"\[\[([^\]]*)\]\]"), r"\1"),
    (re.compile(r"'{2,}"), ""),                    # 굵게/기울임
    (re.compile(r"(?m)^[=]{2,}.*?[=]{2,}\s*$"), ""),  # 섹션 헤딩
    (re.compile(r"(?m)^[*#:;].*$"), ""),           # 목록·정의
    (re.compile(r"(?s)\{\|.*?\|\}"), ""),          # 표
    (re.compile(r"https?://\S+"), ""),
    (re.compile(r"<[^>]+>"), ""),
]

_HANGUL_RE = re.compile(r"[가-힣]")


def clean_wikitext(raw: str) -> str:
    text = raw
    for _ in range(3):  # 중첩 템플릿을 여러 번 훑는다
        for pat, rep in _WIKI_STRIP:
            text = pat.sub(rep, text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 문단 단위로 걸러낸다 — 한글 비중이 낮은 줄은 표·수식 잔해다
    keep = []
    for para in text.split("\n"):
        para = para.strip()
        if len(para) < 40:
            continue
        hangul = len(_HANGUL_RE.findall(para))
        if hangul / len(para) < 0.35:
            continue
        keep.append(para)
    return "\n\n".join(keep).strip()


def cmd_wiki(args: argparse.Namespace) -> int:
    if not os.path.exists(args.dump):
        print(f"덤프 파일이 없습니다: {args.dump}")
        print()
        print("  한국어 위키백과 덤프는 여기서 받습니다:")
        print("    https://dumps.wikimedia.org/kowiki/")
        print("  파일: kowiki-<날짜>-pages-articles.xml.bz2 (약 1GB)")
        print()
        print("  ⚠ 2022년 11월 이전 스냅샷을 받으세요. 최신 덤프는 AI 생성 문서가")
        print("    섞였을 수 있습니다. https://dumps.wikimedia.org/archive/ 참고.")
        return 1

    m = re.search(r"(20\d{2})(\d{2})\d{2}", os.path.basename(args.dump))
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if (y, mo) > (2022, 11):
            print(f"⚠ 경고: 덤프 날짜가 {y}-{mo:02d}로 ChatGPT 공개(2022-11) 이후입니다.")
            print("  이 코퍼스를 'human'으로 쓰면 오염될 수 있습니다.")
            if not args.force:
                print("  그래도 진행하려면 --force 를 붙이세요.")
                return 1

    seen = existing_ids(args.label)
    saved = 0
    opener = bz2.open if args.dump.endswith(".bz2") else open

    print(f"파싱 중… (목표 {args.limit}건)")
    with opener(args.dump, "rb") as f:
        for _event, elem in ET.iterparse(f, events=("end",)):
            tag = elem.tag.rsplit("}", 1)[-1]
            if tag != "page":
                continue
            ns = elem.findtext("./{*}ns")
            title = elem.findtext("./{*}title") or ""
            raw = elem.findtext("./{*}revision/{*}text") or ""
            elem.clear()
            if ns != "0" or not raw:
                continue
            if raw.lstrip().startswith("#넘겨주기") or "#REDIRECT" in raw[:40].upper():
                continue
            text = clean_wikitext(raw)
            if save(args.label, args.genre, text, seen):
                saved += 1
                if saved % 25 == 0:
                    print(f"  {saved} / {args.limit}   (최근: {title[:30]})")
                if saved >= args.limit:
                    break

    print(f"\n{args.label}/{args.genre}: {saved}건 저장")
    return 0


# ---------------------------------------------------------------------------
# generate — LLM으로 AI 글 생성
# ---------------------------------------------------------------------------

# 프롬프트를 섞어야 한 모델·한 문체의 탐지기가 되지 않는다.
PROMPT_TEMPLATES = [
    "다음 주제로 한국어 글을 {n}자 내외로 써 줘.\n주제: {topic}",
    "당신은 칼럼니스트입니다. 다음 주제로 {n}자 분량의 칼럼을 작성하세요.\n주제: {topic}",
    "다음 주제에 대해 {n}자 정도의 한국어 설명문을 자연스럽게 작성해 주세요.\n주제: {topic}",
    "'{topic}'에 관해 {n}자 분량으로 정리해 주세요. 사람이 쓴 것처럼 자연스럽게요.",
    "블로그 글을 써 줘. 주제는 '{topic}', 길이는 {n}자 정도. 너무 딱딱하지 않게.",
]

TEMPERATURES = [0.3, 0.6, 0.8, 1.0]


def call_anthropic(prompt: str, model: str, temperature: float, max_tokens: int) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY 환경변수가 없습니다.")
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        payload = json.loads(r.read())
    return "".join(b.get("text", "") for b in payload.get("content", []))


def call_openai(prompt: str, model: str, temperature: float, max_tokens: int) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY 환경변수가 없습니다.")
    body = json.dumps({
        "model": model,
        "max_completion_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"content-type": "application/json",
                 "authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        payload = json.loads(r.read())
    return payload["choices"][0]["message"]["content"]


PROVIDERS = {"anthropic": call_anthropic, "openai": call_openai}


def load_topics(args: argparse.Namespace) -> list[str]:
    """주제 목록. 사람 코퍼스의 첫 문장에서 뽑으면 주제가 짝지어진다."""
    if args.topics:
        with open(args.topics, encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]

    topics: list[str] = []
    for p in sorted(glob.glob(os.path.join(corpus_dir("human"), "*.txt"))):
        with open(p, encoding="utf-8") as f:
            head = f.read(300)
        first = re.split(r"(?<=[.!?])\s", head.strip())[0]
        if 10 <= len(first) <= 120:
            topics.append(first)
    return topics


def cmd_generate(args: argparse.Namespace) -> int:
    topics = load_topics(args)
    if not topics:
        print("주제가 없습니다.")
        print("  --topics <파일>  으로 한 줄에 하나씩 주면 됩니다.")
        print("  또는 data/corpus/human 을 먼저 채우면 주제를 자동으로 뽑습니다")
        print("  (사람 글과 주제를 맞춰야 탐지기가 '주제'가 아니라 '문체'를 배웁니다).")
        return 1

    fn = PROVIDERS[args.provider]
    seen = existing_ids("ai")
    rng = random.Random(args.seed)
    saved = failed = 0

    print(f"{args.provider}/{args.model} 로 {args.count}건 생성")
    for i in range(args.count):
        topic = topics[i % len(topics)]
        template = rng.choice(PROMPT_TEMPLATES)
        temp = rng.choice(TEMPERATURES)
        prompt = template.format(topic=topic, n=args.length)
        try:
            text = fn(prompt, args.model, temp, args.max_tokens)
        except (urllib.error.URLError, RuntimeError, KeyError, OSError) as e:
            print(f"  [{i + 1}] 실패: {e}")
            failed += 1
            continue
        if save("ai", args.genre, text, seen):
            saved += 1
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{args.count}  (저장 {saved})")

    print(f"\nai/{args.genre}: 저장 {saved} · 실패 {failed}")
    if saved:
        print("\n다음 모델로도 돌려서 섞으세요 — 한 모델만 쓰면")
        print("그 모델 전용 탐지기가 됩니다.")
    return 0


# ---------------------------------------------------------------------------
# adversarial — 방패 통과본 만들기
# ---------------------------------------------------------------------------

def cmd_adversarial(args: argparse.Namespace) -> int:
    src = sorted(glob.glob(os.path.join(corpus_dir("ai"), "*.txt")))
    if not src:
        print("data/corpus/ai 가 비어 있습니다. 먼저 generate 를 돌리세요.")
        return 1

    seen = existing_ids("adversarial")
    saved = 0
    for p in src:
        with open(p, encoding="utf-8") as f:
            text = f.read()
        genre = os.path.basename(p).split("__")[0]
        res = humanize(text, level=args.level, genre=genre,
                       score_before_after=False)
        if res.aborted:
            continue
        if save("adversarial", genre, res.text, seen):
            saved += 1

    print(f"adversarial: {saved}건 생성 (강도 {args.level})")
    print()
    print("이제 scripts/eval.py 를 돌리면 '방패 통과 시 TPR 하락폭'이 나옵니다.")
    print("그 숫자가 이 사업의 실제 난이도입니다.")
    return 0


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

def cmd_stats(args: argparse.Namespace) -> int:
    print()
    total = 0
    for label in LABELS:
        files = sorted(glob.glob(os.path.join(corpus_dir(label), "*.txt")))
        by_genre: dict[str, list[int]] = {}
        for p in files:
            genre = os.path.basename(p).split("__")[0]
            by_genre.setdefault(genre, []).append(os.path.getsize(p))
        total += len(files)
        print(f"  {label:<12} {len(files):>5}건")
        for genre, sizes in sorted(by_genre.items()):
            avg = sum(sizes) / len(sizes) / 3  # UTF-8 한글 ≈ 3바이트
            print(f"      {genre:<10} {len(sizes):>5}건  평균 {avg:>5.0f}자")
    print()
    need = 20
    h = len(glob.glob(os.path.join(corpus_dir("human"), "*.txt")))
    a = len(glob.glob(os.path.join(corpus_dir("ai"), "*.txt")))
    if h < need or a < need:
        print(f"  캘리브레이션까지: 사람 {max(0, need - h)}건 · AI {max(0, need - a)}건 더 필요")
    else:
        print("  캘리브레이션 가능:  python3 scripts/calibrate.py")
    print()
    return 0


# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("import", help="로컬 파일/디렉터리를 코퍼스로 넣는다")
    p.add_argument("paths", nargs="+")
    p.add_argument("--label", required=True, choices=LABELS)
    p.add_argument("--genre", default="essay", choices=GENRES)
    p.add_argument("--attest-pre-2022", action="store_true",
                   help="출처가 2022년 11월 이전임을 확인했다 (human 라벨에 필수)")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("wiki", help="한국어 위키백과 덤프에서 사람 글 추출")
    p.add_argument("dump", help="kowiki-<날짜>-pages-articles.xml.bz2")
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--label", default="human", choices=LABELS)
    p.add_argument("--genre", default="report", choices=GENRES)
    p.add_argument("--force", action="store_true", help="2022-11 이후 덤프도 허용")
    p.set_defaults(func=cmd_wiki)

    p = sub.add_parser("generate", help="LLM API로 AI 글 생성")
    p.add_argument("--provider", default="anthropic", choices=sorted(PROVIDERS))
    p.add_argument("--model", default="claude-haiku-4-5-20251001")
    p.add_argument("--count", type=int, default=50)
    p.add_argument("--genre", default="essay", choices=GENRES)
    p.add_argument("--length", type=int, default=800, help="목표 글자 수")
    p.add_argument("--max-tokens", type=int, default=2000)
    p.add_argument("--topics", help="주제 목록 파일 (한 줄에 하나)")
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("adversarial", help="AI 코퍼스를 다듬기 통과시켜 적대적 샘플 생성")
    p.add_argument("--level", default="aggressive",
                   choices=["safe", "moderate", "aggressive"])
    p.set_defaults(func=cmd_adversarial)

    p = sub.add_parser("stats", help="코퍼스 현황")
    p.set_defaults(func=cmd_stats)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
