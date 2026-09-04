"""웹 UI — 표준 라이브러리 http.server 기반. 설치 없이 바로 뜬다.

    python3 -m aikiller serve --port 8000

라우트
------
    GET  /                 랜딩 페이지 (landing.py)
    GET  /app              도구 화면 (HTML/CSS/JS 인라인)
    POST /api/detect       {text, genre}          -> 탐지 리포트
    POST /api/humanize     {text, level, genre}   -> 다듬기 결과
    POST /api/parse        {filename, data_b64}   -> 문서에서 텍스트 추출
    GET  /api/patterns     패턴 레지스트리 덤프
    GET  /api/history      최근 분석 기록 (로컬 SQLite)
    GET  /api/history/N    기록 한 건 (원문 포함)
    DELETE /api/history/N  기록 한 건 삭제
    DELETE /api/history    전체 삭제

프로덕션 전환 메모
------------------
동시 요청이 늘면 FastAPI + uvicorn으로 옮기세요. 핸들러 로직은 그대로
`analyze()` / `humanize()` 호출이라 이식이 얼마 안 걸립니다. 지금 stdlib을
쓰는 이유는 이 저장소 전체가 무의존성이기 때문입니다.

보안 메모
---------
기본 바인딩은 127.0.0.1입니다. `--host 0.0.0.0`으로 외부에 열 때는 앞에
리버스 프록시를 두고 업로드 크기 제한·인증을 붙이세요.

개인용 기록
-----------
분석 기록은 `~/.aikiller/history.db`(로컬 SQLite)에만 남습니다. 네트워크로
나가지 않습니다. `AIKILLER_NO_HISTORY=1`로 끄거나 UI에서 지울 수 있습니다.
**남의 글을 받는 서비스로 배포할 때는 반드시 꺼야 합니다.**
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import threading
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import history, parsers
from .landing import LANDING_PAGE
from .detect import analyze
from .humanize import humanize
from .patterns import CATEGORIES, PATTERNS

MAX_BODY = 8 * 1024 * 1024   # 8MB
REQUEST_TIMEOUT = 30         # 초. 없으면 slowloris로 워커가 영구히 묶인다
MAX_CONCURRENT = 8           # 동시 분석 요청 수. 압축 해제 메모리 스파이크 상한

# 무거운 작업(파싱·분석)에 들어가는 요청만 제한한다. 정적 페이지는 통과.
_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT)


def _int_or_none(v: str) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 페이지
# ---------------------------------------------------------------------------

APP_PAGE = """<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ai킬러 — 한국어 AI 문체 탐지 + 다듬기</title>
<style>
:root{
  --bg:#fbfbfa; --panel:#fff; --ink:#1f1e1c; --muted:#6b6862; --line:#e6e3dd;
  --accent:#3d5a80; --hi:#c1121f; --mid:#d68c26; --lo:#3f7d52;
  --code:#f4f2ee;
}
@media (prefers-color-scheme: dark){
  :root{--bg:#171614; --panel:#201f1c; --ink:#eceae5; --muted:#9b968d;
        --line:#332f2a; --accent:#8fb3d9; --hi:#e2645c; --mid:#e0a63f;
        --lo:#6fb583; --code:#26241f;}
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.65 -apple-system,BlinkMacSystemFont,"Pretendard","Apple SD Gothic Neo",
  "Noto Sans KR",sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 80px}
header{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:6px}
h1{font-size:21px;margin:0;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:13px}
.warn{margin:14px 0 22px;padding:10px 14px;border-left:3px solid var(--mid);
  background:var(--code);border-radius:0 6px 6px 0;font-size:13px;color:var(--muted)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media (max-width:900px){.cols{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px}
textarea{width:100%;min-height:300px;resize:vertical;padding:13px;border-radius:8px;
  border:1px solid var(--line);background:var(--bg);color:var(--ink);
  font:14px/1.7 inherit}
textarea:focus{outline:2px solid var(--accent);outline-offset:-1px}
.row{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-top:12px}
button{padding:9px 17px;border-radius:7px;border:1px solid var(--accent);
  background:var(--accent);color:#fff;font:600 14px inherit;cursor:pointer}
button.ghost{background:transparent;color:var(--accent)}
button:disabled{opacity:.45;cursor:default}
select,input[type=file]{padding:7px 9px;border-radius:7px;border:1px solid var(--line);
  background:var(--bg);color:var(--ink);font:14px inherit}
label.file{padding:8px 13px;border:1px dashed var(--line);border-radius:7px;
  cursor:pointer;font-size:13px;color:var(--muted)}
label.file input{display:none}
.score{display:flex;align-items:baseline;gap:12px;margin-bottom:4px}
.score b{font-size:44px;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.band{font-size:13px;font-weight:700;padding:3px 10px;border-radius:20px}
.band.high{background:color-mix(in srgb,var(--hi) 16%,transparent);color:var(--hi)}
.band.medium{background:color-mix(in srgb,var(--mid) 18%,transparent);color:var(--mid)}
.band.low{background:color-mix(in srgb,var(--lo) 16%,transparent);color:var(--lo)}
.meter{height:7px;background:var(--code);border-radius:4px;overflow:hidden;margin:10px 0 4px}
.meter i{display:block;height:100%;border-radius:4px;transition:width .35s}
.meta{color:var(--muted);font-size:12.5px}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);
  margin:22px 0 10px;font-weight:700}
.sig{padding:9px 0;border-bottom:1px solid var(--line)}
.sig:last-child{border-bottom:0}
.sig .t{display:flex;gap:8px;align-items:center;font-size:14px}
.sig .d{color:var(--muted);font-size:12.5px;margin-top:2px}
.tag{font-size:10.5px;font-weight:700;padding:2px 6px;border-radius:4px;
  background:var(--code);color:var(--muted);letter-spacing:.03em}
.tag.real{background:color-mix(in srgb,var(--lo) 18%,transparent);color:var(--lo)}
.dot{width:8px;height:8px;border-radius:50%;flex:none}
.heat{line-height:2.05;font-size:14.5px;white-space:pre-wrap;word-break:break-word}
.heat mark{background:none;padding:1px 0;border-radius:3px;cursor:help}
.layers{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:16px}
.layers div{background:var(--code);border-radius:7px;padding:10px 12px}
.layers small{display:block;color:var(--muted);font-size:11px;margin-bottom:3px}
.layers b{font-size:17px;font-variant-numeric:tabular-nums}
.note{color:var(--muted);font-size:12.5px;margin-top:8px;padding-left:14px;
  text-indent:-14px}
.chg{font-size:13px;padding:7px 0;border-bottom:1px solid var(--line)}
.chg code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:12px}
.del{color:var(--hi)} .ins{color:var(--lo)}
.empty{color:var(--muted);font-size:13.5px;padding:30px 0;text-align:center}
.spin{display:inline-block;width:13px;height:13px;border:2px solid var(--line);
  border-top-color:var(--accent);border-radius:50%;animation:s .7s linear infinite}
@keyframes s{to{transform:rotate(360deg)}}
/* --- 개인용 편의 --- */
.tools{display:flex;gap:8px;align-items:center;margin-left:auto}
.ico{padding:6px 11px;border-radius:7px;border:1px solid var(--line);
  background:transparent;color:var(--muted);font:13px inherit;cursor:pointer}
.ico:hover{color:var(--ink);border-color:var(--accent)}
.ico.on{color:var(--accent);border-color:var(--accent)}
textarea.drop{outline:2px dashed var(--accent);outline-offset:-4px;
  background:color-mix(in srgb,var(--accent) 7%,var(--bg))}
.count{margin-left:auto;font-size:12px;color:var(--muted);
  font-variant-numeric:tabular-nums}
#hist{position:fixed;top:0;right:0;bottom:0;width:330px;background:var(--panel);
  border-left:1px solid var(--line);transform:translateX(100%);
  transition:transform .22s ease;overflow-y:auto;padding:16px;z-index:20;
  box-shadow:-12px 0 34px rgba(0,0,0,.10)}
#hist.open{transform:none}
#hist h3{margin-top:0}
.hrow{padding:10px;border-radius:8px;cursor:pointer;border:1px solid transparent;
  display:flex;gap:10px;align-items:flex-start}
.hrow:hover{background:var(--code);border-color:var(--line)}
.hrow b{font-size:13px;font-variant-numeric:tabular-nums;flex:none;width:42px;
  text-align:right}
.hrow .p{font-size:12.5px;line-height:1.5;color:var(--ink);
  overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.hrow .m{font-size:11px;color:var(--muted);margin-top:3px}
.hrow .x{opacity:0;color:var(--muted);flex:none;padding:0 3px;background:none;
  border:0;cursor:pointer;font-size:15px}
.hrow:hover .x{opacity:.6}
.hrow .x:hover{opacity:1;color:var(--hi)}
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.28);z-index:19;display:none}
.scrim.open{display:block}
.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%) translateY(14px);
  background:var(--ink);color:var(--bg);padding:9px 17px;border-radius:8px;
  font-size:13px;opacity:0;transition:.2s;pointer-events:none;z-index:40}
.toast.show{opacity:1;transform:translateX(-50%)}
kbd{font:11px ui-monospace,monospace;background:var(--code);border:1px solid var(--line);
  border-bottom-width:2px;border-radius:4px;padding:1px 5px;color:var(--muted)}
</style></head><body><div class="wrap">

<header>
  <h1><a href="/" style="color:inherit;text-decoration:none">ai킬러</a></h1>
  <span class="sub">한국어 AI 문체 탐지 + 다듬기 · <a href="/" style="color:var(--accent)">소개</a></span>
  <div class="tools">
    <button class="ico" id="btn-auto" title="입력이 멈추면 자동으로 검사합니다">자동 검사</button>
    <button class="ico" id="btn-hist">기록</button>
  </div>
</header>
<div class="warn" id="disclaimer">
  이 도구는 “AI가 썼다”를 단정하지 않습니다. <b>AI 문체 지표 점수와 근거</b>를 냅니다.
  징계·평가·채용의 단독 근거로 쓰지 마세요.
</div>

<div class="cols">
  <div class="panel">
    <textarea id="text" placeholder="검사할 한국어 글을 붙여넣으세요. 150자 미만은 판정하지 않습니다."></textarea>
    <div class="row">
      <select id="genre">
        <option value="essay">에세이</option>
        <option value="report">보고서</option>
        <option value="column">칼럼</option>
        <option value="blog">블로그</option>
        <option value="abstract">초록</option>
      </select>
      <label class="file">파일 열기 · 끌어다 놓기
        <input type="file" id="file" accept=".txt,.md,.docx,.hwpx,.hwp,.pdf">
      </label>
      <span class="meta" id="fname"></span>
      <span class="count" id="count">0자</span>
    </div>
    <div class="row">
      <button id="btn-detect">검사</button>
      <select id="level">
        <option value="safe">약하게 — 확실한 것만</option>
        <option value="moderate" selected>보통 — 기본값</option>
        <option value="aggressive">강하게 — 문체까지</option>
      </select>
      <button class="ghost" id="btn-hum">다듬기</button>
      <span class="meta" id="status"></span>
    </div>
    <div class="meta" style="margin-top:9px">
      <kbd>⌘⏎</kbd> 검사 · <kbd>⌘⇧⏎</kbd> 다듬기 · <kbd>⌘K</kbd> 비우기
    </div>
  </div>

  <div class="panel" id="out">
    <div class="empty">왼쪽에 글을 넣고 <b>검사</b>를 누르세요.<br>
      <span style="font-size:12.5px">파일을 끌어다 놓아도 됩니다 (hwp · hwpx · docx · pdf · txt)</span>
    </div>
  </div>
</div>
</div>

<div class="scrim" id="scrim"></div>
<aside id="hist">
  <h3 style="display:flex;align-items:center">기록
    <button class="ico" id="btn-clear" style="margin-left:auto;padding:4px 9px">전체 삭제</button>
  </h3>
  <div id="hist-list"><div class="meta">기록이 없습니다.</div></div>
  <div class="meta" style="margin-top:16px;line-height:1.6">
    기록은 <code>~/.aikiller/history.db</code>에만 저장됩니다.<br>
    네트워크로 나가지 않습니다.
  </div>
</aside>
<div class="toast" id="toast"></div>

<script>
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const BAND = {high:'높음', medium:'중간', low:'낮음'};
const CONF = {insufficient:'판정 불가', low:'낮음', normal:'보통'};

function color(score){
  if(score >= 70) return 'var(--hi)';
  if(score >= 40) return 'var(--mid)';
  return 'var(--lo)';
}
function busy(on, msg){
  $('#btn-detect').disabled = on; $('#btn-hum').disabled = on;
  $('#status').innerHTML = on ? '<span class="spin"></span> ' + (msg||'') : '';
}
async function post(path, body){
  const r = await fetch(path, {method:'POST', headers:{'content-type':'application/json'},
                              body: JSON.stringify(body)});
  const j = await r.json();
  if(!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
  return j;
}

$('#file').addEventListener('change', e => {
  const f = e.target.files[0]; if(f) readFile(f);
});

function heatmap(text, sentences){
  let html = '', cur = 0;
  for(const s of sentences){
    if(s.start > cur) html += esc(text.slice(cur, s.start));
    const a = Math.min(s.score/100*0.42, 0.42);
    const title = s.hit_ids.length ? s.score.toFixed(0)+'점 · '+[...new Set(s.hit_names)].join(', ')
                                   : s.score.toFixed(0)+'점';
    html += '<mark style="background:color-mix(in srgb,'+color(s.score)+' '
         + (a*100).toFixed(0) + '%,transparent)" title="'+esc(title)+'">'
         + esc(text.slice(s.start, s.end)) + '</mark>';
    cur = s.end;
  }
  html += esc(text.slice(cur));
  return html;
}

function renderDetect(r, text){
  if(r.confidence === 'insufficient'){
    $('#out').innerHTML = '<div class="empty"><b>판정 불가</b><br>' + r.n_chars
      + '자입니다. ' + esc(r.notes[0] || '') + '</div>';
    return;
  }
  const c = color(r.score);
  let h = '<div class="score"><b style="color:'+c+'">'+r.score.toFixed(1)+'</b>'
    + '<span class="meta">/ 100</span>'
    + '<span class="band '+r.band+'">'+ (BAND[r.band]||r.band) +'</span></div>'
    + '<div class="meter"><i style="width:'+r.score+'%;background:'+c+'"></i></div>'
    + '<div class="meta">'+r.n_chars+'자 · '+r.n_sentences+'문장 · 신뢰도 '
    + (CONF[r.confidence]||r.confidence) + (r.fusion_calibrated ? ' · 캘리브레이션됨'
    : ' · <b>미캘리브레이션</b>') + '</div>';

  h += '<div class="layers">'
    + '<div><small>L1 캘리브레이션 지표</small><b>'+r.layers.l1_calibrated_z.toFixed(2)+'</b></div>'
    + '<div><small>L2 패턴 밀도</small><b>'+r.layers.l2_pattern_density.toFixed(2)+'</b></div>'
    + '<div><small>L3 리듬</small><b>'+r.layers.l3_rhythm.toFixed(2)+'</b></div></div>';

  h += '<h3>근거</h3>';
  if(!r.signals.length) h += '<div class="meta">유의미한 AI 문체 신호가 없습니다.</div>';
  for(const s of r.signals.slice(0,12)){
    const d = s.strength > .66 ? c : (s.strength > .33 ? 'var(--mid)' : 'var(--muted)');
    h += '<div class="sig"><div class="t">'
      + '<span class="dot" style="background:'+d+'"></span>'
      + '<span class="tag'+(s.calibrated?' real':'')+'">'+s.layer
      + (s.calibrated?' 실측':' 추정')+'</span>'
      + '<span>'+esc(s.label)+'</span></div>'
      + '<div class="d">'+esc(s.detail)+'</div></div>';
  }

  h += '<h3>문장별 히트맵</h3><div class="heat">'+heatmap(text, r.sentences)+'</div>';
  for(const n of r.notes) h += '<div class="note">! '+esc(n)+'</div>';
  $('#out').innerHTML = h;
}

function renderHumanize(j){
  let h = '<div class="score"><b style="color:var(--lo)">'
    + (j.improved!=null && j.improved>0 ? '−'+j.improved.toFixed(1) : '0')
    + '</b><span class="meta">점 개선</span></div>'
    + '<div class="meta">'+j.before_score+' → '+j.after_score
    + ' · 변경률 '+(j.change_rate*100).toFixed(1)+'% · 강도 '+j.level+'</div>';

  if(j.before_layers && j.after_layers){
    h += '<div class="layers">';
    for(const [k,label] of [['l1_calibrated_z','L1 지표'],
                            ['l2_pattern_density','L2 패턴'],
                            ['l3_rhythm','L3 리듬']]){
      const d = j.after_layers[k] - j.before_layers[k];
      const col = d < -0.02 ? 'var(--lo)' : (d > 0.02 ? 'var(--hi)' : 'var(--muted)');
      h += '<div><small>'+label+'</small><b style="color:'+col+'">'
        + (d>=0?'+':'') + d.toFixed(2) + '</b></div>';
    }
    h += '</div>';
  }

  h += '<h3 style="display:flex;align-items:center;gap:8px">다듬기 결과'
    + '<button class="ico" id="btn-copy" style="margin-left:auto;padding:4px 10px">복사</button>'
    + '<button class="ico" id="btn-apply" style="padding:4px 10px">원문에 적용</button></h3>'
    + '<div class="heat" id="humtext">'+esc(j.text)+'</div>';
  if(j.changes.length){
    h += '<h3>적용된 규칙 ('+j.changes.length+')</h3>';
    for(const c of j.changes){
      h += '<div class="chg"><b>'+c.pattern_id+'</b> ×'+c.count+' '+esc(c.name)
        + '<br><code class="del">'+esc(c.before)+'</code> → <code class="ins">'
        + esc(c.after)+'</code></div>';
    }
  } else {
    h += '<div class="meta" style="margin-top:12px">이 강도에서 적용할 규칙이 없습니다.</div>';
  }
  for(const w of j.warnings) h += '<div class="note">! '+esc(w)+'</div>';
  $('#out').innerHTML = h;
  $('#btn-copy').onclick = async () => {
    try{ await navigator.clipboard.writeText(j.text); toast('복사했습니다'); }
    catch(e){ toast('복사 실패 — 직접 선택해 주세요'); }
  };
  $('#btn-apply').onclick = () => {
    $('#text').value = j.text; updateCount(); toast('원문에 적용했습니다');
    $('#btn-detect').click();
  };
}

$('#btn-detect').onclick = async () => {
  const text = $('#text').value;
  if(!text.trim()) return;
  busy(true, '검사 중');
  try{ renderDetect(await post('/api/detect', {text, genre:$('#genre').value}), text); }
  catch(e){ $('#out').innerHTML = '<div class="empty">오류: '+esc(e.message)+'</div>'; }
  finally{ busy(false); }
};

$('#btn-hum').onclick = async () => {
  const text = $('#text').value;
  if(!text.trim()) return;
  busy(true, '다듬기 중');
  try{ renderHumanize(await post('/api/humanize',
        {text, level:$('#level').value, genre:$('#genre').value})); }
  catch(e){ $('#out').innerHTML = '<div class="empty">오류: '+esc(e.message)+'</div>'; }
  finally{ busy(false); }
};

// ---------- 설정 기억 ----------
const CFG = 'aikiller.cfg';
function loadCfg(){
  let c = {};
  try{ c = JSON.parse(localStorage.getItem(CFG) || '{}'); }catch(e){}
  if(c.genre) $('#genre').value = c.genre;
  if(c.level) $('#level').value = c.level;
  auto = c.auto !== false;
  $('#btn-auto').classList.toggle('on', auto);
}
function saveCfg(){
  try{ localStorage.setItem(CFG, JSON.stringify(
    {genre:$('#genre').value, level:$('#level').value, auto})); }catch(e){}
}

// ---------- 토스트 ----------
let toastT;
function toast(msg){
  const el = $('#toast'); el.textContent = msg; el.classList.add('show');
  clearTimeout(toastT); toastT = setTimeout(()=>el.classList.remove('show'), 1900);
}

// ---------- 글자수 ----------
function updateCount(){
  const n = $('#text').value.trim().length;
  $('#count').textContent = n.toLocaleString() + '자'
    + (n && n < 150 ? ' · 150자 미만은 판정 불가' : '');
}

// ---------- 자동 탐지 ----------
let auto = true, autoT;
$('#btn-auto').onclick = () => {
  auto = !auto; $('#btn-auto').classList.toggle('on', auto); saveCfg();
  toast(auto ? '자동 검사 켜짐' : '자동 검사 꺼짐');
};
function scheduleAuto(){
  clearTimeout(autoT);
  if(!auto) return;
  if($('#text').value.trim().length < 150) return;
  autoT = setTimeout(()=>$('#btn-detect').click(), 900);
}
$('#text').addEventListener('input', () => { updateCount(); scheduleAuto(); });
$('#genre').addEventListener('change', () => { saveCfg(); scheduleAuto(); });
$('#level').addEventListener('change', saveCfg);

// ---------- 드래그앤드롭 ----------
const ta = $('#text');
['dragenter','dragover'].forEach(ev => ta.addEventListener(ev, e => {
  e.preventDefault(); ta.classList.add('drop');
}));
['dragleave','drop'].forEach(ev => ta.addEventListener(ev, e => {
  e.preventDefault(); ta.classList.remove('drop');
}));
ta.addEventListener('drop', e => {
  const f = e.dataTransfer.files[0];
  if(f) readFile(f);
});

async function readFile(f){
  $('#fname').textContent = f.name;
  busy(true, '파일 읽는 중');
  try{
    const buf = await f.arrayBuffer();
    let bin = ''; const bytes = new Uint8Array(buf);
    const CH = 0x8000;
    for(let i=0;i<bytes.length;i+=CH)
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i+CH));
    const j = await post('/api/parse', {filename:f.name, data_b64: btoa(bin)});
    $('#text').value = j.text; updateCount();
    toast(j.text.length.toLocaleString() + '자 추출');
    $('#btn-detect').click();
  }catch(err){ toast('오류: ' + err.message); }
  finally{ busy(false); }
}

// ---------- 기록 ----------
const HIST = $('#hist'), SCRIM = $('#scrim');
function closeHist(){ HIST.classList.remove('open'); SCRIM.classList.remove('open'); }
SCRIM.onclick = closeHist;
$('#btn-hist').onclick = async () => {
  const open = !HIST.classList.contains('open');
  HIST.classList.toggle('open', open); SCRIM.classList.toggle('open', open);
  if(open) await loadHist();
};
async function loadHist(){
  const j = await fetch('/api/history').then(r=>r.json());
  const el = $('#hist-list');
  if(!j.rows.length){
    el.innerHTML = '<div class="meta">'
      + (j.enabled ? '기록이 없습니다.' : '기록이 꺼져 있습니다 (AIKILLER_NO_HISTORY).')
      + '</div>';
    return;
  }
  el.innerHTML = j.rows.map(r => {
    const sc = r.kind === 'humanize'
      ? (r.score!=null && r.after_score!=null ? r.score.toFixed(0)+'→'+r.after_score.toFixed(0) : '다듬기')
      : (r.score!=null ? r.score.toFixed(0) : '—');
    const col = r.score!=null ? color(r.score) : 'var(--muted)';
    const d = new Date(r.ts*1000);
    const when = d.toLocaleDateString('ko-KR',{month:'numeric',day:'numeric'})
      + ' ' + d.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'});
    return '<div class="hrow" data-id="'+r.id+'">'
      + '<b style="color:'+col+'">'+sc+'</b>'
      + '<div style="min-width:0;flex:1"><div class="p">'+esc(r.preview)+'</div>'
      + '<div class="m">'+when+' · '+r.n_chars.toLocaleString()+'자 · '+esc(r.genre)
      + (r.kind==='humanize' ? ' · '+esc(r.level||'') : '') + '</div></div>'
      + '<button class="x" data-del="'+r.id+'" title="삭제">×</button></div>';
  }).join('');
}
$('#hist-list').addEventListener('click', async e => {
  const del = e.target.closest('[data-del]');
  if(del){
    e.stopPropagation();
    await fetch('/api/history/'+del.dataset.del, {method:'DELETE'});
    await loadHist(); return;
  }
  const row = e.target.closest('.hrow');
  if(!row) return;
  const j = await fetch('/api/history/'+row.dataset.id).then(r=>r.json());
  $('#text').value = j.text;
  if(j.genre) $('#genre').value = j.genre;
  updateCount(); closeHist(); $('#btn-detect').click();
});
$('#btn-clear').onclick = async () => {
  if(!confirm('기록을 전부 지웁니다. 되돌릴 수 없습니다.')) return;
  const j = await fetch('/api/history', {method:'DELETE'}).then(r=>r.json());
  await loadHist(); toast(j.deleted + '건 삭제');
};

// ---------- 단축키 ----------
document.addEventListener('keydown', e => {
  const mod = e.metaKey || e.ctrlKey;
  if(mod && e.key === 'Enter'){
    e.preventDefault();
    (e.shiftKey ? $('#btn-hum') : $('#btn-detect')).click();
  } else if(mod && (e.key === 'k' || e.key === 'K')){
    e.preventDefault();
    $('#text').value = ''; updateCount();
    $('#out').innerHTML = '<div class="empty">왼쪽에 글을 넣고 <b>검사</b>를 누르세요.</div>';
    $('#text').focus();
  } else if(e.key === 'Escape'){ closeHist(); }
});

loadCfg(); updateCount(); $('#text').focus();
</script></body></html>
"""


# ---------------------------------------------------------------------------
# 핸들러
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "aikiller"
    protocol_version = "HTTP/1.1"
    timeout = REQUEST_TIMEOUT

    def log_message(self, fmt, *args):
        if os.environ.get("AIKILLER_VERBOSE"):
            super().log_message(fmt, *args)

    # -- 응답 헬퍼 --------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ValueError("본문이 비어 있습니다.")
        if length > MAX_BODY:
            # 본문을 읽지 않고 에러를 내면 남은 바이트가 소켓에 그대로 남아
            # keep-alive 다음 요청으로 파싱된다(요청 desync). 연결을 닫는다.
            self.close_connection = True
            raise ValueError(f"본문이 너무 큽니다 (최대 {MAX_BODY // 1024 // 1024}MB).")
        return json.loads(self.rfile.read(length))

    # -- 라우팅 -----------------------------------------------------------
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, LANDING_PAGE.encode("utf-8"),
                       "text/html; charset=utf-8")
        elif path in ("/app", "/app/"):
            self._send(200, APP_PAGE.encode("utf-8"),
                       "text/html; charset=utf-8")
        elif path == "/api/history":
            self._json(200, {
                "enabled": history.enabled(),
                "rows": [r.to_dict() for r in history.recent(60)],
            })
        elif path.startswith("/api/history/"):
            row = history.get(_int_or_none(path.rsplit("/", 1)[-1]))
            if row is None:
                self._json(404, {"error": "기록이 없습니다."})
            else:
                self._json(200, row)
        elif path == "/api/patterns":
            self._json(200, {
                "categories": CATEGORIES,
                "count": len(PATTERNS),
                "patterns": [
                    {
                        "id": p.id, "category": p.category,
                        "category_name": p.category_name, "name": p.name,
                        "severity": p.severity, "weight": p.weight,
                        "risk": p.risk, "rewritable": p.rewritable,
                        "min_count": p.min_count, "hint": p.hint,
                        "evidence": p.evidence,
                    }
                    for p in PATTERNS
                ],
            })
        else:
            self._json(404, {"error": "not found"})

    def do_DELETE(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/api/history":
            self._json(200, {"deleted": history.clear()})
        elif path.startswith("/api/history/"):
            rid = _int_or_none(path.rsplit("/", 1)[-1])
            ok = history.delete(rid) if rid is not None else False
            self._json(200 if ok else 404, {"deleted": 1 if ok else 0})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        try:
            payload = self._read_json()
        except (ValueError, json.JSONDecodeError) as e:
            self._json(400, {"error": str(e)})
            return

        # 압축 해제·분석은 메모리를 크게 쓴다. 동시 실행 수를 묶어 두지 않으면
        # 요청 몇 개로 프로세스 전체가 OOM으로 죽는다.
        if not _SLOTS.acquire(timeout=20):
            self._json(503, {"error": "서버가 혼잡합니다. 잠시 후 다시 시도하세요."})
            return
        try:
            if path == "/api/detect":
                text = payload.get("text") or ""
                genre = payload.get("genre") or "essay"
                report = analyze(text, genre=genre)
                if report.confidence != "insufficient":
                    history.add("detect", text, genre,
                                score=report.score, band=report.band)
                self._json(200, report.to_dict())

            elif path == "/api/humanize":
                genre = payload.get("genre") or "essay"
                level = payload.get("level") or "moderate"
                res = humanize(payload.get("text") or "",
                               level=level, genre=genre)
                history.add("humanize", res.original, genre, level=level,
                            score=res.before_score, after_score=res.after_score,
                            result=res.text)
                self._json(200, {
                    "text": res.text, "level": res.level,
                    "change_rate": res.change_rate, "aborted": res.aborted,
                    "before_score": res.before_score,
                    "after_score": res.after_score, "improved": res.improved,
                    "before_layers": res.before_layers,
                    "after_layers": res.after_layers,
                    "changes": [asdict(c) for c in res.changes],
                    "warnings": res.warnings,
                })

            elif path == "/api/parse":
                name = payload.get("filename") or ""
                ext = os.path.splitext(name)[1]
                raw = base64.b64decode(payload.get("data_b64") or "", validate=True)
                if len(raw) > MAX_BODY:
                    raise parsers.ParseError("파일이 너무 큽니다.")
                self._json(200, {"text": parsers.parse_bytes(raw, ext),
                                 "filename": os.path.basename(name)})
            else:
                self._json(404, {"error": "not found"})

        except parsers.ParseError as e:
            self._json(400, {"error": str(e)})
        except (binascii.Error, ValueError) as e:
            self._json(400, {"error": f"잘못된 요청: {e}"})
        except MemoryError:
            self.close_connection = True
            self._json(413, {"error": "처리에 필요한 메모리가 상한을 넘었습니다."})
        except Exception as e:  # noqa: BLE001 — 서버가 죽지 않게
            self._json(500, {"error": f"{type(e).__name__}: {e}"})
        finally:
            _SLOTS.release()


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(host: str = "127.0.0.1", port: int = 8000,
          open_browser: bool = True) -> int:
    try:
        httpd = Server((host, port), Handler)
    except OSError as e:
        print(f"  포트 {port} 를 열 수 없습니다: {e}")
        print(f"  다른 포트로:  aikiller serve --port {port + 1}")
        return 1
    shown = host if host != "0.0.0.0" else "localhost"
    url = f"http://{shown}:{port}/"
    print(f"  ai킬러 웹 UI  →  {url}")
    if open_browser and host in ("127.0.0.1", "localhost"):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    if host == "0.0.0.0":
        print("  ⚠ 외부에 열려 있습니다. 리버스 프록시·인증을 앞에 두세요.")
    print("  Ctrl+C 로 종료\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  종료")
    finally:
        httpd.server_close()
    return 0
