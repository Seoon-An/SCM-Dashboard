"""
AI × SCM Daily Newsletter — 프로토타입 완전 반영 버전
"""

import json, os, re, sys, smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import feedparser, requests

with open('config.json', encoding='utf-8') as f:
    config = json.load(f)

GEMINI_KEY   = os.environ['GEMINI_API_KEY']
GEMINI_MODEL = 'gemini-2.5-flash'
TO_EMAIL     = os.environ['TO_EMAIL']
GMAIL_USER   = os.environ['GMAIL_ADDRESS']
GMAIL_PASS   = os.environ['GMAIL_APP_PASSWORD']

AI_COLOR  = '#E97451'
SCM_COLOR = '#1E7E9E'

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

# 히어로 관련성 판단 키워드
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

    print('AI 인사이트 생성 중...')
    for a in ai_top:
        a.update(summarize(a))
        a.update(tag_scm(a))

    print('SCM 인사이트 생성 중...')
    for a in scm_top:
        a.update(summarize(a))

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
        r = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        h = r.text[:15000]
        for p in [r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                  r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                  r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']']:
            m = re.search(p, h, re.I)
            if m and m.group(1).startswith('http'): return m.group(1)
    except: pass
    return None

def call_gemini(prompt, as_json=False):
    url  = f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}'
    body = {'contents':[{'parts':[{'text':prompt}]}]}
    if as_json: body['generationConfig'] = {'responseMimeType':'application/json'}
    r = requests.post(url, json=body, timeout=30)
    return (r.json().get('candidates',[{}])[0].get('content',{}).get('parts',[{}])[0].get('text',''))

def summarize(a):
    prompt = f"""다음 기사를 뉴스레터 에디터가 독자에게 친절하게 설명해주듯 요약해줘.
tone: 친절한 존댓말. 따뜻하고 친근한 에디터 스타일.
headline — 흥미롭게 한 문장, 읽고 싶어지게
body — 쉬운 말로 3-4문장. 존댓말. 이모지 한두 개 OK.
영문이면 자연스러운 한국어로 의역.
기사: {a['title']} / {a['description']}
JSON만: {{"headline":"...","body":"..."}}"""
    try:
        d = json.loads(call_gemini(prompt, True))
        return {'headline':d.get('headline',''), 'body':d.get('body','')}
    except:
        return {'headline':a['title'], 'body':a['description'][:200]}

def tag_scm(a):
    prompt = f"""AI 기사의 K-brand FBA 이커머스 적용 가능성:
5=즉시/4=직접/3=간접/2=일반/1=무관. 3이상 40자이내 코멘트. 2이하 null.
기사: {a['title']}
JSON만: {{"score":<int>,"comment":<string|null>}}"""
    try:
        d = json.loads(call_gemini(prompt, True))
        return {'scm_score':d.get('score',0), 'scm_comment':d.get('comment')}
    except:
        return {'scm_score':0, 'scm_comment':None}

def gen_editor_note(ai_top, scm_top, q_hits):
    ai_names = {f['name'] for f in AI_FEEDS}
    ai_t  = [f'- {a["title"]}' for a in (ai_top + [x for x in q_hits if x['source'] in ai_names])[:8]]
    scm_t = [f'- {a["title"]}' for a in (scm_top + [x for x in q_hits if x['source'] not in ai_names])[:8]]
    kw    = ', '.join(config.get('keywords', []))
    prompt = f"""너는 K-brand FBA SCM Operations Manager 독자를 위한 뉴스레터 에디터야.
관심 키워드: {kw}
[AI] {chr(10).join(ai_t)}
[SCM] {chr(10).join(scm_t)}

두 문단을 하나로 이어서 작성. 각 문단 앞에 이모지 포함:
첫 문단: "🤖 AI —" 로 시작, AI 뉴스 핵심 2-3문장
두번째 문단: "📦 SCM —" 로 시작, SCM 뉴스 핵심 2-3문장
친절한 존댓말. [제약] 특정 회사명·이직 언급 금지.
에디터 노트 전문(다른 말 없이):"""
    return call_gemini(prompt).strip()

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

def scm_tag(a, color):
    sc, cm = a.get('scm_score',0), a.get('scm_comment')
    if sc < 3 or not cm: return ''
    return (f'<div style="margin:10px 0;padding:9px 12px;background:{color}18;'
            f'border-left:3px solid {color};font-size:12px;color:#444;line-height:1.5;">'
            f'💡 {esc(cm)}</div>')


# ── 일간 HTML ──────────────────────────────────────────────
def render_hero(a, color):
    img  = a.get('og_image')
    link = a['link']
    hl   = esc(a.get('headline') or a['title'])
    body = esc(a.get('body',''))
    src  = esc(a['source'])
    img_block = (f'<a href="{link}" style="display:block;"><img src="{img}" alt="" width="100%" '
                 f'style="display:block;max-width:100%;height:280px;object-fit:cover;"></a>'
                 if img else
                 f'<a href="{link}" style="display:block;"><div style="height:200px;background:{color};"></div></a>')
    return f'''<div style="margin-bottom:28px;border-radius:10px;overflow:hidden;border:1px solid #e8e8e8;">
{img_block}
<div style="background:{color};padding:18px 26px;">
  <div style="font-size:10px;font-weight:800;letter-spacing:2px;color:rgba(255,255,255,.7);margin-bottom:7px;">🌟 오늘의 하이라이트</div>
  <a href="{link}" style="text-decoration:none;"><div style="font-size:20px;font-weight:900;color:#fff;line-height:1.35;">{hl}</div></a>
  <div style="font-size:11px;color:rgba(255,255,255,.55);margin-top:7px;">{src}</div>
</div>
<div style="padding:20px 26px;background:#fff;">
  <div style="font-size:14px;color:#444;line-height:1.8;">{body}</div>
  {scm_tag(a, color)}
</div>
</div>'''

def render_card(a, color, show_scm=False):
    img  = a.get('og_image')
    link = a['link']
    hl   = esc(a.get('headline') or a['title'])
    body = esc(a.get('body',''))
    src  = esc(a['source'])
    img_block = (f'<a href="{link}" style="display:block;"><img src="{img}" alt="" width="100%" '
                 f'style="display:block;max-width:100%;height:165px;object-fit:cover;"></a>'
                 if img else
                 f'<a href="{link}" style="display:block;"><div style="height:100px;background:{color};"></div></a>')
    return f'''<div style="margin-bottom:18px;border-radius:8px;overflow:hidden;border:1px solid #e8e8e8;background:#fff;">
{img_block}
<div style="padding:14px 16px;">
  <a href="{link}" style="text-decoration:none;">
    <div style="font-size:15px;font-weight:700;color:#111;line-height:1.4;margin-bottom:8px;">{hl}</div>
  </a>
  <div style="font-size:13px;color:#555;line-height:1.7;margin-bottom:8px;">{body}</div>
  {scm_tag(a,color) if show_scm else ''}
  <div style="font-size:11px;color:#ccc;margin-top:8px;">{src}</div>
</div>
</div>'''

def build_html(editor_note, ai_top, scm_top, q_hits):
    ai_names = {f['name'] for f in AI_FEEDS}

    # 히어로: AI·SCM 관련 키워드가 있는 기사 중 가장 최신
    combined  = sorted(ai_top + scm_top, key=lambda x: x['date'], reverse=True)
    relevant  = [a for a in combined if any(kw.lower() in (a['title']+' '+a['description']).lower() for kw in HERO_KW)]
    hero      = relevant[0] if relevant else combined[0]
    hero_color= AI_COLOR if hero in ai_top else SCM_COLOR
    ai_col    = [a for a in ai_top  if a is not hero]
    scm_col   = [a for a in scm_top if a is not hero]

    W = ('max-width:1000px;margin:0 auto;background:#ffffff;'
         'font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;'
         'color:#111111;line-height:1.6;')

    H = f'<body style="margin:0;padding:20px 0;background:#efefef;"><div style="{W}">'

    # 헤더
    H += f'''<div style="padding:24px 32px 18px;border-bottom:2px solid #111111;">
  <div style="font-size:10px;font-weight:700;letter-spacing:2.5px;color:#aaaaaa;text-transform:uppercase;margin-bottom:6px;">AI × SCM DAILY &nbsp;·&nbsp; 읽기 약 12분</div>
  <div style="font-size:26px;font-weight:900;color:#111111;letter-spacing:-0.5px;">☕ 굿모닝!</div>
  <div style="font-size:13px;color:#aaaaaa;margin-top:6px;">{kr_date(datetime.now())}</div>
</div>'''

    # 에디터 노트: 한 덩어리
    if editor_note:
        H += f'''<div style="padding:18px 32px;border-bottom:1px solid #eeeeee;">
  <div style="font-size:10px;font-weight:700;letter-spacing:2px;color:#bbbbbb;text-transform:uppercase;margin-bottom:10px;">📝 오늘의 한 마디</div>
  <div style="padding:16px 18px;background:#fafafa;border-radius:8px;border-left:3px solid #dddddd;font-size:14px;color:#444444;line-height:1.85;">{esc(editor_note).replace(chr(10)+chr(10),"<br><br>").replace(chr(10),"<br>")}</div>
</div>'''

    # 히어로
    H += f'<div style="padding:24px 32px 0;">{render_hero(hero, hero_color)}</div>'

    # 2단
    def col_header(emoji, label, color):
        return (f'<div style="font-size:12px;font-weight:800;color:{color};'
                f'letter-spacing:1.5px;text-transform:uppercase;'
                f'padding-bottom:10px;border-bottom:2px solid {color};margin-bottom:14px;">'
                f'{emoji} {label}</div>')

    H += '<div style="padding:0 32px 24px;">'
    H += '<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;"><tr>'
    H += '<td width="48%" valign="top" style="padding-right:14px;">'
    if ai_col:
        H += col_header('🤖','AI 핫이슈', AI_COLOR)
        for a in ai_col: H += render_card(a, AI_COLOR, True)
    H += '</td><td width="4%"></td>'
    H += '<td width="48%" valign="top" style="padding-left:14px;">'
    if scm_col:
        H += col_header('📦','SCM 핫이슈', SCM_COLOR)
        for a in scm_col: H += render_card(a, SCM_COLOR)
    H += '</td></tr></table></div>'

    # Quick Hits
    if q_hits:
        H += '<div style="padding:20px 32px;background:#fafafa;border-top:1px solid #eeeeee;">'
        H += '<div style="font-size:11px;font-weight:700;letter-spacing:2px;color:#aaaaaa;text-transform:uppercase;margin-bottom:14px;">⚡ 빠르게 보는 헤드라인</div>'
        for i, a in enumerate(q_hits):
            is_ai = a['source'] in ai_names
            tc = AI_COLOR if is_ai else SCM_COLOR
            tl = 'AI' if is_ai else 'SCM'
            bd = '' if i == len(q_hits)-1 else 'border-bottom:1px solid #eeeeee;'
            H += (f'<div style="padding:9px 0;{bd}display:flex;align-items:baseline;gap:8px;">'
                  f'<span style="font-size:10px;font-weight:700;color:#fff;background:{tc};'
                  f'padding:2px 8px;border-radius:20px;white-space:nowrap;flex-shrink:0;">{tl}</span>'
                  f'<a href="{a["link"]}" style="font-size:13px;color:#333333;text-decoration:none;line-height:1.5;">{esc(a["title"])}</a></div>')
        H += '</div>'

    H += '<div style="padding:18px 32px;border-top:1px solid #eeeeee;text-align:center;font-size:12px;color:#cccccc;">📬 좋은 하루 보내세요 ✨</div>'
    H += '</div></body>'
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>{H}</html>'


# ── 주간 HTML ──────────────────────────────────────────────
def build_weekly_html(summary, ai_top, scm_top, top_kw, ai_cnt, scm_cnt):
    ai_names = {f['name'] for f in AI_FEEDS}
    now = datetime.now()
    W = ('max-width:1000px;margin:0 auto;background:#ffffff;'
         'font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;'
         'color:#111111;line-height:1.6;')
    H = f'<body style="margin:0;padding:20px 0;background:#efefef;"><div style="{W}">'

    kw_badges = ''.join(
        f'<span style="font-size:11px;font-weight:700;color:#fff;background:{AI_COLOR if i%2==0 else SCM_COLOR};padding:3px 10px;border-radius:20px;">{esc(kw)}</span>'
        for i,(kw,_) in enumerate(top_kw))

    H += f'''<div style="padding:24px 32px 18px;border-bottom:2px solid #111111;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
  <div>
    <div style="font-size:10px;font-weight:700;letter-spacing:2.5px;color:#aaa;text-transform:uppercase;margin-bottom:6px;">AI × SCM WEEKLY</div>
    <div style="font-size:24px;font-weight:900;color:#111111;">📅 이번 주 하이라이트</div>
    <div style="font-size:13px;color:#aaa;margin-top:5px;">{now.year}년 {now.month}월 {now.day}일 · {ai_cnt+scm_cnt}건 큐레이션</div>
  </div>
  <div style="display:flex;flex-wrap:wrap;gap:6px;">{kw_badges}</div>
</div>'''

    if summary.get('summary'):
        H += f'''<div style="padding:18px 32px;border-bottom:1px solid #eee;">
  <div style="font-size:10px;font-weight:700;letter-spacing:2px;color:#bbb;text-transform:uppercase;margin-bottom:10px;">📝 이번 주 에디터 노트</div>
  <div style="padding:16px 18px;background:#fafafa;border-radius:8px;border-left:3px solid #ddd;font-size:14px;color:#444;line-height:1.85;">{esc(summary["summary"])}</div>
</div>'''

    H += '<div style="padding:24px 32px;border-bottom:1px solid #eee;">'
    H += '<div style="font-size:12px;font-weight:800;color:#111;letter-spacing:1px;margin-bottom:16px;text-transform:uppercase;">🏆 이번 주 픽</div>'
    H += '<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;"><tr>'
    H += f'''<td width="48%" valign="top" style="padding-right:14px;">
  <div style="padding:18px;border-radius:8px;border:1px solid #eee;border-top:3px solid {AI_COLOR};">
    <div style="font-size:10px;font-weight:700;color:{AI_COLOR};letter-spacing:1px;margin-bottom:10px;">🥇 AI 픽 오브 더 위크</div>
    <div style="font-size:15px;font-weight:700;color:#111;line-height:1.4;margin-bottom:8px;">{esc(summary.get("ai_pick_title",""))}</div>
    <div style="font-size:13px;color:#666;line-height:1.6;">{esc(summary.get("ai_pick_reason",""))}</div>
  </div>
</td><td width="4%"></td>
<td width="48%" valign="top" style="padding-left:14px;">
  <div style="padding:18px;border-radius:8px;border:1px solid #eee;border-top:3px solid {SCM_COLOR};">
    <div style="font-size:10px;font-weight:700;color:{SCM_COLOR};letter-spacing:1px;margin-bottom:10px;">🥇 SCM 픽 오브 더 위크</div>
    <div style="font-size:15px;font-weight:700;color:#111;line-height:1.4;margin-bottom:8px;">{esc(summary.get("scm_pick_title",""))}</div>
    <div style="font-size:13px;color:#666;line-height:1.6;">{esc(summary.get("scm_pick_reason",""))}</div>
  </div>
</td>'''
    H += '</tr></table></div>'

    H += '<div style="padding:20px 32px;background:#fafafa;border-top:1px solid #eee;">'
    H += '<div style="font-size:11px;font-weight:700;letter-spacing:2px;color:#aaa;text-transform:uppercase;margin-bottom:14px;">📋 이번 주 전체 기사</div>'
    for a in ai_top + scm_top:
        is_ai = a['source'] in ai_names
        tc = AI_COLOR if is_ai else SCM_COLOR
        tl = 'AI' if is_ai else 'SCM'
        H += (f'<div style="padding:9px 0;border-bottom:1px solid #eee;display:flex;align-items:baseline;gap:8px;">'
              f'<span style="font-size:10px;font-weight:700;color:#fff;background:{tc};padding:2px 8px;border-radius:20px;white-space:nowrap;flex-shrink:0;">{tl}</span>'
              f'<a href="{a["link"]}" style="font-size:13px;color:#333;text-decoration:none;line-height:1.5;">{esc(a["title"])}</a></div>')
    H += f'''<div style="margin-top:16px;padding:14px 16px;background:#fff;border-radius:8px;border:1px solid #eee;display:flex;gap:24px;">
  <div><div style="font-size:11px;color:#aaa;margin-bottom:4px;">총 기사</div><div style="font-size:20px;font-weight:700;">{ai_cnt+scm_cnt}건</div></div>
  <div><div style="font-size:11px;color:{AI_COLOR};margin-bottom:4px;">AI</div><div style="font-size:20px;font-weight:700;">{ai_cnt}건</div></div>
  <div><div style="font-size:11px;color:{SCM_COLOR};margin-bottom:4px;">SCM</div><div style="font-size:20px;font-weight:700;">{scm_cnt}건</div></div>
</div>'''
    H += '</div>'
    H += '<div style="padding:18px 32px;border-top:1px solid #eee;text-align:center;font-size:12px;color:#ccc;">📬 좋은 주말 보내세요 ✨</div>'
    H += '</div></body>'
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>{H}</html>'


# ── 실행 ───────────────────────────────────────────────────
if __name__ == '__main__':
    if '--weekly' in sys.argv:
        send_weekly()
    else:
        main()
