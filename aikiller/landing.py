"""랜딩 페이지 — `/` 에 서빙되는 소개 화면.

도구 자체는 `/app` 에 있다. 이 파일은 HTML 문자열만 담는다.
디자인 토큰(색·타이포)은 web.py 의 앱 화면과 같은 것을 쓴다.

여기 적힌 숫자는 전부 이 저장소에서 실제로 측정한 값이다. 마케팅 문구를
쓰지 않는 것이 이 도구의 신뢰도 자체다 — 상용 도구들이 "정확도 98%"라고
광고하면서 근거를 대지 않는 것과 반대로 간다.
"""

from __future__ import annotations

LANDING_PAGE = """<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ai킬러 — 한국어 AI 문체 탐지 + 다듬기</title>
<meta name="description" content="한국어 글의 AI 문체를 점수와 근거로 보여주고, 같은 규칙으로 고쳐 줍니다. 74개 패턴 · 무의존성 · 로컬 실행.">
<style>
:root{
  --bg:#fbfbfa; --panel:#fff; --ink:#1f1e1c; --muted:#6b6862; --line:#e6e3dd;
  --accent:#3d5a80; --hi:#c1121f; --mid:#d68c26; --lo:#3f7d52;
  --code:#f4f2ee; --hero:#f2f0eb;
}
@media (prefers-color-scheme: dark){
  :root{--bg:#171614; --panel:#201f1c; --ink:#eceae5; --muted:#9b968d;
        --line:#332f2a; --accent:#8fb3d9; --hi:#e2645c; --mid:#e0a63f;
        --lo:#6fb583; --code:#26241f; --hero:#1c1b18;}
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.7 -apple-system,BlinkMacSystemFont,"Pretendard","Apple SD Gothic Neo",
  "Noto Sans KR",sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit}
.wrap{max-width:1000px;margin:0 auto;padding:0 22px}

/* ---------- nav ---------- */
nav{position:sticky;top:0;z-index:30;background:color-mix(in srgb,var(--bg) 88%,transparent);
  backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
nav .wrap{display:flex;align-items:center;gap:20px;height:58px}
nav b{font-size:17px;letter-spacing:-.02em}
nav .links{display:flex;gap:19px;margin-left:auto;font-size:14px;color:var(--muted)}
nav .links a{text-decoration:none}
nav .links a:hover{color:var(--ink)}
@media(max-width:640px){nav .links a:not(.cta){display:none}}
.cta{display:inline-block;padding:8px 17px;border-radius:8px;background:var(--accent);
  color:#fff!important;font-weight:600;text-decoration:none;font-size:14px;
  border:1px solid var(--accent)}
.cta:hover{opacity:.9}
.cta.ghost{background:transparent;color:var(--accent)!important}

/* ---------- hero ---------- */
.hero{background:var(--hero);border-bottom:1px solid var(--line);
  padding:84px 0 76px;text-align:center}
.hero h1{font-size:clamp(30px,5.4vw,48px);line-height:1.22;letter-spacing:-.033em;
  margin:0 0 20px;font-weight:800}
.hero h1 em{font-style:normal;color:var(--accent)}
.hero p{font-size:clamp(16px,2.2vw,19px);color:var(--muted);max-width:620px;
  margin:0 auto 32px;line-height:1.65}
.hero .btns{display:flex;gap:11px;justify-content:center;flex-wrap:wrap}
.hero .note{margin-top:26px;font-size:13px;color:var(--muted)}

/* ---------- sections ---------- */
section{padding:74px 0;border-bottom:1px solid var(--line)}
section:last-of-type{border-bottom:0}
h2{font-size:clamp(21px,3vw,27px);letter-spacing:-.022em;margin:0 0 12px;font-weight:700}
.lede{color:var(--muted);margin:0 0 34px;max-width:640px;font-size:15.5px}
h3{font-size:15px;margin:0 0 7px;font-weight:700}

/* ---------- demo ---------- */
.demo{background:var(--panel);border:1px solid var(--line);border-radius:13px;
  overflow:hidden}
.demo .bar{display:flex;align-items:center;gap:8px;padding:11px 15px;
  border-bottom:1px solid var(--line);background:var(--code);font-size:12.5px;
  color:var(--muted)}
.demo .dots{display:flex;gap:5px}
.demo .dots i{width:9px;height:9px;border-radius:50%;background:var(--line)}
.demo .body{display:grid;grid-template-columns:1.25fr 1fr}
@media(max-width:760px){.demo .body{grid-template-columns:1fr}}
.demo .txt{padding:20px;font-size:14px;line-height:2.05;border-right:1px solid var(--line)}
@media(max-width:760px){.demo .txt{border-right:0;border-bottom:1px solid var(--line)}}
.demo mark{background:none;padding:2px 0;border-radius:3px;color:inherit}
/* .demo mark 가 (0,1,1) 이라 .m-hi (0,1,0) 를 이긴다. 같은 컨텍스트로 올린다. */
.demo mark.m-hi{background:color-mix(in srgb,var(--hi) 30%,transparent)}
.demo mark.m-md{background:color-mix(in srgb,var(--mid) 26%,transparent)}
.demo .side{padding:20px}
.gauge{display:flex;align-items:baseline;gap:9px;margin-bottom:5px}
.gauge b{font-size:40px;letter-spacing:-.035em;color:var(--hi);
  font-variant-numeric:tabular-nums}
.pill{font-size:12px;font-weight:700;padding:3px 10px;border-radius:20px;
  background:color-mix(in srgb,var(--hi) 15%,transparent);color:var(--hi)}
.meter{height:6px;background:var(--code);border-radius:4px;overflow:hidden;margin:9px 0 18px}
.meter i{display:block;height:100%;background:var(--hi);border-radius:4px}
.ev{padding:8px 0;border-bottom:1px solid var(--line);font-size:13px}
.ev:last-child{border-bottom:0}
.ev .k{display:flex;align-items:center;gap:7px}
.ev .d{color:var(--muted);font-size:12px;margin-top:2px}
.tag{font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;
  background:var(--code);color:var(--muted)}
.tag.real{background:color-mix(in srgb,var(--lo) 18%,transparent);color:var(--lo)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--hi);flex:none}

/* ---------- separation chart ---------- */
.chart{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:22px}
.row{display:grid;grid-template-columns:110px 1fr 52px;align-items:center;gap:12px;
  padding:5px 0;font-size:13.5px}
.row .track{height:19px;background:var(--code);border-radius:5px;overflow:hidden}
.row .fill{height:100%;border-radius:5px}
.row .num{text-align:right;font-variant-numeric:tabular-nums;color:var(--muted);
  font-size:12.5px}
.row.ai .num{color:var(--hi);font-weight:700}
.sep{height:1px;background:var(--line);margin:13px 0}
.legend{display:flex;gap:18px;font-size:12.5px;color:var(--muted);margin-top:15px;
  flex-wrap:wrap}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;
  margin-right:5px;vertical-align:-1px}

/* ---------- grids ---------- */
.grid{display:grid;gap:15px}
.g3{grid-template-columns:repeat(3,1fr)}
.g2{grid-template-columns:repeat(2,1fr)}
.g4{grid-template-columns:repeat(4,1fr)}
@media(max-width:820px){.g3,.g4{grid-template-columns:repeat(2,1fr)}}
@media(max-width:560px){.g2,.g3,.g4{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:18px}
.card p{margin:0;color:var(--muted);font-size:13.5px;line-height:1.62}
.card .n{font-size:11px;font-weight:700;color:var(--accent);letter-spacing:.09em;
  margin-bottom:9px}
.stat{text-align:center;padding:17px 12px}
.stat b{display:block;font-size:28px;letter-spacing:-.03em;line-height:1.15}
.stat span{font-size:12.5px;color:var(--muted)}

/* ---------- layers ---------- */
.layer{display:grid;grid-template-columns:64px 1fr 92px;gap:15px;align-items:start;
  padding:15px 0;border-bottom:1px solid var(--line)}
.layer:last-child{border-bottom:0}
@media(max-width:600px){.layer{grid-template-columns:52px 1fr}.layer .cal{display:none}}
.layer .id{font-weight:800;font-size:15px;color:var(--accent)}
.layer .cal{font-size:11.5px;text-align:right;color:var(--muted)}
.layer .cal.ok{color:var(--lo);font-weight:700}

/* ---------- limits ---------- */
.limits{background:var(--code);border-radius:12px;padding:26px;
  border-left:3px solid var(--mid)}
.limits ul{margin:0;padding-left:19px}
.limits li{margin:9px 0;font-size:14.5px;color:var(--muted);line-height:1.62}
.limits li b{color:var(--ink)}

/* ---------- code ---------- */
pre{background:var(--code);border:1px solid var(--line);border-radius:9px;
  padding:14px 16px;overflow-x:auto;font:13px/1.6 ui-monospace,SFMono-Regular,
  Menlo,monospace;margin:0 0 11px}
code{font:13px ui-monospace,SFMono-Regular,Menlo,monospace}
.pat{display:inline-block;font:11.5px ui-monospace,monospace;background:var(--code);
  border:1px solid var(--line);border-radius:5px;padding:2px 7px;margin:0 4px 6px 0;
  color:var(--muted)}
footer{padding:44px 0 60px;color:var(--muted);font-size:13px;line-height:1.75}
footer a{color:var(--accent)}
</style></head><body>

<nav><div class="wrap">
  <b>ai킬러</b>
  <div class="links">
    <a href="#how">작동 원리</a>
    <a href="#patterns">패턴</a>
    <a href="#limits">한계</a>
    <a href="#start">설치</a>
    <a class="cta" href="/app">검사하기</a>
  </div>
</div></nav>

<div class="hero"><div class="wrap">
  <h1>AI가 썼는지가 아니라<br><em>왜 그렇게 보이는지</em>를 말합니다</h1>
  <p>한국어 글의 AI 문체를 문장 단위로 짚고, 근거를 대고,
     같은 규칙으로 고쳐 줍니다. 판정이 아니라 교정 도구입니다.</p>
  <div class="btns">
    <a class="cta" href="/app">글 검사하기</a>
    <a class="cta ghost" href="#how">원리 보기</a>
  </div>
  <div class="note">설치 불필요 · 의존성 없음 · 글이 서버에 저장되지 않습니다</div>
</div></div>

<section><div class="wrap">
  <h2>이렇게 보입니다</h2>
  <p class="lede">점수 하나만 던지지 않습니다. 어느 문장이 왜 걸렸는지 패턴 ID까지 나옵니다.</p>

  <div class="demo">
    <div class="bar"><div class="dots"><i></i><i></i><i></i></div>
      &nbsp;AI 에세이 · 406자 · 장르 에세이</div>
    <div class="body">
      <div class="txt">
        <mark class="m-md" title="61점 · '급변하는 현대사회' 서두">급변하는 현대 사회에서, 인공지능 기술은 우리의 삶에 매우 중요한 영향을 미치고 있다.</mark>
        <mark class="m-hi" title="74점 · 무생물 주어">이 연구는 인공지능이 노동 시장에 미치는 영향을 보여준다.</mark>
        <mark class="m-hi" title="85점 · '-들' 남용, 다중 완곡">많은 전문가들이 지적하듯이, 자동화를 통해 생산성이 크게 향상될 수 있을 것으로 보인다.</mark>
        <mark class="m-hi" title="94점 · 부정대구">중요한 것은 속도가 아니라 방향이다.</mark>
        <mark class="m-md" title="62점 · 기계적 병렬">첫째, 재교육 프로그램이 확대되어져야 한다.</mark>
        <mark class="m-hi" title="94점 · '결론적으로', '-들' 남용">결론적으로, 다양한 이해관계자들이 협력해야 하며, 균형 잡힌 접근이 필요하다.</mark>
      </div>
      <div class="side">
        <div class="gauge"><b>84.8</b><span style="color:var(--muted);font-size:13px">/ 100</span>
          <span class="pill">높음</span></div>
        <div class="meter"><i style="width:84.8%"></i></div>
        <div class="ev"><div class="k"><span class="dot"></span>
          <span class="tag real">L1 실측</span> 연결어미 뒤 쉼표 비율</div>
          <div class="d">z=+3.00 (AI 쪽)</div></div>
        <div class="ev"><div class="k"><span class="dot"></span>
          <span class="tag">L2 추정</span> [C-8b] 부정대구</div>
          <div class="d">2회 · 사람 24편 0건 vs AI 27건</div></div>
        <div class="ev"><div class="k"><span class="dot"></span>
          <span class="tag">L2 추정</span> [D-8a] 분열문</div>
          <div class="d">2회 · 사람 0.09 vs AI 0.92 (10배)</div></div>
        <div class="ev"><div class="k"><span class="dot"></span>
          <span class="tag">L2 추정</span> [A-8] 이중 피동</div>
          <div class="d">1회 · '되어져야' → '되어야'</div></div>
      </div>
    </div>
  </div>
</div></section>

<section><div class="wrap">
  <h2>사람 글과 얼마나 갈리나</h2>
  <p class="lede">레지스터 9종을 직접 넣어 잰 값입니다. 표본이 9건뿐이라
     통계적 주장은 아니고, 지금 상태를 그대로 보여드리는 것입니다.</p>

  <div class="chart">
    <div class="row"><span>개인 블로그</span>
      <div class="track"><div class="fill" style="width:6.6%;background:var(--lo)"></div></div>
      <span class="num">6.6</span></div>
    <div class="row"><span>신문 기사</span>
      <div class="track"><div class="fill" style="width:7.8%;background:var(--lo)"></div></div>
      <span class="num">7.8</span></div>
    <div class="row"><span>기술 문서</span>
      <div class="track"><div class="fill" style="width:8.7%;background:var(--lo)"></div></div>
      <span class="num">8.7</span></div>
    <div class="row"><span>학술 논문</span>
      <div class="track"><div class="fill" style="width:9.4%;background:var(--lo)"></div></div>
      <span class="num">9.4</span></div>
    <div class="row"><span>문학 에세이</span>
      <div class="track"><div class="fill" style="width:9.8%;background:var(--lo)"></div></div>
      <span class="num">9.8</span></div>
    <div class="row"><span>법률 문서</span>
      <div class="track"><div class="fill" style="width:10%;background:var(--lo)"></div></div>
      <span class="num">10.0</span></div>
    <div class="row"><span>관공서 공문</span>
      <div class="track"><div class="fill" style="width:10.1%;background:var(--lo)"></div></div>
      <span class="num">10.1</span></div>
    <div class="sep"></div>
    <div class="row ai"><span>AI 칼럼</span>
      <div class="track"><div class="fill" style="width:39.8%;background:var(--mid)"></div></div>
      <span class="num">39.8</span></div>
    <div class="row ai"><span>AI 에세이</span>
      <div class="track"><div class="fill" style="width:84.8%;background:var(--hi)"></div></div>
      <span class="num">84.8</span></div>
    <div class="legend">
      <span><i style="background:var(--lo)"></i>사람이 쓴 글</span>
      <span><i style="background:var(--mid)"></i>AI · 잘 쓴 칼럼</span>
      <span><i style="background:var(--hi)"></i>AI · 전형적 에세이</span>
    </div>
  </div>

  <div class="grid g4" style="margin-top:20px">
    <div class="card stat"><b>98.6 → 9.4</b><span>학술 논문 오탐</span></div>
    <div class="card stat"><b>94.5 → 10.1</b><span>관공서 공문 오탐</span></div>
    <div class="card stat"><b>90.8 → 8.7</b><span>기술 문서 오탐</span></div>
    <div class="card stat"><b>85.9 → 7.8</b><span>신문 기사 오탐</span></div>
  </div>
  <p class="lede" style="margin:16px 0 0;font-size:14px">
    검수 전에는 격식체 한국어를 체계적으로 AI로 몰았습니다. 원인은 깨진 지표 하나,
    실측이 역전된 가중치, 그리고 <b>"사람이라는 증거"를 세지 않은 것</b>이었습니다.
  </p>
</div></section>

<section id="how"><div class="wrap">
  <h2>어떻게 판단하나</h2>
  <p class="lede">네 계층의 증거를 모아 하나의 점수로 합칩니다.
     각 계층이 실측 근거를 갖고 있는지 아닌지를 화면에 그대로 표시합니다.</p>

  <div class="card">
    <div class="layer">
      <div class="id">L1</div>
      <div><h3>통계 지표</h3><p>쉼표 계열 4종. 한국어는 연결어미 뒤에 쉼표를
        잘 안 찍는데 AI는 영어 습관대로 찍습니다.</p></div>
      <div class="cal ok">실측 기준선</div>
    </div>
    <div class="layer">
      <div class="id">L2</div>
      <div><h3>패턴 밀도</h3><p>74개 AI 티 패턴을 1,000자당 가중 밀도로 환산.
        번역투·AI 관용구·구조 습관·hedging 등 10개 카테고리.</p></div>
      <div class="cal">가중치 추정</div>
    </div>
    <div class="layer">
      <div class="id">L3</div>
      <div><h3>리듬</h3><p>문장 길이 변동계수, 종결어미 다양성, 장문 부재.
        AI는 짧은 문장만 찍어내고 긴 호흡을 못 만듭니다.</p></div>
      <div class="cal">휴리스틱</div>
    </div>
    <div class="layer">
      <div class="id">L4</div>
      <div><h3>사람이라는 증거 <span style="color:var(--lo)">— 점수를 깎습니다</span></h3>
        <p>"솔직히", "당시", "힘들었다", 문두 "또,". AI 코퍼스에서 0건으로
        관측된 표현들입니다. 이게 격식체 오탐을 막는 핵심입니다.</p></div>
      <div class="cal">가중치 추정</div>
    </div>
  </div>

  <div class="grid g3" style="margin-top:26px">
    <div class="card"><div class="n">차별점 01</div>
      <h3>탐지와 다듬기가 한 몸</h3>
      <p>같은 패턴 레지스트리를 씁니다. "이게 AI 티다"라고 짚은 규칙이
         그대로 "이렇게 고쳐라"가 됩니다. 두 벌로 관리하지 않습니다.</p></div>
    <div class="card"><div class="n">차별점 02</div>
      <h3>HWP를 읽습니다</h3>
      <p>hwp 바이너리와 hwpx를 직접 파싱합니다. 해외 도구가 못 하는
         지점이고, 한국에서 실제로 필요한 기능입니다.</p></div>
    <div class="card"><div class="n">차별점 03</div>
      <h3>모르는 건 모른다고</h3>
      <p>150자 미만은 점수를 안 냅니다. 캘리브레이션 안 된 값은
         "추정"이라고 표시합니다. 근거 없는 가중치는 낮춥니다.</p></div>
  </div>
</div></section>

<section id="patterns"><div class="wrap">
  <h2>74개 패턴 + 역방향 7</h2>
  <p class="lede">한국어 AI 글의 티는 대부분 <b>영어 번역투</b>에서 나옵니다.
     각 패턴에는 실측 근거를 함께 적어 뒀습니다.</p>

  <div class="grid g2">
    <div class="card"><h3>가장 강한 신호</h3>
      <p style="margin-bottom:11px">부정대구 <b style="color:var(--ink)">"A가 아니라 B다"</b> —
        AI 5.8 vs 인간 0.6 (9.2배, p&lt;0.0001). 사람 24편에서 0건.</p>
      <span class="pat">C-8b 부정대구</span>
      <span class="pat">D-8a 분열문 10배</span>
      <span class="pat">D-9a ~로 이어진다</span>
      <span class="pat">D-12 과제도 남아 있다</span>
      <span class="pat">D-14a 감각 술어</span>
    </div>
    <div class="card"><h3>낮춘 신호</h3>
      <p style="margin-bottom:11px">실측이 <b style="color:var(--ink)">역전된</b> 것들.
        대명사는 사람이 8배 더 씁니다. 통념과 반대라 가중치를 눌렀습니다.</p>
      <span class="pat">A-16 대명사 ×0.13</span>
      <span class="pat">A-2 ~를 통해 (기각)</span>
      <span class="pat">A-1 ~에 대해 (사람 3배)</span>
      <span class="pat">I-1 것이다 (사람 2배)</span>
      <span class="pat">D-4 hype 어휘 1.3배</span>
    </div>
  </div>

  <div class="grid g4" style="margin-top:15px">
    <div class="card"><div class="n">A · 20</div><h3>번역투</h3>
      <p>이중피동, 가지고 있다, 피동 진행, 무생물 주어</p></div>
    <div class="card"><div class="n">D · 22</div><h3>AI 관용구</h3>
      <p>결론적으로, 시사하는 바가 크다, ~하는 이유다</p></div>
    <div class="card"><div class="n">C · 10</div><h3>구조</h3>
      <p>부정대구, 첫째/둘째, 연결어미 뒤 쉼표, 이모지</p></div>
    <div class="card"><div class="n">G · 4</div><h3>hedging</h3>
      <p>다중 완곡, 사료된다, 안전 균형 lexicon</p></div>
    <div class="card"><div class="n">H · 4</div><h3>접속사</h3>
      <p>문두 접속사, 이는~ 반복, 즉 남발</p></div>
    <div class="card"><div class="n">I · 5</div><h3>형식명사</h3>
      <p>것이다 종결, ~할 필요가 있다</p></div>
    <div class="card"><div class="n">F · 4</div><h3>수식·중복</h3>
      <p>정도부사, ~적 N 체인, 범용 정책동사</p></div>
    <div class="card"><div class="n">B J · 5</div><h3>영어·장식</h3>
      <p>괄호 병기, 대시 남용, 괄호 부연</p></div>
  </div>
</div></section>

<section><div class="wrap">
  <h2>고칠 때는 안전장치가 붙습니다</h2>
  <p class="lede">다듬기는 규칙 기반이라 결정적입니다. LLM을 안 부르므로
     없던 주장이 생기거나 사실이 바뀔 수 없습니다.</p>
  <div class="grid g2">
    <div class="card"><div class="n">01</div><h3>보호 구간</h3>
      <p>코드블록·인라인코드·직접인용·URL·인용블록은 마스킹 후 복원합니다.
         절대 수정되지 않습니다.</p></div>
    <div class="card"><div class="n">02</div><h3>강도 3단계</h3>
      <p><code>safe</code>는 문법적으로 의미 불변이 보장되는 것만.
         판단이 서지 않는 규칙은 탐지 전용으로 둡니다.</p></div>
    <div class="card"><div class="n">03</div><h3>변경률 게이트</h3>
      <p>30% 넘으면 경고, 50% 넘으면 중단하고 원문을 돌려줍니다.
         과다듬기는 의미 드리프트로 이어집니다.</p></div>
    <div class="card"><div class="n">04</div><h3>경어법 유지</h3>
      <p><code>습니다</code>체를 반말로 떨어뜨리지 않습니다.
         조사도 종성에 맞춰 다시 고릅니다.</p></div>
  </div>
</div></section>

<section id="limits"><div class="wrap">
  <h2>못 하는 것</h2>
  <p class="lede">이 항목이 이 도구의 신뢰도 그 자체입니다.
     상용 도구들이 광고하는 "정확도 98%"는 자체 테스트셋 기준이라
     실사용 성능을 말해 주지 않습니다.</p>

  <div class="limits"><ul>
    <li><b>융합 가중치가 아직 실측 피팅되지 않았습니다.</b> 점수는 상대
      비교용입니다. 화면에 항상 "미캘리브레이션"이라고 표시됩니다.</li>
    <li><b>짧은 글은 원리적으로 판정할 수 없습니다.</b> 150자 미만은
      점수 대신 "판정 불가"를 반환합니다.</li>
    <li><b>휴머나이저를 통과한 글은 못 잡습니다.</b> 이 저장소의 다듬기 기능이
      곧 자기 자신에 대한 공격입니다. 창과 방패 중 방패가 이기는 국면입니다.</li>
    <li><b>패턴 다수가 추정 가중치입니다.</b> 실측 근거가 있는 것만
      화면에 "실측" 배지가 붙습니다.</li>
    <li><b>"AI가 썼다"를 단정하지 않습니다.</b> AI 문체 지표 점수와 근거를 냅니다.
      징계·평가·채용의 단독 근거로 쓰지 마세요.</li>
  </ul></div>
</div></section>

<section id="start"><div class="wrap">
  <h2>쓰는 법</h2>
  <p class="lede">파이썬 표준 라이브러리만 씁니다. 설치할 패키지가 없습니다.</p>
  <div class="grid g2">
    <div>
      <h3 style="margin-bottom:9px">설치</h3>
      <pre>./install.sh</pre>
      <p style="color:var(--muted);font-size:13.5px;margin:0 0 24px">
        <code>~/.local/bin/aikiller</code> 런처 하나만 만듭니다.
        제거는 <code>./install.sh --uninstall</code>.</p>
      <h3 style="margin-bottom:9px">실행</h3>
      <pre>aikiller</pre>
      <p style="color:var(--muted);font-size:13.5px;margin:0">
        브라우저가 자동으로 열립니다.</p>
    </div>
    <div>
      <h3 style="margin-bottom:9px">터미널에서</h3>
      <pre>aikiller detect 자소서.hwp
aikiller humanize 글.txt --level aggressive --diff
aikiller clip
aikiller history</pre>
      <h3 style="margin-bottom:9px;margin-top:20px">웹 UI 단축키</h3>
      <p style="color:var(--muted);font-size:13.5px;margin:0">
        <code>⌘⏎</code> 탐지 · <code>⌘⇧⏎</code> 다듬기 · <code>⌘K</code> 비우기<br>
        입력이 멈추면 자동으로 분석합니다. 파일은 끌어다 놓으면 열립니다.</p>
    </div>
  </div>

  <div style="margin-top:34px;text-align:center">
    <a class="cta" href="/app" style="padding:12px 26px;font-size:15px">지금 검사해 보기</a>
  </div>
</div></section>

<footer><div class="wrap">
  <b>ai킬러</b> — 한국어 AI 문체 탐지 + 다듬기<br>
  hwp · hwpx · docx · pdf · txt 지원 · 글이 서버에 저장되지 않습니다 ·
  분석 기록은 내 컴퓨터의 <code>~/.aikiller/</code> 에만 남습니다<br><br>
  L1 계층의 사람/AI 실측 극값은 한국어 AI 텍스트 판별 연구
  <b>KatFish</b>(Park et al., 사람 470편 vs LLM 1,624편)의 보고 수치입니다.
  패턴 분류 체계는 <a href="https://github.com/epoko77-ai/im-not-ai">Humanize KR</a>의
  한국어 AI 티 taxonomy를 참고했습니다. MIT 라이선스.
</div></footer>

</body></html>
"""
