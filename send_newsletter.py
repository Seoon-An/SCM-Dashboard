"""
AI × SCM Daily Newsletter
2단 레이아웃 버전 — AI 왼쪽 / SCM 오른쪽, 썸네일 이미지 포함
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


# ── 메인 함수 ──────────────────────────────────────────────
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
    ai_top   = pick_top(ai_articles,  per_feed, config.get('maxAiCards',   4))
    scm_top  = pick_top(scm_articles, per_feed, config.get('maxScmCards',  4))
    q_hits   = pick_quick_hits(ai_articles + scm_articles, ai_top + scm_top,
                                config.get('maxQuickHits', 12))

    # 썸네일 이미지 수집
    print('이미지 가져오는 중...')
    for a in ai_top + scm_top:
        a['og_image'] = fetch_og_image(a['link'])

    # Gemini 인사이트 생성
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


# ── Gemini API ─────────────────────────────────────────────
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
    """기사를 뉴스레터 카드용 헤드라인 + 본문으로 요약합니다."""
    prompt = f"""다음 기사를 뉴스레터 카드 스타일로 요약해줘.
두 파트로 작성:
1. headline: 핵심을 한 문장으로, 읽고 싶어지도록 임팩트 있게
2. body: 왜 중요한지와 실무 시사점을 레이블 없이 자연스럽게 이어지는 2-3문장으로

영문 기사면 한국어로 자연스럽게 의역.

기사 제목: {article['title']}
기사 내용: {article['description']}

JSON만 출력: {{"headline": "...", "body": "..."}}"""
    try:
        data = json.loads(call_gemini(prompt, as_json=True))
        return {
            'headline': data.get('headline', ''),
            'body':     data.get('body', ''),
        }
    except Exception:
        return {'headline': article['title'], 'body': article['description'][:150]}


def tag_scm_relevance(article):
    """AI 기사의 SCM 적용 가능성을 1-5점으로 평가합니다."""
    prompt = f"""AI 기사의 K-brand FBA 이커머스 적용 가능성:
5=즉시 도입 / 4=직접 시사점 / 3=간접 가치 / 2=일반 트렌드 / 1=무관
3점 이상이면 40자 이내 한국어 코멘트. 2점 이하면 comment를 null로.
기사: {article['title']}
JSON만: {{"score":<int>,"comment":<string or null>}}"""
    try:
        data = json.loads(call_gemini(prompt, as_json=True))
        return {'scm_score': data.get('score', 0), 'scm_comment': data.get('comment')}
    except Exception:
        return {'scm_score': 0, 'scm_comment': None}


def generate_editor_note(ai_top, scm_top, q_hits):
    """오늘 헤드라인 기반 에디터 노트를 생성합니다."""
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


def render_col_card(article, color, show_scm_tag=False):
    """2단 컬럼용 카드를 렌더링합니다. 썸네일 이미지 + 헤드라인 + 본문 구성."""
    img_url = article.get('og_image')
    if img_url:
        img_block = (f'<img src="{img_url}" alt="" width="100%" '
                     f'style="display:block;max-width:100%;height:160px;'
                     f'object-fit:cover;">')
    else:
        # 이미지 없으면 컬러 블록 대체
        img_block = f'<div style="height:90px;background:{color};display:block;"></div>'

    scm_html = ''
    if show_scm_tag and article.get('scm_score', 0) >= 3 and article.get('scm_comment'):
        scm_html = (f'<div style="margin:8px 0;padding:8px 10px;'
                    f'background:{color}18;border-left:3px solid {color};'
                    f'font-size:12px;color:#444;line-height:1.5;border-radius:0 4px 4px 0;">'
                    f'💡 {esc(article["scm_comment"])}</div>')

    headline = esc(article.get('headline') or article['title'])
    body     = esc(article.get('body', ''))

    return f'''<div style="margin-bottom:16px;border-radius:10px;overflow:hidden;border:1px solid #e8e8e8;background:#fff;">
  {img_block}
  <div style="padding:14px 15px;">
    <div style="font-size:15px;font-weight:700;color:#111;line-height:1.4;margin-bottom:8px;">{headline}</div>
    <div style="font-size:13px;color:#555;line-height:1.65;margin-bottom:10px;">{body}</div>
    {scm_html}
    <div style="font-size:11px;color:#bbb;margin-top:8px;">{esc(article["source"])} &nbsp;·&nbsp;
      <a href="{article["link"]}" style="color:{color};font-weight:700;text-decoration:none;">원문 →</a>
    </div>
  </div>
</div>'''


def build_html(editor_note, ai_top, scm_top, q_hits):
    """전체 뉴스레터 HTML을 조립합니다. 2단 레이아웃 (AI 왼쪽 / SCM 오른쪽)"""
    ai_names = {f['name'] for f in AI_FEEDS}

    # 섹션 헤더 스타일
    def col_header(emoji, label, color):
        return (f'<div style="font-size:13px;font-weight:800;color:{color};'
                f'letter-spacing:1px;text-transform:uppercase;'
                f'padding-bottom:12px;border-bottom:2px solid {color};'
                f'margin-bottom:16px;">{emoji} {label}</div>')

    # 전체 래퍼
    wrap = ('max-width:700px;margin:0 auto;padding:0;background:#ffffff;'
            'font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",'
            '"Malgun Gothic",sans-serif;color:#111;line-height:1.6;')

    html = f'<body style="margin:0;padding:20px 0;background:#f0f0f0;"><div style="{wrap}">'

    # ── 헤더 ──────────────────────────────────────────────
    html += f'''<div style="padding:28px 32px 20px;border-bottom:2px solid #111;">
  <div style="font-size:11px;font-weight:700;letter-spacing:2px;color:#aaa;text-transform:uppercase;margin-bottom:8px;">AI × SCM Daily</div>
  <div style="font-size:26px;font-weight:900;color:#111;letter-spacing:-0.5px;">☕ 굿모닝!</div>
  <div style="font-size:13px;color:#aaa;margin-top:6px;">{format_kr_date(datetime.now())}</div>
</div>'''

    # ── 에디터 노트 ────────────────────────────────────────
    if editor_note:
        html += f'''<div style="padding:20px 32px;background:#fff;border-bottom:1px solid #eee;">
  <div style="font-size:10px;font-weight:800;letter-spacing:2px;color:#aaa;text-transform:uppercase;margin-bottom:8px;">📝 오늘의 한 마디</div>
  <div style="font-size:15px;color:#333;line-height:1.75;">{esc(editor_note)}</div>
</div>'''

    # ── 2단 레이아웃: AI 왼쪽 / SCM 오른쪽 ─────────────────
    html += '<div style="padding:24px 32px;">'
    html += '<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">'
    html += '<tr>'

    # 왼쪽: AI
    html += '<td width="48%" valign="top" style="padding-right:12px;">'
    html += col_header('🤖', 'AI 핫이슈', AI_COLOR)
    for a in ai_top:
        html += render_col_card(a, AI_COLOR, show_scm_tag=True)
    html += '</td>'

    # 간격
    html += '<td width="4%" valign="top"></td>'

    # 오른쪽: SCM
    html += '<td width="48%" valign="top" style="padding-left:12px;">'
    html += col_header('📦', 'SCM 핫이슈', SCM_COLOR)
    for a in scm_top:
        html += render_col_card(a, SCM_COLOR)
    html += '</td>'

    html += '</tr></table>'
    html += '</div>'

    # ── Quick Hits ─────────────────────────────────────────
    if q_hits:
        html += '<div style="padding:20px 32px;background:#fafafa;border-top:1px solid #eee;">'
        html += '<div style="font-size:11px;font-weight:800;letter-spacing:2px;color:#aaa;text-transform:uppercase;margin-bottom:14px;">⚡ 더 보기</div>'
        for i, a in enumerate(q_hits):
            is_ai   = a['source'] in ai_names
            tag_color  = AI_COLOR if is_ai else SCM_COLOR
            tag_label  = 'AI' if is_ai else 'SCM'
            border  = '' if i == len(q_hits) - 1 else 'border-bottom:1px solid #eee;'
            html += (f'<div style="padding:9px 0;{border}display:flex;align-items:baseline;gap:8px;">'
                     f'<span style="font-size:10px;font-weight:700;color:#fff;background:{tag_color};'
                     f'padding:2px 8px;border-radius:20px;white-space:nowrap;flex-shrink:0;">{tag_label}</span>'
                     f'<a href="{a["link"]}" style="font-size:13px;color:#333;text-decoration:none;line-height:1.5;">{esc(a["title"])}</a>'
                     f'</div>')
        html += '</div>'

    # ── 푸터 ──────────────────────────────────────────────
    html += '<div style="padding:20px 32px;border-top:1px solid #eee;text-align:center;font-size:12px;color:#bbb;">📬 좋은 하루 보내세요 ✨</div>'

    html += '</div></body>'
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"></head>{html}</html>')


# ── 실행 ───────────────────────────────────────────────────
if __name__ == '__main__':
    main()
