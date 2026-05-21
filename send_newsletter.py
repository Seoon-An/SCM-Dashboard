"""
AI × SCM Daily Newsletter
"""
# 매일 KST 06:00 자동 발송 (GitHub Actions 스케줄)

import json, os, re, sys, smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import feedparser, requests

with open('config.json', encoding='utf-8') as f:
    config = json.load(f)

GEMINI_KEY    = os.environ.get('GEMINI_API_KEY', '')   # Gemini 비활성화 시 없어도 무방
GEMINI_MODEL  = 'gemini-2.0-flash'
GEMINI_ENABLED = False   # ← Gemini API 준비되면 True로 변경
TO_EMAIL     = os.environ['TO_EMAIL']
GMAIL_USER   = os.environ['GMAIL_ADDRESS']
GMAIL_PASS   = os.environ['GMAIL_APP_PASSWORD']

AI_COLOR  = '#C85A35'
SCM_COLOR = '#175F7A'
AI_BG     = '#FFF3E0'
SCM_BG    = '#E3F2F8'

AI_FEEDS = [
    {'name': 'TechCrunch AI',  'url': 'https://techcrunch.com/category/artificial-intelligence/feed/'},
    {'name': 'The Verge AI',   'url': 'https://www.theverge.com/rss/ai-artificial-intelligence/index.xml'},
    {'name': 'VentureBeat AI', 'url': 'https://venturebeat.com/category/ai/feed/'},
    {'name': 'The Decoder',    'url': 'https://the-decoder.com/feed/'},
    {'name': 'AI타임스',        'url': 'https://www.aitimes.com/rss/allArticle.xml'},
    {'name': '인공지능신문',     'url': 'https://www.aitimes.kr/rss/allArticle.xml'},
]
SCM_FEEDS = [
    {'name': 'Supply Chain Dive',         'url': 'https://www.supplychaindive.com/feeds/news/'},
    {'name': 'FreightWaves',              'url': 'https://www.freightwaves.com/feed'},
    {'name': 'Modern Materials Handling', 'url': 'https://www.mmh.com/rss/articles'},
    {'name': 'Logistics Management',      'url': 'https://www.logisticsmgmt.com/rss/news.xml'},
    {'name': 'DC Velocity',              'url': 'https://www.dcvelocity.com/rss/news/'},
    {'name': '물류신문',                   'url': 'https://www.klnews.co.kr/rss/allArticle.xml'},
    {'name': '코리아쉬핑가제트',            'url': 'https://www.ksg.co.kr/rss/allArticle.xml'},
    {'name': '물류센터뉴스',               'url': 'https://news.google.com/rss/search?q=%EB%AC%BC%EB%A5%98%EC%84%BC%ED%84%B0&hl=ko&gl=KR&ceid=KR:ko'},
    {'name': '물류부동산뉴스',              'url': 'https://news.google.com/rss/search?q=%EB%AC%BC%EB%A5%98%EB%B6%80%EB%8F%99%EC%82%B0+%EB%AC%BC%EB%A5%98%EC%B0%BD%EA%B3%A0&hl=ko&gl=KR&ceid=KR:ko'},
]

HERO_KW = ['AI', '인공지능', 'SCM', '물류', '공급망', '자동화', '에이전트',
           '로봇', 'robot', 'agent', '이커머스', 'FBA', '수요예측', '재고',
           'supply chain', 'logistics', 'warehouse', 'automation', 'machine learning']


# ── 일간 메인 ──────────────────────────────────────────────
def main():
    since    = datetime.now(timezone.utc) - timedelta(hours=24)
    disabled = set(config.get('disabledFeeds', []))
    active_ai  = [f for f in AI_FEEDS  if f['name'] not in disabled]
    active_scm = [f for f in SCM_FEEDS if f['name'] not in disabled]

    print('Fetching feeds...')
    ai_raw  = collect_articles(active_ai,  since)
    scm_raw = collect_articles(active_scm, since)
    print(f'AI: {len(ai_raw)}건, SCM: {len(scm_raw)}건')
    if not ai_raw and not scm_raw:
        print('새 기사 없음.'); return

    per_feed = config.get('topPerFeed', 2)
    ai_top   = pick_top(ai_raw,  per_feed, config.get('maxAiCards', 4) + 1, max_en=1)
    scm_top  = pick_top(scm_raw, per_feed, config.get('maxScmCards', 4) + 1, max_en=1)
    q_hits   = pick_quick_hits(ai_raw + scm_raw, ai_top + scm_top, config.get('maxQuickHits', 12))

    print('이미지 수집 중...')
    for a in ai_top + scm_top:
        a['og_image'] = fetch_og_image(a['link'])

    print('인사이트 생성 중...')
    summarize_batch(ai_top, is_ai=True)
    summarize_batch(scm_top, is_ai=False)

    print('에디터 노트 생성 중...')
    editor_note = gen_editor_note(ai_top, scm_top, q_hits)

    html = build_html(editor_note, ai_top, scm_top, q_hits, len(ai_raw), len(scm_raw))
    send_email(f'☕ [AI × SCM Daily] {kr_date(datetime.now())}', html)
    print('완료!')


# ── 주간 다이제스트 ────────────────────────────────────────
def send_weekly():
    since    = datetime.now(timezone.utc) - timedelta(days=7)
    disabled = set(config.get('disabledFeeds', []))
    active_ai  = [f for f in AI_FEEDS  if f['name'] not in disabled]
    active_scm = [f for f in SCM_FEEDS if f['name'] not in disabled]

    print('주간 피드 수집 중...')
    ai_raw  = collect_articles(active_ai,  since)
    scm_raw = collect_articles(active_scm, since)
    all_art = ai_raw + scm_raw
    if not all_art:
        print('이번 주 기사 없음.'); return

    keywords = config.get('keywords', [])
    kw_counts = {kw: sum(1 for a in all_art if kw.lower() in (a['title']+a['description']).lower())
                 for kw in keywords}
    top_kw = sorted([(k,v) for k,v in kw_counts.items() if v], key=lambda x: x[1], reverse=True)[:5]

    ai_top  = pick_top(ai_raw,  2, 5)
    scm_top = pick_top(scm_raw, 2, 5)

    print('주간 요약 생성 중...')
    summary = gen_weekly_summary(ai_top, scm_top, top_kw)
    html = build_weekly_html(summary, ai_top, scm_top, top_kw, len(ai_raw), len(scm_raw))
    now = datetime.now()
    send_email(f'📅 [AI × SCM Weekly] {now.year}년 {now.month}월 {now.day}일 주간 다이제스트', html)
    print('주간 완료!')


# ── RSS ────────────────────────────────────────────────────
def collect_articles(feeds, since):
    arts = []
    for feed in feeds:
        try:
            parsed = feedparser.parse(feed['url'])
            for e in parsed.entries:
                pub = e.get('published_parsed') or e.get('updated_parsed')
                if not pub: continue
                date = datetime(*pub[:6], tzinfo=timezone.utc)
                if date < since: continue
                title = clean(e.get('title',''))
                if not title: continue
                desc = (e.get('summary') or (e.get('content') or [{}])[0].get('value',''))
                arts.append({'title':title, 'link':e.get('link',''), 'date':date,
                             'description':clean(desc)[:600], 'source':feed['name']})
        except Exception as ex:
            print(f'  Skip {feed["name"]}: {ex}')
    return arts

def clean(s):
    s = re.sub(r'<[^>]+>',' ',str(s or ''))
    for o,n in [('&nbsp;',' '),('&amp;','&'),('&lt;','<'),('&gt;','>'),('&quot;','"'),('&#39;',"'")]:
        s = s.replace(o,n)
    return re.sub(r'\s+',' ',s).strip()

EN_SOURCES = {'TechCrunch AI', 'The Verge AI', 'VentureBeat AI', 'The Decoder',
              'Supply Chain Dive', 'FreightWaves', 'Modern Materials Handling'}

def _kw_score(a):
    """관심 키워드 매칭 수 — 많을수록 우선 노출."""
    text = (a['title'] + ' ' + a['description']).lower()
    return sum(1 for kw in config.get('keywords', []) if kw.lower() in text)

def pick_top(arts, per_feed, max_total, max_en=1):
    by = {}
    for a in arts: by.setdefault(a['source'],[]).append(a)
    picked = []
    for arr in by.values():
        # 피드별로 키워드 점수 우선, 동점이면 최신순
        arr.sort(key=lambda x: (_kw_score(x), x['date'].timestamp()), reverse=True)
        picked.extend(arr[:per_feed])
    # 전체도 키워드 점수 우선 정렬
    picked.sort(key=lambda x: (_kw_score(x), x['date'].timestamp()), reverse=True)

    # 영문 기사 max_en개 초과분을 한국어로 대체
    result, en_count = [], 0
    ko_reserve = [a for a in picked if a['source'] not in EN_SOURCES]
    for a in picked:
        if len(result) >= max_total:
            break
        if a['source'] in EN_SOURCES:
            if en_count < max_en:
                result.append(a)
                en_count += 1
        else:
            result.append(a)
    used = {a['link'] for a in result}
    for a in ko_reserve:
        if len(result) >= max_total:
            break
        if a['link'] not in used:
            result.append(a)
            used.add(a['link'])
    # 최종 출력은 키워드 점수 우선, 동점이면 최신순
    return sorted(result, key=lambda x: (_kw_score(x), x['date'].timestamp()), reverse=True)[:max_total]

def pick_quick_hits(all_arts, picked, max_h):
    seen     = {a['link'] for a in picked}
    ai_names = {f['name'] for f in AI_FEEDS}
    rest     = [a for a in all_arts if a['link'] not in seen]

    # AI / SCM 분리 후 한국어 우선 정렬
    def sort_ko_first(lst):
        ko = [a for a in lst if a['source'] not in EN_SOURCES]
        en = [a for a in lst if a['source'] in EN_SOURCES]
        return sorted(ko, key=lambda x: x['date'], reverse=True) + \
               sorted(en, key=lambda x: x['date'], reverse=True)

    ai_pool  = sort_ko_first([a for a in rest if a['source'] in ai_names])
    scm_pool = sort_ko_first([a for a in rest if a['source'] not in ai_names])

    # 50/50 균형으로 뽑기
    half     = max_h // 2
    en_limit = max_h // 3   # 영문 기사 전체의 1/3 이하
    en_count = 0
    result   = []

    for pool in (ai_pool, scm_pool):
        added = 0
        for a in pool:
            if added >= half:
                break
            if a['source'] in EN_SOURCES:
                if en_count >= en_limit:
                    continue
                en_count += 1
            result.append(a)
            added += 1

    # 부족하면 남은 기사로 채우기 (한국어 우선)
    used = {a['link'] for a in result}
    extras = sort_ko_first([a for a in rest if a['link'] not in used])
    for a in extras:
        if len(result) >= max_h:
            break
        if a['source'] in EN_SOURCES and en_count >= en_limit:
            continue
        if a['source'] in EN_SOURCES:
            en_count += 1
        result.append(a)

    return sorted(result, key=lambda x: x['date'], reverse=True)[:max_h]

def fetch_og_image(url):
    try:
        r = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=6)
        h = r.text[:20000]
        for p in [r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                  r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                  r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
                  r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']']:
            m = re.search(p, h, re.I)
            if m and m.group(1).startswith('http'): return m.group(1)
        # 본문 첫 번째 의미 있는 이미지 fallback
        for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', h, re.I):
            src = m.group(1)
            if (src.startswith('http')
                    and re.search(r'\.(jpg|jpeg|png|webp)', src, re.I)
                    and not re.search(r'logo|icon|avatar|pixel|tracking|1x1|spinner|blank', src, re.I)):
                return src
    except: pass
    return None

def call_gemini(prompt, as_json=False):
    url  = f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}'
    body = {'contents':[{'parts':[{'text':prompt}]}]}
    # JSON 모드 제거 — HTML 태그 포함 프롬프트에서 strict JSON 모드가 실패하는 경우 방지
    r = requests.post(url, json=body, timeout=60)
    data = r.json()
    # 디버그: 응답 전체 구조 출력
    print(f'  [Gemini] HTTP {r.status_code} | keys: {list(data.keys())}')
    if 'error' in data:
        print(f'  [Gemini] 오류: {data["error"]}')
        return ''
    candidates = data.get('candidates', [])
    if not candidates:
        print(f'  [Gemini] candidates 없음. 전체 응답: {str(data)[:400]}')
        return ''
    candidate = candidates[0]
    finish = candidate.get('finishReason', '')
    parts  = candidate.get('content', {}).get('parts', [])
    print(f'  [Gemini] finishReason={finish} | parts={len(parts)}')
    if not parts:
        print(f'  [Gemini] parts 없음. candidate: {str(candidate)[:300]}')
        return ''
    text = parts[0].get('text', '')
    print(f'  [Gemini] 응답 길이: {len(text)}자 | 앞부분: {text[:80].replace(chr(10)," ")}')
    return text

def summarize_batch(articles, is_ai=True):
    if not articles:
        return
    label = 'AI' if is_ai else 'SCM'

    # ── Gemini 비활성화 상태: raw 텍스트 보관 (render 시 강조 적용) ──
    if not GEMINI_ENABLED:
        for a in articles:
            a['summary'] = a['description'][:300]   # raw — highlight_title이 escape 처리
            a['insight']  = ''
        print(f'  {label} summarize: Gemini 꺼짐, 원문 사용')
        return

    # ── Gemini 활성화 시 아래 코드 실행 (GEMINI_ENABLED = True) ──
    color = AI_COLOR if is_ai else SCM_COLOR
    bg    = AI_BG    if is_ai else SCM_BG
    items = '\n'.join([f'{i+1}. 제목: {a["title"]}\n   내용: {a["description"][:300]}'
                       for i, a in enumerate(articles)])
    prompt = f"""다음 {len(articles)}개 기사를 K-brand FBA SCM 실무자를 위한 뉴스레터로 정리해줘.
반드시 한국어로. 영문 기사도 한국어로 의역.

각 기사마다 두 필드:
- summary: 핵심 내용 2문장. 친절한 에디터 말투, 존댓말, 이모지 1~2개.
- insight: FBA 이커머스·SCM 물류 실무 활용 인사이트 1~2문장. 이모지 1개. 해당 없으면 "".

HTML 강조 (summary·insight 모두):
- <strong style="color:{color}">강조 텍스트</strong>
- <span style="background:{bg};padding:1px 6px;border-radius:3px;font-weight:600;font-size:12px;color:{color}">키워드</span>

insight 예시:
"이제 AI가 단순 보조를 넘어 <strong style="color:{color}">업무 자체를 대신 처리</strong>하는 시대가 됐습니다 💼 <span style="background:{bg};padding:1px 6px;border-radius:3px;font-weight:600;font-size:12px;color:{color}">발주서 자동화</span>에도 바로 응용할 수 있을 것 같아요!"

{items}

JSON 배열로만 응답:
[{{"summary":"...","insight":"..."}}, ...]"""
    for attempt in range(3):
        try:
            raw = call_gemini(prompt)
            if not raw:
                raise ValueError('빈 응답')
            m = re.search(r'\[.*\]', raw, re.DOTALL)
            result = json.loads(m.group() if m else raw)
            for i, a in enumerate(articles):
                r = result[i] if i < len(result) else {}
                a['summary'] = r.get('summary') or esc(a['description'][:200])
                a['insight']  = r.get('insight', '')
            print(f'  {label} summarize 완료')
            return
        except Exception as e:
            print(f'  {label} summarize 실패 (시도 {attempt+1}/3): {e}')
            if attempt < 2:
                import time; time.sleep(10)
    for a in articles:
        a['summary'] = esc(a['description'][:200])
        a['insight']  = ''

def gen_editor_note(ai_top, scm_top, q_hits):
    # ── Gemini 비활성화 상태: 섹션 숨김 ─────────────────────────
    if not GEMINI_ENABLED:
        return ''

    # ── Gemini 활성화 시 아래 코드 실행 (GEMINI_ENABLED = True) ──
    ai_names = {f['name'] for f in AI_FEEDS}
    ai_t  = [f'- {a["title"]}' for a in (ai_top + [x for x in q_hits if x['source'] in ai_names])[:8]]
    scm_t = [f'- {a["title"]}' for a in (scm_top + [x for x in q_hits if x['source'] not in ai_names])[:8]]
    kw    = ', '.join(config.get('keywords', []))
    prompt = f"""너는 K-brand FBA SCM Operations Manager 독자를 위한 뉴스레터 에디터야.

오늘 수집된 기사:
관심 키워드: {kw}
[AI] {chr(10).join(ai_t)}
[SCM] {chr(10).join(scm_t)}

위 기사들의 실제 내용을 바탕으로 오늘의 에디터 노트 작성.
반드시 오늘 기사에서 나온 구체적인 흐름이나 키워드를 언급해야 함. 뻔한 말 금지.

형식:
첫 문단 "🤖 AI —" 시작: 오늘 AI 기사 중 가장 주목할 흐름 2~3문장
두번째 문단 "📦 SCM —" 시작: 오늘 SCM 기사 중 실무자가 지금 주목해야 할 포인트 2~3문장
친절한 존댓말. 특정 회사명·이직 언급 금지.

HTML 강조:
AI → <strong style="color:#C85A35">텍스트</strong> 또는 <span style="background:#FFF3E0;padding:1px 6px;border-radius:3px;font-weight:600;color:#C85A35;font-size:13px;">키워드</span>
SCM → <strong style="color:#175F7A">텍스트</strong> 또는 <span style="background:#E3F2F8;padding:1px 6px;border-radius:3px;font-weight:600;color:#175F7A;font-size:13px;">키워드</span>
위 태그만 사용. 문단 구분은 <br><br>.

에디터 노트만 출력 (다른 말 없이):"""
    for attempt in range(3):
        result = call_gemini(prompt).strip()
        result = re.sub(r'^```[a-z]*\n?', '', result).rstrip('`').strip()
        if result:
            print(f'  에디터 노트: 생성됨')
            return result
        print(f'  에디터 노트 실패 (시도 {attempt+1}/3)')
        if attempt < 2:
            import time; time.sleep(10)
    return ''

def gen_weekly_summary(ai_top, scm_top, top_kw):
    ai_t  = [a['title'] for a in ai_top[:5]]
    scm_t = [a['title'] for a in scm_top[:5]]
    kw_s  = ', '.join([f'{k}({v}건)' for k,v in top_kw])
    prompt = f"""주간 AI × SCM 요약. 키워드: {kw_s}
AI: {', '.join(ai_t)} / SCM: {', '.join(scm_t)}
JSON만: {{"ai_pick_title":"...","ai_pick_reason":"...","scm_pick_title":"...","scm_pick_reason":"...","summary":"..."}}"""
    try:
        return json.loads(call_gemini(prompt, True))
    except:
        return {'ai_pick_title': ai_top[0]['title'] if ai_top else '',
                'ai_pick_reason':'', 'scm_pick_title': scm_top[0]['title'] if scm_top else '',
                'scm_pick_reason':'', 'summary':'이번 주도 다양한 AI·SCM 소식이 있었습니다.'}

def send_email(subject, html):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = f'"AI × SCM Daily" <{GMAIL_USER}>'
    msg['To']      = TO_EMAIL
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(GMAIL_USER, GMAIL_PASS)
        s.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())


# ── HTML 유틸 ──────────────────────────────────────────────
def esc(s):
    return str(s or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;').replace("'",'&#39;')

def kr_date(d):
    return f'{d.year}년 {d.month}월 {d.day}일 ({"월화수목금토일"[d.weekday()]})'

# 제목에서 주요 키워드를 색상+볼드로 강조
_HIGHLIGHT_KW = (config.get('keywords', []) +
                 ['AI', '인공지능', 'SCM', '물류', '공급망', '자동화', '에이전트',
                  'FBA', '수요예측', '재고', '로봇', '이커머스', '관세', '운임'])

_IMPACT_KW = ['최초', '최대', '최고', '역대', '급증', '급락', '급등', '대폭', '전격',
              '세계 최', '국내 최', '사상 최', '혁신', '붕괴', '위기', '돌파']

def highlight_title(title, color):
    """제목: 관심키워드 배지 + 임팩트 표현 볼드."""
    bg = AI_BG if color == AI_COLOR else SCM_BG
    result = esc(title)
    # 1. 관심 키워드 → 배지
    for kw in sorted(config.get('keywords', []), key=len, reverse=True):
        result = re.sub(re.escape(esc(kw)),
            f'<span style="background:{bg};padding:1px 5px;border-radius:3px;font-weight:700;color:{color};">{esc(kw)}</span>',
            result, count=1, flags=re.IGNORECASE)
    # 2. 임팩트 표현 → 볼드
    for kw in sorted(_IMPACT_KW, key=len, reverse=True):
        result = result.replace(esc(kw), f'<strong style="color:{color};">{esc(kw)}</strong>', 1)
    return result

def highlight_body(text, color):
    """본문: 관심키워드 배지 + 숫자/퍼센트 볼드 + 임팩트 표현 볼드."""
    bg = AI_BG if color == AI_COLOR else SCM_BG
    result = esc(text)
    # 1. 관심 키워드 → 배지 (가장 눈에 띄게)
    for kw in sorted(config.get('keywords', []), key=len, reverse=True):
        result = re.sub(re.escape(esc(kw)),
            f'<span style="background:{bg};padding:1px 5px;border-radius:3px;font-weight:700;color:{color};">{esc(kw)}</span>',
            result, count=1, flags=re.IGNORECASE)
    # 2. 수치+단위 → 볼드 (e.g. "30%", "1조원", "3배", "200억")
    result = re.sub(
        r'(\d[\d,]*(?:\.\d+)?(?:억|조|만|천)?(?:원|달러|위안|유로)?\s*(?:%|퍼센트|배|건|명|개))',
        f'<strong style="color:{color};">\\1</strong>', result)
    # 3. 임팩트 표현 → 볼드
    for kw in sorted(_IMPACT_KW, key=len, reverse=True):
        result = result.replace(esc(kw), f'<strong style="color:{color};">{esc(kw)}</strong>', 1)
    return result


# ── 일간 HTML ──────────────────────────────────────────────
def render_hero(a, color):
    link    = a['link']
    hl      = esc(a['title'])
    src     = esc(a['source'])
    _raw    = a.get('summary') or a['description'][:200]
    summary = _raw if GEMINI_ENABLED else highlight_body(_raw, color)
    insight = a.get('insight', '')
    img     = a.get('og_image')
    bg      = AI_BG if color == AI_COLOR else SCM_BG

    if img:
        # 썸네일 이미지가 있을 때: 이미지 + 컬러 타이틀 바
        top_html = (
            f'<a href="{link}" style="display:block;text-decoration:none;">'
            f'<img src="{img}" alt="" width="100%" style="display:block;width:100%;height:220px;object-fit:cover;border:0;"></a>'
            f'<a href="{link}" style="display:block;text-decoration:none;">'
            f'<div style="background:{color};padding:16px 26px;">'
            f'<div style="font-size:12px;letter-spacing:2px;color:rgba(255,255,255,0.7);font-weight:600;margin-bottom:6px;">🌟 오늘의 하이라이트</div>'
            f'<div style="font-size:20px;font-weight:700;color:#fff;line-height:1.35;">{hl}</div>'
            f'<div style="font-size:13px;color:rgba(255,255,255,0.55);margin-top:6px;">{src}</div>'
            f'</div></a>'
        )
    else:
        # 썸네일 없을 때: 컬러 블록 안에 텍스트 하단 정렬
        top_html = (
            f'<a href="{link}" style="display:block;text-decoration:none;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" style="background:{color};height:220px;">'
            f'<tr><td valign="bottom" style="padding:20px 26px;">'
            f'<div style="font-size:12px;letter-spacing:2px;color:rgba(255,255,255,0.7);font-weight:600;margin-bottom:8px;">🌟 오늘의 하이라이트</div>'
            f'<div style="font-size:20px;font-weight:700;color:#fff;line-height:1.35;">{hl}</div>'
            f'<div style="font-size:13px;color:rgba(255,255,255,0.55);margin-top:8px;">{src}</div>'
            f'</td></tr></table></a>'
        )

    insight_html = ''
    if insight:
        insight_html = (
            f'<div style="margin-top:12px;">'
            f'<div style="font-size:12px;font-weight:700;color:{color};letter-spacing:0.3px;margin-bottom:5px;">💡 인사이트</div>'
            f'<div style="font-size:14px;color:#555;line-height:1.8;padding:10px 14px;background:{bg};border-radius:6px;">{insight}</div>'
            f'</div>'
        )

    hero_label = (f'<div style="font-size:12px;font-weight:700;color:{color};letter-spacing:0.3px;margin-bottom:5px;">📌 핵심 요약</div>'
                  if GEMINI_ENABLED else '')

    return (
        f'<div style="border-radius:10px;overflow:hidden;border:1px solid #e8e8e8;margin-bottom:24px;">'
        f'{top_html}'
        f'<div style="padding:20px 26px;background:#fff;border-top:1px solid #eee;">'
        f'{hero_label}'
        f'<div style="font-size:15px;color:#444;line-height:1.8;">{summary}</div>'
        f'{insight_html}'
        f'</div></div>'
    )

def render_card(a, color, placeholder_bg):
    img     = a.get('og_image')
    link    = a['link']
    hl      = esc(a['title'])
    src     = esc(a['source'])
    _raw    = a.get('summary') or a['description'][:200]
    summary = _raw if GEMINI_ENABLED else highlight_body(_raw, color)
    insight = a.get('insight', '')
    bg      = AI_BG if color == AI_COLOR else SCM_BG

    if img:
        thumb = (f'<a href="{link}" style="display:block;text-decoration:none;">'
                 f'<img src="{img}" alt="" width="100%" style="display:block;width:100%;height:140px;object-fit:cover;border:0;"></a>')
    else:
        thumb = (f'<a href="{link}" style="display:block;text-decoration:none;">'
                 f'<table width="100%" cellpadding="0" cellspacing="0" style="background:{placeholder_bg};height:130px;">'
                 f'<tr><td align="center" valign="middle" style="color:#ccc;font-size:13px;">썸네일</td></tr>'
                 f'</table></a>')

    insight_html = ''
    if insight:
        insight_html = (
            f'<div style="margin-top:10px;">'
            f'<div style="font-size:12px;font-weight:700;color:{color};margin-bottom:4px;">💡 인사이트</div>'
            f'<div style="font-size:13px;color:#555;line-height:1.7;padding:8px 10px;background:{bg};border-radius:5px;">{insight}</div>'
            f'</div>'
        )

    summary_label = (f'<div style="font-size:12px;font-weight:700;color:{color};margin-bottom:4px;">📌 핵심 요약</div>'
                     if GEMINI_ENABLED else '')

    return (
        f'<div style="margin-bottom:18px;border-radius:8px;overflow:hidden;border:1px solid #e8e8e8;background:#fff;">'
        f'{thumb}'
        f'<div style="padding:14px 16px;">'
        f'<a href="{link}" style="text-decoration:none;">'
        f'<div style="font-size:15px;font-weight:700;color:#111;line-height:1.4;margin-bottom:10px;">{hl}</div>'
        f'</a>'
        f'{summary_label}'
        f'<div style="font-size:14px;color:#444;line-height:1.75;">{summary}</div>'
        f'{insight_html}'
        f'<div style="font-size:12px;color:#bbb;margin-top:10px;">{src}</div>'
        f'</div></div>'
    )

def gen_briefing(ai_total, scm_total, all_articles):
    """Gemini 없이 오늘의 기사 통계 + 키워드 배지 HTML 생성."""
    total = ai_total + scm_total
    kw_list = config.get('keywords', [])
    all_text = ' '.join(a['title'] + ' ' + a['description'] for a in all_articles)
    kw_hits = sorted(
        [(kw, len(re.findall(re.escape(kw), all_text, re.I))) for kw in kw_list if kw.lower() in all_text.lower()],
        key=lambda x: x[1], reverse=True
    )[:6]
    colors  = [AI_COLOR, SCM_COLOR, '#7B5EA7', AI_COLOR, SCM_COLOR, '#7B5EA7']
    badges  = ''.join(
        f'<span style="display:inline-block;margin:3px 4px 3px 0;padding:4px 12px;'
        f'background:{colors[i % len(colors)]}18;border:1px solid {colors[i % len(colors)]}44;'
        f'border-radius:20px;font-size:13px;font-weight:600;color:{colors[i % len(colors)]};">'
        f'{esc(kw)}</span>'
        for i, (kw, _) in enumerate(kw_hits)
    )
    return (
        f'<div style="padding:18px 32px;border-bottom:1px solid #eee;">'
        f'<div style="font-size:12px;letter-spacing:2px;color:#bbb;font-weight:600;margin-bottom:10px;">📰 오늘의 브리핑</div>'
        f'<div style="font-size:14px;color:#555;margin-bottom:10px;">'
        f'오늘 <strong style="color:#111;">{total}건</strong>의 기사를 수집했어요 &nbsp;·&nbsp; '
        f'<span style="color:{AI_COLOR};">🤖 AI {ai_total}건</span> &nbsp;·&nbsp; '
        f'<span style="color:{SCM_COLOR};">📦 SCM {scm_total}건</span>'
        f'</div>'
        f'{("<div>" + badges + "</div>") if badges else ""}'
        f'</div>'
    )

def build_html(editor_note, ai_top, scm_top, q_hits, ai_total=0, scm_total=0):
    ai_names = {f['name'] for f in AI_FEEDS}

    combined  = sorted(ai_top + scm_top, key=lambda x: x['date'], reverse=True)
    relevant  = [a for a in combined if any(kw.lower() in (a['title']+' '+a['description']).lower() for kw in HERO_KW)]
    hero      = relevant[0] if relevant else combined[0]
    hero_color= AI_COLOR if hero in ai_top else SCM_COLOR
    ai_col    = [a for a in ai_top  if a is not hero]
    scm_col   = [a for a in scm_top if a is not hero]

    W = ('max-width:900px;margin:0 auto;background:#fff;'
         'font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;'
         'color:#111;line-height:1.6;')

    H = f'<body style="margin:0;padding:20px 0;background:#efefef;"><div style="{W}">'

    # ── 헤더
    H += (f'<div style="padding:22px 32px 16px;border-bottom:2.5px solid #111;">'
          f'<div style="font-size:12px;letter-spacing:2.5px;color:#aaa;margin-bottom:6px;font-weight:500;">AI × SCM DAILY</div>'
          f'<div style="font-size:28px;font-weight:700;line-height:1.2;">☕ 굿모닝!</div>'
          f'<div style="font-size:14px;color:#aaa;margin-top:6px;">{kr_date(datetime.now())}</div>'
          f'</div>')

    # ── Gemini ON: 에디터 노트 / Gemini OFF: 기사 통계 + 키워드 브리핑
    if editor_note:
        H += (f'<div style="padding:18px 32px;border-bottom:1px solid #eee;">'
              f'<div style="font-size:12px;letter-spacing:2px;color:#bbb;font-weight:600;margin-bottom:10px;">📝 오늘의 한 마디</div>'
              f'<div style="font-size:15px;color:#333;line-height:1.9;">{editor_note}</div>'
              f'</div>')
    else:
        H += gen_briefing(ai_total, scm_total, ai_top + scm_top + q_hits)

    # ── 히어로
    H += f'<div style="padding:24px 32px 0;">{render_hero(hero, hero_color)}</div>'

    # ── 2단 (table — Gmail 호환)
    def col_header(emoji, label, color):
        return (f'<div style="font-size:16px;font-weight:800;color:{color};'
                f'padding-bottom:10px;border-bottom:2.5px solid {color};margin-bottom:16px;">'
                f'{emoji} {label}</div>')

    ai_cards   = ''.join(render_card(a, AI_COLOR,  '#f5f0ec') for a in ai_col)
    scm_cards  = ''.join(render_card(a, SCM_COLOR, '#edf5f8') for a in scm_col)

    H += (f'<div style="padding:0 32px 24px;">'
          f'<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;"><tr>'
          f'<td width="50%" valign="top" style="padding-right:9px;">'
          f'{col_header("🤖","AI 이슈", AI_COLOR)}{ai_cards}'
          f'</td>'
          f'<td width="50%" valign="top" style="padding-left:9px;">'
          f'{col_header("📦","SCM 이슈", SCM_COLOR)}{scm_cards}'
          f'</td>'
          f'</tr></table></div>')

    # ── Quick Hits
    if q_hits:
        rows = ''
        for i, a in enumerate(q_hits):
            is_ai = a['source'] in ai_names
            tc  = AI_COLOR if is_ai else SCM_COLOR
            tl  = 'AI' if is_ai else 'SCM'
            bd  = 'border-bottom:1px solid #eee;' if i < len(q_hits)-1 else ''
            ttl = highlight_title(a['title'], tc)
            rows += (
                f'<table width="100%" cellpadding="0" cellspacing="0" style="{bd}padding:0;">'
                f'<tr>'
                # 배지 셀: 고정 너비로 제목 시작점 통일
                f'<td width="52" style="width:52px;padding:9px 10px 9px 0;vertical-align:middle;">'
                f'<span style="display:inline-block;width:48px;text-align:center;font-size:11px;'
                f'font-weight:700;color:#fff;background:{tc};padding:3px 0;border-radius:20px;">{tl}</span>'
                f'</td>'
                # 제목 셀
                f'<td style="padding:9px 0;vertical-align:middle;">'
                f'<a href="{a["link"]}" style="font-size:14px;color:#333;text-decoration:none;line-height:1.5;">{ttl}</a>'
                f'</td>'
                f'</tr></table>'
            )
        H += (f'<div style="padding:18px 32px;background:#fafafa;border-top:1px solid #eee;">'
              f'<div style="font-size:13px;letter-spacing:1.5px;color:#aaa;font-weight:600;margin-bottom:6px;">⚡ 빠르게 보는 헤드라인</div>'
              f'{rows}</div>')

    H += '<div style="padding:18px 32px;border-top:1px solid #eee;text-align:center;font-size:14px;color:#ccc;">📬 좋은 하루 보내세요 ✨</div>'
    H += '</div></body>'
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>{H}</html>'


# ── 주간 HTML ──────────────────────────────────────────────
def build_weekly_html(summary, ai_top, scm_top, top_kw, ai_cnt, scm_cnt):
    ai_names = {f['name'] for f in AI_FEEDS}
    now = datetime.now()
    W = ('max-width:900px;margin:0 auto;background:#fff;'
         'font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;'
         'color:#111;line-height:1.6;')
    H = f'<body style="margin:0;padding:20px 0;background:#efefef;"><div style="{W}">'

    kw_badges = ''.join(
        f'<span style="font-size:12px;font-weight:700;color:#fff;background:{AI_COLOR if i%2==0 else SCM_COLOR};'
        f'padding:3px 11px;border-radius:20px;margin-right:4px;">{esc(kw)}</span>'
        for i,(kw,_) in enumerate(top_kw))

    H += (f'<div style="padding:22px 32px 16px;border-bottom:2.5px solid #111;">'
          f'<div style="font-size:12px;letter-spacing:2.5px;color:#aaa;margin-bottom:6px;font-weight:500;">AI × SCM WEEKLY</div>'
          f'<div style="font-size:28px;font-weight:700;line-height:1.2;">📅 이번 주 하이라이트</div>'
          f'<div style="font-size:14px;color:#aaa;margin-top:6px;">{now.year}년 {now.month}월 {now.day}일 · {ai_cnt+scm_cnt}건 큐레이션</div>'
          f'<div style="margin-top:10px;">{kw_badges}</div>'
          f'</div>')

    if summary.get('summary'):
        H += (f'<div style="padding:18px 32px;border-bottom:1px solid #eee;">'
              f'<div style="font-size:12px;letter-spacing:2px;color:#bbb;font-weight:600;margin-bottom:10px;">📝 이번 주 에디터 노트</div>'
              f'<div style="font-size:15px;color:#333;line-height:1.9;">{esc(summary["summary"])}</div>'
              f'</div>')

    H += (f'<div style="padding:24px 32px;border-bottom:1px solid #eee;">'
          f'<div style="font-size:16px;font-weight:800;color:#111;margin-bottom:16px;">🏆 이번 주 픽</div>'
          f'<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;"><tr>'
          f'<td width="48%" valign="top" style="padding-right:12px;">'
          f'<div style="padding:18px;border-radius:8px;border:1px solid #eee;border-top:3px solid {AI_COLOR};">'
          f'<div style="font-size:12px;font-weight:700;color:{AI_COLOR};margin-bottom:10px;">🥇 AI 픽 오브 더 위크</div>'
          f'<div style="font-size:16px;font-weight:700;color:#111;line-height:1.4;margin-bottom:8px;">{esc(summary.get("ai_pick_title",""))}</div>'
          f'<div style="font-size:14px;color:#666;line-height:1.6;">{esc(summary.get("ai_pick_reason",""))}</div>'
          f'</div></td>'
          f'<td width="4%"></td>'
          f'<td width="48%" valign="top" style="padding-left:12px;">'
          f'<div style="padding:18px;border-radius:8px;border:1px solid #eee;border-top:3px solid {SCM_COLOR};">'
          f'<div style="font-size:12px;font-weight:700;color:{SCM_COLOR};margin-bottom:10px;">🥇 SCM 픽 오브 더 위크</div>'
          f'<div style="font-size:16px;font-weight:700;color:#111;line-height:1.4;margin-bottom:8px;">{esc(summary.get("scm_pick_title",""))}</div>'
          f'<div style="font-size:14px;color:#666;line-height:1.6;">{esc(summary.get("scm_pick_reason",""))}</div>'
          f'</div></td>'
          f'</tr></table></div>')

    rows = ''
    for a in ai_top + scm_top:
        is_ai = a['source'] in ai_names
        tc = AI_COLOR if is_ai else SCM_COLOR
        tl = 'AI' if is_ai else 'SCM'
        rows += (f'<div style="padding:9px 0;border-bottom:1px solid #eee;display:table;width:100%;">'
                 f'<span style="display:table-cell;white-space:nowrap;vertical-align:middle;padding-right:8px;">'
                 f'<span style="font-size:11px;font-weight:700;color:#fff;background:{tc};padding:3px 9px;border-radius:20px;">{tl}</span></span>'
                 f'<span style="display:table-cell;vertical-align:middle;">'
                 f'<a href="{a["link"]}" style="font-size:14px;color:#333;text-decoration:none;line-height:1.5;">{esc(a["title"])}</a>'
                 f'</span></div>')

    H += (f'<div style="padding:18px 32px;background:#fafafa;border-top:1px solid #eee;">'
          f'<div style="font-size:13px;letter-spacing:1.5px;color:#aaa;font-weight:600;margin-bottom:14px;">📋 이번 주 전체 기사</div>'
          f'{rows}'
          f'<table cellpadding="0" cellspacing="0" style="margin-top:16px;padding:14px 16px;background:#fff;border-radius:8px;border:1px solid #eee;">'
          f'<tr>'
          f'<td style="padding-right:24px;"><div style="font-size:12px;color:#aaa;margin-bottom:4px;">총 기사</div><div style="font-size:22px;font-weight:700;">{ai_cnt+scm_cnt}건</div></td>'
          f'<td style="padding-right:24px;"><div style="font-size:12px;color:{AI_COLOR};margin-bottom:4px;">AI</div><div style="font-size:22px;font-weight:700;">{ai_cnt}건</div></td>'
          f'<td><div style="font-size:12px;color:{SCM_COLOR};margin-bottom:4px;">SCM</div><div style="font-size:22px;font-weight:700;">{scm_cnt}건</div></td>'
          f'</tr></table>'
          f'</div>')

    H += '<div style="padding:18px 32px;border-top:1px solid #eee;text-align:center;font-size:14px;color:#ccc;">📬 좋은 주말 보내세요 ✨</div>'
    H += '</div></body>'
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>{H}</html>'


# ── 실행 ───────────────────────────────────────────────────
if __name__ == '__main__':
    if '--weekly' in sys.argv:
        send_weekly()
    else:
        main()
