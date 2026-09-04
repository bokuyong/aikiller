"""핵심 회귀 테스트.

의존성 없이 돈다:  python3 -m unittest discover tests -v
"""

from __future__ import annotations

import io
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aikiller import parsers  # noqa: E402
from aikiller.detect import analyze  # noqa: E402
from aikiller.hangul import (  # noqa: E402
    instrumental_particle,
    object_particle,
    subject_particle,
)
from aikiller.humanize import humanize  # noqa: E402
from aikiller.patterns import (  # noqa: E402
    PATTERNS,
    PATTERNS_BY_ID,
    apply_rewrites,
    find_hits,
)

AI_TEXT = (
    "급변하는 현대 사회에서, 인공지능 기술은 우리의 삶에 매우 중요한 영향을 미치고 있다. "
    "이 연구는 인공지능이 노동 시장에 미치는 영향을 보여준다. "
    "많은 전문가들이 지적하듯이, 자동화를 통해 생산성이 향상될 수 있을 것으로 보인다. "
    "하지만, 동시에 일자리 감소라는 부정적인 측면도 간과할 수 없다. "
    "따라서, 정책적 대응이 중요한 역할을 한다고 볼 수 있다. "
    "결론적으로, 다양한 이해관계자들이 협력해야 하며, 균형 잡힌 접근이 요구되어진다."
)

HUMAN_TEXT = (
    "어제 퇴근길에 지하철에서 이상한 걸 봤다. 어떤 아저씨가 문 앞에 서서 계속 뭔가를 "
    "중얼거리는 거다. 처음엔 통화하는 줄 알았는데 이어폰도 안 꽂았더라. 슬쩍 봤더니 손에 "
    "종이를 들고 있었다. 대본 같았다.\n"
    "아마 면접 준비였겠지. 아니면 발표. 뭐가 됐든 남들 다 보는 데서 그렇게 연습할 정도면 "
    "꽤 절박했을 거다. 나도 그런 적 있다. 첫 직장 면접 전날 밤에 화장실 거울 보면서 "
    "자기소개를 스무 번쯤 읽었다. 그때는 그게 창피한 줄도 몰랐다.\n"
    "요즘은 그런 절박함이 좀 그립다. 뭔가를 그렇게까지 원해본 게 언제였더라. "
    "지하철 아저씨는 신도림에서 내렸다. 나는 계속 갔다."
)


class TestHangul(unittest.TestCase):
    def test_subject_particle(self):
        self.assertEqual(subject_particle("사람"), "이")
        self.assertEqual(subject_particle("요소"), "가")

    def test_object_particle(self):
        self.assertEqual(object_particle("학생"), "을")
        self.assertEqual(object_particle("의자"), "를")

    def test_instrumental_riul_exception(self):
        # 받침 ㄹ 은 '으로'가 아니라 '로'
        self.assertEqual(instrumental_particle("서울"), "로")
        self.assertEqual(instrumental_particle("물"), "로")
        self.assertEqual(instrumental_particle("사람"), "으로")


class TestPatterns(unittest.TestCase):
    def test_registry_integrity(self):
        ids = [p.id for p in PATTERNS]
        self.assertEqual(len(ids), len(set(ids)), "패턴 ID 중복")
        for p in PATTERNS:
            self.assertIn(p.risk, ("safe", "moderate", "aggressive"))
            self.assertIn(p.severity, (1, 2, 3))
            self.assertTrue(p.hint, f"{p.id} 에 hint 가 없다")

    def test_double_passive(self):
        # 이중 피동은 safe 등급 — 활용형까지 잡혀야 한다
        for before, after in (
            ("고려되어져야 한다", "고려되어야 한다"),
            ("그렇게 보여진다", "그렇게 보인다"),
            ("잊혀진 이름", "잊힌 이름"),
        ):
            self.assertEqual(apply_rewrites(before, "safe")[0], after)

    def test_deul_particle_reselection(self):
        # A-17 은 aggressive + min_count=2 로 내렸다 — 유정명사의 '-들'은
        # 오류가 아니고, 원 분류 체계에서도 hold 상태다.
        text = "다양한 요소들이 있고 많은 사람들이 모였다."
        self.assertEqual(apply_rewrites(text, "safe")[0], text)
        out, _ = apply_rewrites(text, "aggressive")
        # '들'을 지우면 조사도 종성에 맞게 다시 골라야 한다
        self.assertIn("다양한 요소가", out)
        self.assertIn("많은 사람이", out)

    def test_deul_does_not_break_copula(self):
        # 조사 '이' 뒤에 어미가 오면 주격조사가 아니라 계사 '이-'다.
        # 구분 못 하면 '여러 문제들이었다' -> '여러 문제가었다' 가 된다.
        for t in ("여러 문제들이었다. 다양한 요소들이지만 하나다.",
                  "모든 국가들이라면 수많은 기회들이며"):
            out, _ = apply_rewrites(t, "aggressive")
            for bad in ("가었", "가지만", "가라면", "가며"):
                self.assertNotIn(bad, out, f"계사 파괴: {out}")

    def test_politeness_preserved(self):
        # 습니다체를 해라체로 떨어뜨리면 안 된다 (E-7)
        out, _ = apply_rewrites("그렇다고 볼 수 있습니다.", "moderate")
        self.assertTrue(out.endswith("습니다."), out)
        out2, _ = apply_rewrites("이는 중요한 문제라고 할 수 있습니다.", "moderate")
        self.assertEqual(out2, "이는 중요한 문제입니다.")

    def test_predicative_noun_whitelist(self):
        # '조사를 진행했다' -> '조사했다' (O),  '업무를 진행했다' 는 그대로 (X)
        self.assertEqual(apply_rewrites("조사를 진행했다", "moderate")[0], "조사했다")
        self.assertEqual(apply_rewrites("업무를 진행했다", "moderate")[0], "업무를 진행했다")

    def test_risk_ordering(self):
        # safe 는 aggressive 규칙을 절대 적용하지 않는다.
        # F-1 은 min_count=2 라 정도부사가 두 번 이상 나와야 발동한다.
        text = "매우 중요한 문제다. 정말 시급한 사안이다."
        safe_out, _ = apply_rewrites(text, "safe")
        self.assertIn("매우", safe_out)
        agg_out, _ = apply_rewrites(text, "aggressive")
        self.assertNotIn("매우", agg_out)
        self.assertNotIn("정말", agg_out)

    def test_min_count_suppresses_single_occurrence(self):
        # 사람도 한두 번은 쓰는 표현을 1회로 잡으면 오탐이 난다
        once = "매우 중요한 문제다."
        self.assertEqual(apply_rewrites(once, "aggressive")[0], once)
        self.assertFalse([h for h in find_hits(once) if h.pattern_id == "F-1"])

    def test_context_condition_final_section(self):
        # D-11 은 '문두 + 후반 30%' 조건에서만 발화한다
        head = "향후 계획을 세운다. " + "본문 문장이다. " * 20
        tail = "본문 문장이다. " * 20 + "향후 계획을 세운다."
        self.assertFalse([h for h in find_hits(head) if h.pattern_id == "D-11"])
        self.assertTrue([h for h in find_hits(tail) if h.pattern_id == "D-11"])

    def test_evidence_backed_patterns_outweigh_weak_ones(self):
        # 사람 코퍼스 0건 패턴이 근거 약한 패턴보다 무거워야 한다
        strong = PATTERNS_BY_ID["D-8a"].weight   # 사람 0.09 vs AI 0.92
        weak = PATTERNS_BY_ID["D-4"].weight      # 사람 0.26 vs AI 0.34
        self.assertGreater(strong, weak * 2)

    def test_find_hits_sorted(self):
        hits = find_hits(AI_TEXT)
        self.assertTrue(hits)
        self.assertEqual([h.start for h in hits], sorted(h.start for h in hits))


class TestReviewRegressions(unittest.TestCase):
    """검수에서 나온 결함들. 전부 실제로 사람 글을 망가뜨렸던 것들이다."""

    def test_inhae_does_not_eat_euro(self):
        # 탐욕적 매칭이 '으로'의 '으'를 먹어 '전쟁으 때문에'가 됐다
        for noun in ("전쟁", "폭염", "사건", "경쟁", "확산"):
            out, _ = apply_rewrites(f"{noun}으로 인해 문제가 생겼다.", "moderate")
            self.assertEqual(out, f"{noun} 때문에 문제가 생겼다.")

    def test_comma_rule_preserves_noun_lists(self):
        # '사고, 광고, 냉장고'의 나열 쉼표를 지우면 안 된다
        for t in ("재난 항목은 사고, 화재, 침수, 정전이다.",
                  "각 분야는 광고, 홍보, 마케팅을 포함한다.",
                  "냉장고, 세탁기, 에어컨을 샀다."):
            self.assertEqual(apply_rewrites(t, "safe")[0], t)

    def test_comma_rule_preserves_newlines(self):
        t = "밥을 먹으며,\n둘째 줄이다."
        self.assertIn("\n", apply_rewrites(t, "safe")[0])

    def test_politeness_in_saryodoenda(self):
        # 고정 문자열 치환이 '여겨집니다' -> '보인다' 로 경어법을 깼다
        self.assertEqual(apply_rewrites("그렇게 여겨집니다.", "moderate")[0],
                         "그렇게 보입니다.")
        self.assertEqual(apply_rewrites("그렇게 여겨진다.", "moderate")[0],
                         "그렇게 보인다.")

    def test_copula_not_doubled(self):
        # '혁신이라고 할 수 있습니다' -> '혁신이입니다' 였다
        self.assertEqual(apply_rewrites("이것은 혁신이라고 할 수 있습니다.", "moderate")[0],
                         "이것은 혁신입니다.")

    def test_passive_progressive_not_active(self):
        # A-20 은 피동 진행이 신호다. 능동 '~하고 있다'는 명시된 대조군이라
        # 건드리면 순수 오탐이 된다.
        self.assertEqual(apply_rewrites("경쟁이 심화되고 있다.", "moderate")[0],
                         "경쟁이 심화된다.")
        self.assertEqual(apply_rewrites("매출이 증가하고 있다.", "moderate")[0],
                         "매출이 증가하고 있다.")

    def test_conclusion_deleted_only_at_sentence_start(self):
        self.assertEqual(apply_rewrites("결론적으로, 세 가지다.", "moderate")[0],
                         "세 가지다.")
        self.assertEqual(apply_rewrites("이를 요약하면, 세 가지다.", "moderate")[0],
                         "이를 요약하면, 세 가지다.")

    def test_existential_verb_not_rewritten(self):
        t = "나는 도서관에 있어서 전화를 못 받았다."
        self.assertEqual(apply_rewrites(t, "aggressive")[0], t)

    def test_emoji_rule_spares_ordinary_symbols(self):
        out, _ = apply_rewrites("평점은 ★★★☆☆ 이고 체크는 ✓ 다.", "safe")
        self.assertIn("★★★☆☆", out)
        self.assertIn("✓", out)
        self.assertNotIn("📌", apply_rewrites("정리 📌 완료 ✅", "safe")[0])

    def test_roui_false_positive(self):
        for t in ("경로의 우선순위를 정한다.", "고속도로의 확장 공사가 시작됐다."):
            self.assertFalse([h for h in find_hits(t) if h.pattern_id == "A-19"], t)

    def test_broken_l1_metrics_removed(self):
        # 이 둘은 하드코딩된 극값 때문에 항상 클립 천장에 붙는 상수였고,
        # lexical_diversity 는 부호까지 반대였다.
        from aikiller.detect import CALIBRATED_METRICS
        self.assertNotIn("lexical_diversity", CALIBRATED_METRICS)
        self.assertNotIn("hanja_nominalizer_density", CALIBRATED_METRICS)

    def test_l2_does_not_saturate(self):
        """증거 밀도를 절반으로 줄이면 L2 도 눈에 띄게 내려가야 한다.

        L2 는 1,000자당 밀도라 길이 불변이다. 그래서 길이를 고정한 채
        AI 문장을 중립 문장으로 바꿔 밀도만 낮춘다. 이전 지수 포화 곡선은
        증거를 75% 지워도 값이 19%밖에 안 움직였다.
        """
        from aikiller.detect import _layer2
        filler = "그는 아침에 밥을 먹고 집을 나섰다. " * 53   # 약 1,100자
        vals = []
        for n in (1, 2, 4):
            t = filler + "결론적으로 그렇다. " * n
            vals.append(_layer2(t, find_hits(t))[0])
        # 밀도가 배로 늘면 L2 도 대략 배로 늘어야 한다 (선형 구간)
        self.assertGreater(vals[1] - vals[0], 0.05, f"포화: {vals}")
        self.assertGreater(vals[2] - vals[1], 0.05, f"포화: {vals}")

    def test_short_document_not_inflated(self):
        """400자 문서의 히트 1건이 2.5/1k 로 잡혀 곧바로 cap 에 걸리던 편향."""
        from aikiller.detect import _layer2, MIN_DENSITY_DENOM
        short = "결론적으로 그렇다. " + "그는 밥을 먹었다. " * 20   # 약 400자
        self.assertLess(len(short), MIN_DENSITY_DENOM)
        long_ = short + "그는 밥을 먹었다. " * 45
        l2s = _layer2(short, find_hits(short))[0]
        l2l = _layer2(long_, find_hits(long_))[0]
        # 같은 히트 수라면 짧은 쪽이 과도하게 높아선 안 된다
        self.assertLess(l2s, l2l * 2.2, f"짧은 문서 부풀림: {l2s} vs {l2l}")

    def test_human_evidence_lowers_score(self):
        from aikiller.detect import _layer_human
        human = ("솔직히 그때는 참 힘들었다. 근데 지나고 보니 내가 배운 게 많더라. "
                 "당시 선배가 도와줬다. " * 3)
        ai = "이러한 변화는 구조적 대응을 요구한다. " * 6
        self.assertGreater(_layer_human(human)[0], _layer_human(ai)[0])
        self.assertEqual(_layer_human(ai)[0], 0.0)

    def test_antithesis_pattern_implemented(self):
        # 원 분류 체계가 최강 신호로 지목한 구성물 (9.2배, p<0.0001)
        t = ("중요한 것은 속도가 아니라 방향이다. 필요한 것은 기술이 아니라 사람이다. "
             "이는 단순한 문제가 아니라 구조의 문제다.")
        self.assertTrue([h for h in find_hits(t) if h.pattern_id == "C-8b"])

    def test_weights_respect_negative_evidence(self):
        # 실측이 역전된 항목(사람이 더 많이 씀)은 가중치가 낮아야 한다
        for pid in ("A-1", "A-2", "A-11", "A-16", "I-1"):
            self.assertLessEqual(PATTERNS_BY_ID[pid].weight, 0.4,
                                 f"{pid}: 실측 역전 항목인데 가중치가 높다")


class TestDetect(unittest.TestCase):
    def test_ai_scores_higher_than_human(self):
        ai = analyze(AI_TEXT).score
        human = analyze(HUMAN_TEXT).score
        self.assertGreater(ai, human + 30, f"분리 실패: AI {ai} vs 사람 {human}")

    def test_short_text_refuses_to_judge(self):
        r = analyze("결론적으로, 이는 매우 중요하다.")
        self.assertEqual(r.confidence, "insufficient")

    def test_uncalibrated_flag_is_honest(self):
        r = analyze(AI_TEXT)
        if not os.path.exists(os.path.join(os.path.dirname(__file__),
                                           "..", "data", "fusion_weights.json")):
            self.assertFalse(r.fusion_calibrated)
            self.assertTrue(any("피팅" in n for n in r.notes))

    def test_sentence_scores_discriminate(self):
        # 곡선이 포화하면 안 된다 — 점수가 한 점으로 뭉치는지 본다
        scores = [s.score for s in analyze(AI_TEXT).sentences]
        self.assertGreater(max(scores) - min(scores), 20, f"변별력 없음: {scores}")

    def test_report_is_json_serializable(self):
        import json
        json.dumps(analyze(AI_TEXT).to_dict(), ensure_ascii=False)


class TestHumanize(unittest.TestCase):
    def test_score_improves(self):
        res = humanize(AI_TEXT, level="aggressive")
        self.assertLess(res.after_score, res.before_score)

    def test_change_rate_bounded(self):
        res = humanize(AI_TEXT, level="aggressive")
        self.assertLess(res.change_rate, 0.30, "규칙 다듬기가 과하게 바꿨다")
        self.assertFalse(res.aborted)

    def test_code_block_protected(self):
        text = (
            "결론적으로, 이는 매우 중요한 문제라고 할 수 있다.\n\n"
            "```python\n결론적으로 = '매우 중요한 값'\n```\n\n"
            "많은 사람들이 그렇게 생각한다."
        )
        res = humanize(text, level="aggressive")
        self.assertIn("결론적으로 = '매우 중요한 값'", res.text)
        self.assertIn("많은 사람들이", res.text)   # 1회뿐이라 A-17 미발동

    def test_quote_protected(self):
        text = '그는 "결론적으로, 매우 중요하다"고 말했다. 많은 사람들이 동의했다.'
        res = humanize(text, level="aggressive")
        self.assertIn('"결론적으로, 매우 중요하다"', res.text)

    def test_safe_level_is_conservative(self):
        res = humanize(AI_TEXT, level="safe")
        self.assertLess(res.change_rate, 0.06)


class TestParsers(unittest.TestCase):
    def test_docx(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", (
                '<?xml version="1.0"?><w:document xmlns:w="http://schemas.'
                'openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                "<w:p><w:r><w:t>첫 문단</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>둘째 문단</w:t></w:r></w:p>"
                "</w:body></w:document>"
            ))
        self.assertEqual(parsers.parse_docx(buf.getvalue()), "첫 문단\n\n둘째 문단")

    def test_hwpx(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("Contents/section0.xml", (
                '<?xml version="1.0"?><hs:sec xmlns:hs="http://www.hancom.co.kr/'
                'hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/'
                'paragraph"><hp:p><hp:run><hp:t>한글 문단</hp:t></hp:run></hp:p>'
                "</hs:sec>"
            ))
        self.assertEqual(parsers.parse_hwpx(buf.getvalue()), "한글 문단")

    def test_cp949_fallback(self):
        self.assertEqual(parsers.parse_txt("한글 인코딩".encode("cp949")), "한글 인코딩")

    def test_unsupported_extension(self):
        with self.assertRaises(parsers.ParseError):
            parsers.parse_bytes(b"x", ".xyz")


class TestSkillPackaging(unittest.TestCase):
    """Claude Code 스킬·플러그인 매니페스트. 형식이 깨지면 설치가 조용히 실패한다."""

    ROOT = os.path.join(os.path.dirname(__file__), "..")

    def _read(self, *parts):
        with open(os.path.join(self.ROOT, *parts), encoding="utf-8") as f:
            return f.read()

    def test_manifests_are_valid_json(self):
        import json
        plugin = json.loads(self._read(".claude-plugin", "plugin.json"))
        market = json.loads(self._read(".claude-plugin", "marketplace.json"))
        self.assertEqual(plugin["name"], "aikiller")
        self.assertEqual(market["name"], "aikiller")
        self.assertTrue(plugin["version"])
        self.assertEqual(market["metadata"]["pluginRoot"], ".")

    def test_runs_on_stock_macos_python(self):
        """macOS 기본 python3 는 3.9 다. 플러그인 설치자가 그걸 만난다.

        3.12+ 문법(여러 줄 중첩 f-string)을 쓰면 설치자에게 SyntaxError 가
        뜬다. 실제로 한 번 그랬다.
        """
        import py_compile
        import tempfile
        import glob
        for path in glob.glob(os.path.join(self.ROOT, "aikiller", "*.py")) + \
                glob.glob(os.path.join(self.ROOT, "scripts", "*.py")):
            with tempfile.NamedTemporaryFile(suffix=".pyc") as tmp:
                try:
                    py_compile.compile(path, cfile=tmp.name, doraise=True)
                except py_compile.PyCompileError as e:
                    self.fail(f"{os.path.basename(path)}: {e}")

    def test_versions_agree(self):
        import json
        import re
        plugin = json.loads(self._read(".claude-plugin", "plugin.json"))["version"]
        market = json.loads(self._read(".claude-plugin", "marketplace.json"))
        skill = re.search(r'^version:\s*"([^"]+)"',
                          self._read("skills", "aikiller", "SKILL.md"), re.M)
        self.assertIsNotNone(skill, "SKILL.md 에 version 이 없다")
        self.assertEqual(plugin, skill.group(1))
        self.assertEqual(plugin, market["metadata"]["version"])
        self.assertEqual(plugin, market["plugins"][0]["version"])

    def test_skill_frontmatter(self):
        text = self._read("skills", "aikiller", "SKILL.md")
        self.assertTrue(text.startswith("---\n"), "frontmatter 가 첫 줄이어야 한다")
        head = text.split("---", 2)[1]
        for key in ("name:", "description:"):
            self.assertIn(key, head)
        # description 은 트리거 문구를 담아야 스킬이 호출된다
        self.assertIn("트리거", head)
        self.assertGreater(len(head), 300, "description 이 너무 짧아 호출되지 않는다")

    def test_runner_is_executable_and_finds_repo(self):
        import subprocess
        runner = os.path.join(self.ROOT, "skills", "aikiller", "run.sh")
        self.assertTrue(os.access(runner, os.X_OK), "run.sh 에 실행 권한이 없다")
        # PATH 에 aikiller 가 없는 상태에서도 저장소를 찾아야 한다
        env = dict(os.environ, PATH="/usr/bin:/bin")
        out = subprocess.run([runner, "--help"], capture_output=True, text=True,
                             env=env, cwd="/", timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("humanize", out.stdout)

    def test_command_references_skill(self):
        cmd = self._read("commands", "aikiller.md")
        self.assertIn("$ARGUMENTS", cmd)
        self.assertIn("aikiller", cmd)


class TestCorpusTools(unittest.TestCase):
    """scripts/corpus.py — 코퍼스 구축 도구."""

    @staticmethod
    def _clean(raw):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        from corpus import clean_wikitext
        return clean_wikitext(raw)

    def test_wikitext_cleaner_strips_markup(self):
        raw = (
            "{{인용 틀|내용}}\n"
            "'''한국어'''는 [[한반도|한국]]에서 쓰이는 언어이다.<ref>출처 문헌</ref> "
            "사용 인구는 약 8천만 명으로 추정되며, 남북한 모두에서 공용어로 "
            "지정되어 있다. 문자 체계로는 [[한글]]을 사용한다.\n"
            "== 역사 ==\n"
            "* 목록 항목 하나\n"
            '{| class="wikitable"\n|-\n| 표 셀 내용 || 다른 셀\n|}\n'
            "15세기 세종대왕이 훈민정음을 창제하면서 고유 문자를 갖게 되었다. "
            "그 이전에는 한자를 빌려 표기하는 이두와 향찰이 쓰였다. 이러한 "
            "표기법은 한국어의 문법 구조와 맞지 않아 불편이 컸다.\n"
            "[[분류:언어]]\n"
        )
        out = self._clean(raw)
        for junk in ("{{", "[[", "<ref", "==", "wikitable", "분류:", "'''"):
            self.assertNotIn(junk, out, f"위키 마크업 잔존: {junk}")
        # 본문은 살아남아야 한다
        self.assertIn("한국어는 한국에서 쓰이는 언어이다", out)
        self.assertIn("훈민정음을 창제하면서", out)
        # 링크 표시 텍스트가 보존됐는지 ([[한반도|한국]] -> 한국)
        self.assertNotIn("한반도|", out)

    def test_wikitext_cleaner_drops_low_hangul_lines(self):
        # 표·수식 잔해는 한글 비중이 낮아 버려져야 한다
        raw = "abc def ghi jkl mno pqr stu vwx yz 123 456 789 000 111 222 333\n"
        self.assertEqual(self._clean(raw), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
