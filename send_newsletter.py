"""
AI × SCM Daily Newsletter
"""

import json, os, re, sys, smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import feedparser, requests

with open('config.json', encoding='utf-8') as f:
    config = json.load(f)

GEMINI_KEY   = os.environ['GEMINI_API_KEY']
GEMINI_MODEL = 'gemini-2.0-flash'
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
    {'name': '물류신문',                   'url': 'https://www.klnews.co.kr/rss/allArticle.xml'},
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
    ai_top   = pick_top(ai_raw,  per_feed, config.get('maxAiCards', 4) + 1)
    scm_top  = pick_top(scm_raw, per_feed, config.get('maxScmCards', 4) + 1)
    q_hits   = pick_quick_hits(ai_raw + scm_raw, ai_top + scm_top, config.get('maxQuickHits', 12))

    print('이미지 수집 중...')
    for a in ai_top + scm_top:
        a['og_image'] = fetch_og_image(a['link'])

    print('인사이트 생성 중...')
    summarize_batch(ai_top, is_ai=True)
    summarize_batch(scm_top, is_ai=False)

    print('에디터 노트 생성 중...')
    editor_note = gen_editor_note(ai_top, scm_top, q_hits)

    html = build_html(editor_note, ai_top, scm_top, q_hits)
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

def pick_top(arts, per_feed, max_total):
    by = {}
    for a in arts: by.setdefault(a['source'],[]).append(a)
    picked = []
    for arr in by.values():
        arr.sort(key=lambda x: x['date'], reverse=True)
        picked.extend(arr[:per_feed])
    picked.sort(key=lambda x: x['date'], reverse=True)
    return picked[:max_total]

def pick_quick_hits(all_arts, picked, max_h):
    seen = {a['link'] for a in picked}
    rest = [a for a in all_arts if a['link'] not in seen]
    rest.sort(key=lambda x: x['date'], reverse=True)
    return rest[:max_h]

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
    if as_json:
        body['generationConfig'] = {'responseMimeType':'application/json'}
    r = requests.post(url, json=body, timeout=60)
    data = r.json()
    if 'error' in data:
        print(f'  Gemini 오류: {data["error"].get("message","")}')
        return ''
    parts = data.get('candidates',[{}])[0].get('content',{}).get('parts',[])
    if not parts:
        print(f'  Gemini 빈 응답: {str(data)[:300]}')
        return ''
    return parts[0].get('text', '')

def summarize_batch(articles, is_ai=True):
    if not articles:
        return
    color = AI_COLOR if is_ai else SCM_COLOR
    bg    = AI_BG    if is_ai else SCM_BG
    label = 'AI' if is_ai else 'SCM'
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
            raw = call_gemini(prompt, True)
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
    for a in articles:
        a['summary'] = esc(a['description'][:200])
        a['insight']  = ''

def gen_editor_note(ai_top, scm_top, q_hits):
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


# ── 일간 HTML ──────────────────────────────────────────────
def render_hero(a, color):
    link    = a['link']
    hl      = esc(a['title'])
    src     = esc(a['source'])
    summary = a.get('summary') or esc(a['description'][:200])
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

    return (
        f'<div style="border-radius:10px;overflow:hidden;border:1px solid #e8e8e8;margin-bottom:24px;">'
        f'{top_html}'
        f'<div style="padding:20px 26px;background:#fff;border-top:1px solid #eee;">'
        f'<div style="font-size:12px;font-weight:700;color:{color};letter-spacing:0.3px;margin-bottom:5px;">📌 핵심 요약</div>'
        f'<div style="font-size:15px;color:#444;line-height:1.8;">{summary}</div>'
        f'{insight_html}'
        f'</div></div>'
    )

def render_card(a, color, placeholder_bg):
    img     = a.get('og_image')
    link    = a['link']
    hl      = esc(a['title'])
    src     = esc(a['source'])
    summary = a.get('summary') or esc(a['description'][:200])
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

    return (
        f'<div style="margin-bottom:18px;border-radius:8px;overflow:hidden;border:1px solid #e8e8e8;background:#fff;">'
        f'{thumb}'
        f'<div style="padding:14px 16px;">'
        f'<a href="{link}" style="text-decoration:none;">'
        f'<div style="font-size:15px;font-weight:700;color:#111;line-height:1.4;margin-bottom:10px;">{hl}</div>'
        f'</a>'
        f'<div style="font-size:12px;font-weight:700;color:{color};margin-bottom:4px;">📌 핵심 요약</div>'
        f'<div style="font-size:14px;color:#444;line-height:1.75;">{summary}</div>'
        f'{insight_html}'
        f'<div style="font-size:12px;color:#bbb;margin-top:10px;">{src}</div>'
        f'</div></div>'
    )

def build_html(editor_note, ai_top, scm_top, q_hits):
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

    # ── 에디터 노트
    if not editor_note:
        editor_note = '🤖 AI — 오늘도 AI 업계에서 흥미로운 소식들이 들어왔습니다.<br><br>📦 SCM — 물류·공급망 현장의 최신 트렌드를 확인해보세요.'
    H += (f'<div style="padding:18px 32px;border-bottom:1px solid #eee;">'
          f'<div style="font-size:12px;letter-spacing:2px;color:#bbb;font-weight:600;margin-bottom:10px;">📝 오늘의 한 마디</div>'
          f'<div style="font-size:15px;color:#333;line-height:1.9;">{editor_note}</div>'
          f'</div>')

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
          f'<td width="48%" valign="top" style="padding-right:12px;">'
          f'{col_header("🤖","AI 핫이슈", AI_COLOR)}{ai_cards}'
          f'</td>'
          f'<td width="4%" style="width:4%;"></td>'
          f'<td width="48%" valign="top" style="padding-left:12px;">'
          f'{col_header("📦","SCM 핫이슈", SCM_COLOR)}{scm_cards}'
          f'</td>'
          f'</tr></table></div>')

    # ── Quick Hits
    if q_hits:
        rows = ''
        for i, a in enumerate(q_hits):
            is_ai = a['source'] in ai_names
            tc = AI_COLOR if is_ai else SCM_COLOR
            tl = 'AI' if is_ai else 'SCM'
            bd = 'border-bottom:1px solid #eee;' if i < len(q_hits)-1 else ''
            rows += (f'<div style="padding:9px 0;{bd}display:table;width:100%;">'
                     f'<span style="display:table-cell;white-space:nowrap;vertical-align:middle;padding-right:8px;">'
                     f'<span style="font-size:11px;font-weight:700;color:#fff;background:{tc};'
                     f'padding:3px 9px;border-radius:20px;">{tl}</span></span>'
                     f'<span style="display:table-cell;vertical-align:middle;">'
                     f'<a href="{a["link"]}" style="font-size:14px;color:#333;text-decoration:none;line-height:1.5;">{esc(a["title"])}</a>'
                     f'</span></div>')
        H += (f'<div style="padding:18px 32px;background:#fafafa;border-top:1px solid #eee;">'
              f'<div style="font-size:13px;letter-spacing:1.5px;color:#aaa;font-weight:600;margin-bottom:14px;">⚡ 빠르게 보는 헤드라인</div>'
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
