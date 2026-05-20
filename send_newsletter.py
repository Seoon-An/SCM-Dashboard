"""
AI × SCM Daily Newsletter
매일 아침 AI와 SCM 뉴스를 정리해서 메일로 발송합니다.
"""

import json
import os
import re
import smtplib
from calendar import timegm
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import feedparser
import requests


# ── 설정 불러오기 ───────────────────────────────────────────
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


# ── 메인 함수 ──────────────────────────────────────────────
def main():
    since    = datetime.now(timezone.utc) - timedelta(hours=24)
    disabled = set(config.get('disabledFeeds', []))

    active_ai  = [f for f in AI_FEEDS  if f['name'] not in disabled]
    active_scm = [f for f in SCM_FEEDS if f['name'] not in disabled]

    print('Fetching feeds...')
    ai_articles  = collect_articles(active_ai, since)
    scm_articles = collect_articles(active_scm, since)
    print(f'AI: {len(ai_articles)}건, SCM: {len(scm_articles)}건')

    if not ai_articles and not scm_articles:
        print('새 기사가 없습니다. 발송 건너뜀.')
        return

    per_feed = config.get('topPerFeed', 2)
    ai_top   = pick_top(ai_articles,  per_feed, config.get('maxAiCards', 4))
    scm_top  = pick_top(scm_articles, per_feed, config.get('maxScmCards', 4))
    q_hits   = pick_quick_hits(ai_articles + scm_articles, ai_top + scm_top,
                                config.get('maxQuickHits', 12))

    if ai_top:
        print('히어로 이미지 가져오는 중...')
        ai_top[0]['hero_image'] = fetch_og_image(ai_top[0]['link'])

    print('AI 인사이트 생성 중...')
    for article in ai_top:
        article.update(summarize(article))
        article.update(tag_scm_relevance(article))

    print('SCM 인사이트 생성 중...')
    for article in scm_top:
        article.update(summarize(article))

    print('에디터 노트 생성 중...')
    editor_note = generate_editor_note(ai_top, scm_top, q_hits)

    html    = build_html(editor_note, ai_top, scm_top, q_hits)
    subject = f'☕ [AI × SCM Daily] {format_kr_date(datetime.now())}'

    print('메일 발송 중...')
    send_email(subject, html)
    print('완료!')


# ── RSS 수집 ───────────────────────────────────────────────
def collect_articles(feeds, since):
    """피드 목록에서 24시간 이내 기사를 모아 반환합니다."""
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
                description = clean_text(content)[:600]

                articles.append({
                    'title':       title,
                    'link':        entry.get('link', ''),
                    'date':        date,
                    'description': description,
                    'source':      feed['name'],
                })
        except Exception as e:
            print(f'  건너뜀 {feed["name"]}: {e}')
    return articles


def clean_text(s):
    """HTML 태그와 특수문자를 제거하고 텍스트를 정리합니다."""
    s = re.sub(r'<[^>]+>', ' ', str(s or ''))
    for old, new in [('&nbsp;', ' '), ('&amp;', '&'), ('&lt;', '<'),
                     ('&gt;', '>'), ('&quot;', '"'), ('&#39;', "'")]:
        s = s.replace(old, new)
    s = re.sub(r'&[a-z]+;', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


# ── 기사 선별 ──────────────────────────────────────────────
def pick_top(articles, per_feed, max_total):
    """매체당 최신 N건씩 뽑아 전체 상위 max_total건 반환합니다."""
    by_feed = {}
    for a in articles:
        by_feed.setdefault(a['source'], []).append(a)

    picked = []
    for feed_articles in by_feed.values():
        feed_articles.sort(key=lambda x: x['date'], reverse=True)
        picked.extend(feed_articles[:per_feed])

    picked.sort(key=lambda x: x['date'], reverse=True)
    return picked[:max_total]


def pick_quick_hits(all_articles, already_picked, max_hits):
    """메인 카드에 포함되지 않은 기사들을 Quick Hits로 반환합니다."""
    seen = {a['link'] for a in already_picked}
    remaining = [a for a in all_articles if a['link'] not in seen]
    remaining.sort(key=lambda x: x['date'], reverse=True)
    return remaining[:max_hits]


# ── OG 이미지 ──────────────────────────────────────────────
def fetch_og_image(url):
    """기사 URL에서 OG 이미지 URL을 가져옵니다. 없으면 None 반환."""
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        html = res.text[:15000]
        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        ]
        for pattern in patterns:
            m = re.search(pattern, html, re.IGNORECASE)
            if m and m.group(1).startswith('http'):
                return m.group(1)
    except Exception:
        pass
    return None


# ── Gemini API ─────────────────────────────────────────────
def call_gemini(prompt, as_json=False):
    """Gemini에 프롬프트를 보내고 응답 텍스트를 반환합니다."""
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
    """기사를 '무슨 일 / 왜 중요 / 시사점' 3단 구조로 요약합니다."""
    prompt = f"""다음 기사를 SCM/물류/이커머스 종사자 관점에서 분석해줘.
원문 없이도 핵심 파악 가능하게. 각 항목 2-3문장. 영문이면 한국어로 의역.
기사: {article['title']} / {article['description']}
JSON만: {{"what":"무슨 일","why":"왜 중요","implication":"시사점"}}"""
    try:
        data = json.loads(call_gemini(prompt, as_json=True))
        return {
            'what':        data.get('what', ''),
            'why':         data.get('why', ''),
            'implication': data.get('implication', ''),
        }
    except Exception:
        return {'what': article['description'][:200], 'why': '', 'implication': ''}


def tag_scm_relevance(article):
    """AI 기사의 SCM 적용 가능성을 1-5점으로 평가합니다."""
    prompt = f"""AI 기사의 K-brand FBA 이커머스 적용 가능성:
5=즉시 도입 / 4=직접 시사점 / 3=간접 가치 / 2=일반 트렌드 / 1=무관
3점 이상이면 50자 이내 한국어 코멘트. 2점 이하면 comment를 null로.
기사: {article['title']}
JSON만: {{"score":<int>,"comment":<string or null>}}"""
    try:
        data = json.loads(call_gemini(prompt, as_json=True))
        return {'scm_score': data.get('score', 0), 'scm_comment': data.get('comment')}
    except Exception:
        return {'scm_score': 0, 'scm_comment': None}


def generate_editor_note(ai_top, scm_top, q_hits):
    """오늘 헤드라인을 보고 업무 맥락에 맞는 짧은 에디터 노트를 생성합니다."""
    ai_names  = {f['name'] for f in AI_FEEDS}
    ai_titles = [f"- {a['title']}" for a in
                 (ai_top + [x for x in q_hits if x['source'] in ai_names])[:8]]
    scm_titles = [f"- {a['title']}" for a in
                  (scm_top + [x for x in q_hits if x['source'] not in ai_names])[:8]]
    keywords = ', '.join(config.get('keywords', []))

    prompt = f"""너는 K-brand FBA 글로벌 이커머스 SCM Operations Manager 동료야.
관심 키워드: {keywords}
[AI] {chr(10).join(ai_titles)}
[SCM] {chr(10).join(scm_titles)}
주목할 thread 3-4문장. Morning Brew 톤.
[제약] 특정 회사명·이직 언급 금지.
에디터 노트(본문만):"""
    return call_gemini(prompt).strip()


# ── 이메일 발송 ────────────────────────────────────────────
def send_email(subject, html):
    """Gmail SMTP를 이용해 HTML 메일을 발송합니다."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = f'"AI × SCM Daily" <{GMAIL_USER}>'
    msg['To']      = TO_EMAIL
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_USER, GMAIL_PASS)
        server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())


# ── HTML 이메일 생성 ───────────────────────────────────────
def esc(s):
    """HTML 특수문자를 이스케이프합니다."""
    return (str(s or '')
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;').replace("'", '&#39;'))


def insight_rows(article, color):
    """무슨 일 / 왜 중요 / 시사점 세 줄을 HTML로 생성합니다."""
    html = ''
    lbl_style = f'font-size:10px;font-weight:800;letter-spacing:2px;text-transform:uppercase;display:block;margin-bottom:4px;color:{color};'
    txt_style  = 'font-size:14px;color:#333;line-height:1.7;margin:0;'
    row_style  = 'margin-bottom:14px;'
    for label, key in [('무슨 일', 'what'), ('왜 중요', 'why'), ('시사점', 'implication')]:
        if article.get(key):
            html += f'<div style="{row_style}"><span style="{lbl_style}">{label}</span><p style="{txt_style}">{esc(article[key])}</p></div>'
    return html


def scm_tag_html(article, color):
    """SCM 적용 포인트 태그 HTML을 생성합니다. 3점 미만이면 빈 문자열 반환."""
    score   = article.get('scm_score', 0)
    comment = article.get('scm_comment')
    if score < 3 or not comment:
        return ''
    stars = '★' * score + '☆' * (5 - score)
    return (f'<div style="padding:12px 16px;border-radius:8px;margin:14px 0;font-size:13px;'
            f'line-height:1.5;background:{color}18;border-left:3px solid {color};">'
            f'<strong style="color:{color};display:block;margin-bottom:4px;">💡 SCM 적용 포인트 {stars}</strong>'
            f'{esc(comment)}</div>')


def render_hero(article, color):
    """첫 번째 AI 기사를 히어로 섹션으로 렌더링합니다."""
    img_url = article.get('hero_image')
    if img_url:
        top = (f'<img src="{img_url}" alt="" style="display:block;width:100%;border-radius:12px 12px 0 0;">'
               f'<div style="background:{color};padding:20px 26px;">')
    else:
        top = f'<div style="background:linear-gradient(135deg,{color},{color}cc);padding:44px 28px;border-radius:12px 12px 0 0;">'

    return f"""<div style="background:#fff;border-radius:12px;margin-bottom:14px;overflow:hidden;border:1px solid #e8e2d8;">
{top}
  <span style="font-size:10px;font-weight:800;letter-spacing:2px;color:rgba(255,255,255,.7);display:block;margin-bottom:8px;">🌟 오늘의 피처드</span>
  <div style="font-size:22px;font-weight:900;color:#fff;line-height:1.35;">{esc(article['title'])}</div>
  <div style="font-size:12px;color:rgba(255,255,255,.65);margin-top:6px;">{esc(article['source'])}</div>
</div>
<div style="padding:22px 24px;">
  {insight_rows(article, color)}
  {scm_tag_html(article, color)}
  <div style="font-size:12px;color:#999;margin:16px 0 0;">
    <a href="{article['link']}" style="color:{color};font-weight:700;text-decoration:none;">원문 →</a>
  </div>
</div></div>"""


def render_card(article, is_ai, color):
    """일반 카드를 렌더링합니다."""
    return f"""<div style="background:#fff;border-radius:12px;margin-bottom:14px;overflow:hidden;border:1px solid #e8e2d8;">
<div style="height:4px;background:{color};"></div>
<div style="padding:22px 24px;">
  <div style="font-size:18px;font-weight:900;color:#1a1a1a;margin:0 0 18px;line-height:1.35;">{esc(article['title'])}</div>
  {insight_rows(article, color)}
  {scm_tag_html(article, color) if is_ai else ''}
  <div style="font-size:12px;color:#999;margin:16px 0 0;">
    {esc(article['source'])} &nbsp;·&nbsp;
    <a href="{article['link']}" style="color:{color};font-weight:700;text-decoration:none;">원문 →</a>
  </div>
</div></div>"""


def build_html(editor_note, ai_top, scm_top, q_hits):
    """뉴스레터 전체 HTML을 조립합니다."""
    ai_names   = {f['name'] for f in AI_FEEDS}
    wrap_style = ('max-width:1100px;margin:0 auto;padding:28px 24px;background:#F4F0EB;'
                  'font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;'
                  'color:#1a1a1a;line-height:1.6;')
    sec_hdr    = 'padding:14px 22px;border-radius:10px;margin:36px 0 16px;font-weight:900;font-size:15px;'

    html = f'<body style="margin:0;padding:0;background:#F4F0EB;"><div style="{wrap_style}">'

    # 헤더
    html += f'''<div style="padding:24px 0 20px;border-bottom:3px solid #1a1a1a;margin-bottom:28px;">
  <div style="margin:0;font-size:28px;font-weight:900;">☕ 굿모닝!</div>
  <div style="color:#888;font-size:13px;margin-top:6px;">{format_kr_date(datetime.now())} &nbsp;·&nbsp; AI × SCM 다이제스트</div>
</div>'''

    # 에디터 노트
    if editor_note:
        html += f'''<div style="background:#fff;border-left:5px solid #1a1a1a;padding:20px 24px;margin-bottom:32px;border-radius:0 10px 10px 0;">
  <span style="font-size:10px;font-weight:800;letter-spacing:2px;color:#888;text-transform:uppercase;display:block;margin-bottom:8px;">📝 오늘의 한 마디</span>
  <p style="font-size:15px;color:#222;line-height:1.75;margin:0;">{esc(editor_note)}</p>
</div>'''

    # AI 섹션
    if ai_top:
        html += f'<div style="{sec_hdr}background:{AI_COLOR};color:#fff;">🤖 AI 핫이슈</div>'
        html += render_hero(ai_top[0], AI_COLOR)
        for article in ai_top[1:]:
            html += render_card(article, is_ai=True, color=AI_COLOR)

    # SCM 섹션
    if scm_top:
        html += f'<div style="{sec_hdr}background:{SCM_COLOR};color:#fff;">📦 SCM · 물류 핫이슈</div>'
        for article in scm_top:
            html += render_card(article, is_ai=False, color=SCM_COLOR)

    # Quick Hits
    if q_hits:
        html += '<div style="font-size:12px;font-weight:800;letter-spacing:2px;color:#888;text-transform:uppercase;margin:36px 0 12px;">⚡ 빠르게 보는 헤드라인</div>'
        html += '<div style="background:#fff;border-radius:12px;padding:22px 24px;border:1px solid #e8e2d8;">'
        for i, article in enumerate(q_hits):
            dot_color  = AI_COLOR if article['source'] in ai_names else SCM_COLOR
            border     = 'border-bottom:1px solid #f4f0eb;' if i < len(q_hits) - 1 else ''
            html += (f'<div style="padding:10px 0;{border}font-size:14px;">'
                     f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{dot_color};margin-right:10px;vertical-align:middle;"></span>'
                     f'<a href="{article["link"]}" style="color:#1a1a1a;text-decoration:none;font-weight:500;">{esc(article["title"])}</a>'
                     f'<span style="color:#bbb;font-size:11px;margin-left:8px;">{esc(article["source"])}</span></div>')
        html += '</div>'

    html += '<div style="margin-top:44px;padding-top:22px;border-top:2px solid #1a1a1a;color:#999;font-size:13px;text-align:center;">📬 좋은 하루 보내세요 ✨</div>'
    html += '</div></body>'

    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>{html}</html>'


def format_kr_date(d):
    days = ['월', '화', '수', '목', '금', '토', '일']
    return f'{d.year}년 {d.month}월 {d.day}일 ({days[d.weekday()]})'


# ── 실행 ───────────────────────────────────────────────────
if __name__ == '__main__':
    main()
