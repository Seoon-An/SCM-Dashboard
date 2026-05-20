"""
AI × SCM Daily Newsletter
히어로 + 2단 레이아웃 | 친절한 존댓말 에디터 톤
히어로: AI/SCM 전체 중 가장 최신 기사
"""

import json
import os
import re
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import feedparser
import requests


# ── 설정 ───────────────────────────────────────────────────
with open('config.json', encoding='utf-8') as f:
    config = json.load(f)

GEMINI_KEY   = os.environ['GEMINI_API_KEY']
GEMINI_MODEL = 'gemini-2.5-flash'
TO_EMAIL     = os.environ['TO_EMAIL']
GMAIL_USER   = os.environ['GMAIL_ADDRESS']
GMAIL_PASS   = os.environ['GMAIL_APP_PASSWORD']

AI_COLOR  = '#E97451'
SCM_COLOR = '#1E7E9E'


# ── 피드 목록 ──────────────────────────────────────────────
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


# ── 메인 ───────────────────────────────────────────────────
def main():
    since    = datetime.now(timezone.utc) - timedelta(hours=24)
    disabled = set(config.get('disabledFeeds', []))

    active_ai  = [f for f in AI_FEEDS  if f['name'] not in disabled]
    active_scm = [f for f in SCM_FEEDS if f['name'] not in disabled]

    print('Fetching feeds...')
    ai_articles  = collect_articles(active_ai,  since)
    scm_articles = collect_articles(active_scm, since)
    print(f'AI: {len(ai_articles)}건, SCM: {len(scm_articles)}건')

    if not ai_articles and not scm_articles:
        print('새 기사가 없습니다.')
        return

    per_feed = config.get('topPerFeed', 2)
    ai_top   = pick_top(ai_articles,  per_feed, config.get('maxAiCards', 4) + 1)
    scm_top  = pick_top(scm_articles, per_feed, config.get('maxScmCards', 4) + 1)
    q_hits   = pick_quick_hits(ai_articles + scm_articles, ai_top + scm_top,
                                config.get('maxQuickHits', 12))

    print('이미지 가져오는 중...')
    for a in ai_top + scm_top:
        a['og_image'] = fetch_og_image(a['link'])

    print('AI 인사이트 생성 중...')
    for a in ai_top:
        a.update(summarize(a))
        a.update(tag_scm_relevance(a))

    print('SCM 인사이트 생성 중...')
    for a in scm_top:
        a.update(summarize(a))

    print('에디터 노트 생성 중...')
    editor_note = generate_editor_note(ai_top, scm_top, q_hits)

    html    = build_html(editor_note, ai_top, scm_top, q_hits)
    subject = f'☕ [AI × SCM Daily] {format_kr_date(datetime.now())}'

    print('발송 중...')
    send_email(subject, html)
    print('완료!')


# ── RSS 수집 ───────────────────────────────────────────────
def collect_articles(feeds, since):
    articles = []
    for feed in feeds:
        try:
            parsed = feedparser.parse(feed['url'])
            for entry in parsed.entries:
                published = entry.get('published_parsed') or entry.get('updated_parsed')
                if not published:
                    continue
                date = datetime(*published[:6], tzinfo=timezone.utc)
                if date < since:
                    continue
                title = clean_text(entry.get('title', ''))
                if not title:
                    continue
                content = (entry.get('summary') or
                           (entry.get('content') or [{}])[0].get('value', ''))
                articles.append({
                    'title':       title,
                    'link':        entry.get('link', ''),
                    'date':        date,
                    'description': clean_text(content)[:600],
                    'source':      feed['name'],
                })
        except Exception as e:
            print(f'  건너뜀 {feed["name"]}: {e}')
    return articles


def clean_text(s):
    s = re.sub(r'<[^>]+>', ' ', str(s or ''))
    for old, new in [('&nbsp;', ' '), ('&amp;', '&'), ('&lt;', '<'),
                     ('&gt;', '>'), ('&quot;', '"'), ('&#39;', "'")]:
        s = s.replace(old, new)
    return re.sub(r'\s+', ' ', s).strip()


def pick_top(articles, per_feed, max_total):
    by_feed = {}
    for a in articles:
        by_feed.setdefault(a['source'], []).append(a)
    picked = []
    for arr in by_feed.values():
        arr.sort(key=lambda x: x['date'], reverse=True)
        picked.extend(arr[:per_feed])
    picked.sort(key=lambda x: x['date'], reverse=True)
    return picked[:max_total]


def pick_quick_hits(all_articles, already_picked, max_hits):
    seen = {a['link'] for a in already_picked}
    remaining = [a for a in all_articles if a['link'] not in seen]
    remaining.sort(key=lambda x: x['date'], reverse=True)
    return remaining[:max_hits]


# ── OG 이미지 ──────────────────────────────────────────────
def fetch_og_image(url):
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        html = res.text[:15000]
        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        ]
        for p in patterns:
            m = re.search(p, html, re.IGNORECASE)
            if m and m.group(1).startswith('http'):
                return m.group(1)
    except Exception:
        pass
    return None


# ── Gemini ─────────────────────────────────────────────────
def call_gemini(prompt, as_json=False):
    url  = f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}'
    body = {'contents': [{'parts': [{'text': prompt}]}]}
    if as_json:
        body['generationConfig'] = {'responseMimeType': 'application/json'}
    res  = requests.post(url, json=body, timeout=30)
    data = res.json()
    return (data.get('candidates', [{}])[0]
                .get('content', {})
                .get('parts', [{}])[0]
                .get('text', ''))


def summarize(article):
    """친절한 존댓말 에디터 스타일로 기사를 요약합니다."""
    prompt = f"""다음 기사를 뉴스레터 에디터가 독자에게 친절하게 설명해주듯 요약해줘.
tone: 친절한 존댓말. "이번에 흥미로운 소식이 있는데요~" 같은 따뜻하고 친근한 에디터 스타일.
두 파트:
headline — 흥미롭게 한 문장으로, 읽고 싶어지게 (존댓말 불필요, 임팩트 위주)
body — 모르는 사람도 이해할 수 있게 쉬운 말로 3-4문장. 레이블 없이 자연스럽게. 존댓말. 이모지 한두 개 OK.

영문이면 자연스러운 한국어로 의역.

기사 제목: {article['title']}
기사 내용: {article['description']}

JSON만: {{"headline": "...", "body": "..."}}"""
    try:
        data = json.loads(call_gemini(prompt, as_json=True))
        return {'headline': data.get('headline', ''), 'body': data.get('body', '')}
    except Exception:
        return {'headline': article['title'], 'body': article['description'][:200]}


def tag_scm_relevance(article):
    """AI 기사의 SCM 적용 가능성을 평가합니다."""
    prompt = f"""AI 기사의 K-brand FBA 이커머스 적용 가능성:
5=즉시 도입 / 4=직접 시사점 / 3=간접 가치 / 2=일반 트렌드 / 1=무관
3점 이상이면 40자 이내 한국어 코멘트. 2점 이하면 comment=null.
기사: {article['title']}
JSON만: {{"score":<int>,"comment":<string or null>}}"""
    try:
        data = json.loads(call_gemini(prompt, as_json=True))
        return {'scm_score': data.get('score', 0), 'scm_comment': data.get('comment')}
    except Exception:
        return {'scm_score': 0, 'scm_comment': None}


def generate_editor_note(ai_top, scm_top, q_hits):
    """오늘의 에디터 노트를 생성합니다."""
    ai_names   = {f['name'] for f in AI_FEEDS}
    ai_titles  = [f"- {a['title']}" for a in
                  (ai_top + [x for x in q_hits if x['source'] in ai_names])[:8]]
    scm_titles = [f"- {a['title']}" for a in
                  (scm_top + [x for x in q_hits if x['source'] not in ai_names])[:8]]
    keywords   = ', '.join(config.get('keywords', []))

    prompt = f"""너는 K-brand FBA 글로벌 이커머스 SCM Operations Manager 독자를 위한 뉴스레터 에디터야.
관심 키워드: {keywords}
[AI] {chr(10).join(ai_titles)}
[SCM] {chr(10).join(scm_titles)}
오늘 주목할 만한 내용을 3-4문장으로. 친절한 존댓말. Morning Brew처럼 따뜻하게.
[제약] 특정 회사명·이직 언급 금지.
에디터 노트(본문만):"""
    return call_gemini(prompt).strip()


# ── 이메일 발송 ────────────────────────────────────────────
def send_email(subject, html):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = f'"AI × SCM Daily" <{GMAIL_USER}>'
    msg['To']      = TO_EMAIL
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_USER, GMAIL_PASS)
        server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())


# ── HTML 생성 ──────────────────────────────────────────────
def esc(s):
    return (str(s or '')
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;').replace("'", '&#39;'))


def format_kr_date(d):
    days = ['월', '화', '수', '목', '금', '토', '일']
    return f'{d.year}년 {d.month}월 {d.day}일 ({days[d.weekday()]})'


def scm_tag_block(article, color):
    """SCM 적용 포인트 태그. 3점 이상일 때만 표시."""
    score   = article.get('scm_score', 0)
    comment = article.get('scm_comment')
    if score < 3 or not comment:
        return ''
    return (f'<div style="padding:8px 10px;background:{color}18;border-left:3px solid {color};'
            f'font-size:12px;color:#444;line-height:1.5;border-radius:0 4px 4px 0;margin-bottom:8px;">'
            f'💡 {esc(comment)}</div>')


def render_hero(article, color=None):
    """AI/SCM 하이라이트 기사를 풀 히어로로 렌더링합니다."""
    if color is None:
        color = AI_COLOR
    img      = article.get('og_image')
    headline = esc(article.get('headline') or article['title'])
    body     = esc(article.get('body', ''))
    source   = esc(article['source'])
    link     = article['link']

    img_block = (f'<a href="{link}"><img src="{img}" alt="" width="100%" '
                 f'style="display:block;max-width:100%;height:280px;object-fit:cover;"></a>'
                 if img else
                 f'<a href="{link}"><div style="height:200px;background:linear-gradient(135deg,{color},{color}cc);'
                 f'display:block;"></div></a>')

    return f'''<div style="margin-bottom:28px;border-radius:12px;overflow:hidden;border:1px solid #e8e8e8;">
  {img_block}
  <div style="background:{color};padding:18px 26px;">
    <div style="font-size:10px;font-weight:800;letter-spacing:2px;color:rgba(255,255,255,.7);margin-bottom:6px;">🌟 오늘의 하이라이트</div>
    <a href="{link}" style="text-decoration:none;">
      <div style="font-size:20px;font-weight:900;color:#fff;line-height:1.35;">{headline}</div>
    </a>
    <div style="font-size:12px;color:rgba(255,255,255,.6);margin-top:6px;">{source}</div>
  </div>
  <div style="padding:20px 26px;background:#fff;">
    <div style="font-size:14px;color:#444;line-height:1.75;">{body}</div>
    {scm_tag_block(article, color)}
  </div>
</div>'''


def render_col_card(article, color, show_scm_tag=False):
    """컬럼용 카드. 제목 클릭하면 원문으로 이동."""
    img  = article.get('og_image')
    link = article['link']

    img_block = (f'<a href="{link}"><img src="{img}" alt="" width="100%" '
                 f'style="display:block;max-width:100%;height:170px;object-fit:cover;"></a>'
                 if img else
                 f'<a href="{link}"><div style="height:100px;background:{color};display:block;"></div></a>')

    headline = esc(article.get('headline') or article['title'])
    body     = esc(article.get('body', ''))
    source   = esc(article['source'])

    return f'''<div style="margin-bottom:18px;border-radius:10px;overflow:hidden;border:1px solid #e8e8e8;background:#fff;">
  {img_block}
  <div style="padding:14px 16px;">
    <a href="{link}" style="text-decoration:none;">
      <div style="font-size:15px;font-weight:700;color:#111;line-height:1.4;margin-bottom:8px;">{headline}</div>
    </a>
    <div style="font-size:13px;color:#555;line-height:1.65;margin-bottom:8px;">{body}</div>
    {scm_tag_block(article, color) if show_scm_tag else ''}
    <div style="font-size:11px;color:#ccc;margin-top:8px;">{source}</div>
  </div>
</div>'''


def build_html(editor_note, ai_top, scm_top, q_hits):
    """뉴스레터 전체 HTML. 히어로 + 2단 + Quick Hits."""
    ai_names = {f['name'] for f in AI_FEEDS}

    # 히어로: AI + SCM 전체 중 가장 최신 기사
    all_combined = sorted(ai_top + scm_top, key=lambda x: x['date'], reverse=True)
    hero_article = all_combined[0] if all_combined else None
    hero_color   = AI_COLOR if hero_article in ai_top else SCM_COLOR
    ai_col       = [a for a in ai_top  if a is not hero_article]
    scm_col      = [a for a in scm_top if a is not hero_article]

    wrap = ('max-width:1000px;margin:0 auto;background:#ffffff;'
            'font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;'
            'color:#111;line-height:1.6;')

    html = f'<body style="margin:0;padding:20px 0;background:#efefef;"><div style="{wrap}">'

    # 헤더
    html += f'''<div style="padding:24px 32px 18px;border-bottom:2px solid #111;">
  <div style="font-size:10px;font-weight:800;letter-spacing:2px;color:#aaa;text-transform:uppercase;margin-bottom:6px;">AI × SCM Daily</div>
  <div style="font-size:24px;font-weight:900;color:#111;letter-spacing:-0.3px;">☕ 굿모닝!</div>
  <div style="font-size:13px;color:#aaa;margin-top:5px;">{format_kr_date(datetime.now())}</div>
</div>'''

    # 에디터 노트
    if editor_note:
        html += f'''<div style="padding:18px 32px;border-bottom:1px solid #eee;">
  <div style="font-size:10px;font-weight:800;letter-spacing:2px;color:#bbb;text-transform:uppercase;margin-bottom:8px;">📝 오늘의 한 마디</div>
  <div style="font-size:15px;color:#333;line-height:1.75;">{esc(editor_note)}</div>
</div>'''

    # 히어로
    if hero_article:
        html += f'<div style="padding:24px 32px 0;">{render_hero(hero_article, hero_color)}</div>'

    # 2단 레이아웃
    html += '<div style="padding:0 32px 24px;">'
    html += '<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">'
    html += '<tr>'

    # 왼쪽: AI
    html += '<td width="48%" valign="top" style="padding-right:14px;">'
    if ai_col:
        html += (f'<div style="font-size:12px;font-weight:800;color:{AI_COLOR};'
                 f'letter-spacing:1px;padding-bottom:10px;border-bottom:2px solid {AI_COLOR};'
                 f'margin-bottom:14px;text-transform:uppercase;">🤖 AI 핫이슈</div>')
        for a in ai_col:
            html += render_col_card(a, AI_COLOR, show_scm_tag=True)
    html += '</td>'

    html += '<td width="4%" valign="top"></td>'

    # 오른쪽: SCM
    html += '<td width="48%" valign="top" style="padding-left:14px;">'
    if scm_col:
        html += (f'<div style="font-size:12px;font-weight:800;color:{SCM_COLOR};'
                 f'letter-spacing:1px;padding-bottom:10px;border-bottom:2px solid {SCM_COLOR};'
                 f'margin-bottom:14px;text-transform:uppercase;">📦 SCM 핫이슈</div>')
        for a in scm_col:
            html += render_col_card(a, SCM_COLOR)
    html += '</td>'

    html += '</tr></table></div>'

    # Quick Hits
    if q_hits:
        html += '<div style="padding:20px 32px;background:#fafafa;border-top:1px solid #eee;">'
        html += (f'<div style="font-size:11px;font-weight:800;letter-spacing:2px;'
                 f'color:#aaa;text-transform:uppercase;margin-bottom:14px;">⚡ 빠르게 보는 헤드라인</div>')
        for i, a in enumerate(q_hits):
            is_ai     = a['source'] in ai_names
            tag_color = AI_COLOR if is_ai else SCM_COLOR
            tag_label = 'AI' if is_ai else 'SCM'
            border    = '' if i == len(q_hits) - 1 else 'border-bottom:1px solid #eee;'
            html += (f'<div style="padding:9px 0;{border}display:flex;align-items:baseline;gap:8px;">'
                     f'<span style="font-size:10px;font-weight:700;color:#fff;background:{tag_color};'
                     f'padding:2px 8px;border-radius:20px;white-space:nowrap;flex-shrink:0;">{tag_label}</span>'
                     f'<a href="{a["link"]}" style="font-size:13px;color:#333;text-decoration:none;'
                     f'line-height:1.5;">{esc(a["title"])}</a></div>')
        html += '</div>'

    # 푸터
    html += '<div style="padding:18px 32px;border-top:1px solid #eee;text-align:center;font-size:12px;color:#ccc;">📬 좋은 하루 보내세요 ✨</div>'
    html += '</div></body>'

    return (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"></head>{html}</html>')


# ── 실행 ───────────────────────────────────────────────────
if __name__ == '__main__':
    main()
