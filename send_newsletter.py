"""
AI × SCM Daily Newsletter
"""
# 매일 KST 06:00 자동 발송 (GitHub Actions 스케줄)

import json, os, re, sys, smtplib, random
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import feedparser, requests

with open('config.json', encoding='utf-8') as f:
    config = json.load(f)

GEMINI_KEY    = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL  = 'gemini-2.5-flash'
GEMINI_ENABLED = True
TO_EMAIL     = os.environ['TO_EMAIL']
GMAIL_USER   = os.environ['GMAIL_ADDRESS']
GMAIL_PASS   = os.environ['GMAIL_APP_PASSWORD']

MORNING_QUOTES = [
    # 불교
    "지금 이 순간에 충실하라. 과거는 이미 지나갔고, 미래는 아직 오지 않았다. — 붓다",
    "자기 자신을 이기는 것이 천 명의 적을 이기는 것보다 위대하다. — 법구경",
    "모든 것은 변한다. 변하지 않는 것은 변한다는 사실뿐이다. — 붓다",
    "욕심을 버리면 자유로워지고, 집착을 놓으면 평화가 온다. — 붓다",
    "남의 허물을 보지 말고, 자신의 허물을 살펴라. — 법구경",
    "마음이 고요하면 세상이 고요하다. — 선가 어록",
    "꽃은 스스로 피어나고, 그 향기는 바람이 퍼뜨린다. — 선가 어록",
    "급할수록 돌아가라. — 선가 어록",
    # 동양 철학
    "천 리 길도 한 걸음부터. — 노자",
    "물은 다투지 않고도 낮은 곳으로 흘러 결국 바다에 이른다. — 노자",
    "아는 자는 말하지 않고, 말하는 자는 알지 못한다. — 노자",
    "아는 것을 안다 하고 모르는 것을 모른다 하는 것, 그것이 앎이다. — 공자",
    "지혜로운 자는 물을 좋아하고, 인자한 자는 산을 좋아한다. — 공자",
    "배우고 때때로 익히면 또한 즐겁지 아니한가. — 공자",
    "군자는 말은 느리게 하되 행동은 민첩하게 한다. — 공자",
    # 서양 철학
    "나는 내가 아무것도 모른다는 것을 안다. — 소크라테스",
    "탁월함은 습관에서 비롯된다. — 아리스토텔레스",
    "시작이 반이다. — 아리스토텔레스",
    "지금 이 순간을 즐겨라. 다시 오지 않는다. — 호라티우스",
    "운명이 우리를 어디로 이끌든, 먼저 용기를 갖추어라. — 베르길리우스",
    "잃어버린 시간은 돌아오지 않는다. — 세네카",
    "방해받지 않는 한, 자연은 완벽하게 작동한다. — 마르쿠스 아우렐리우스",
    "네가 통제할 수 없는 것에 시간을 낭비하지 마라. — 에픽테토스",
    "인생은 짧고, 기술은 길다. — 히포크라테스",
    "우리가 두려워할 것은 두려움 그 자체뿐이다. — 프랜시스 베이컨",
]

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
    {'name': '전자신문',         'url': 'https://www.etnews.com/rss/article.xml'},
    {'name': '디지털타임스',     'url': 'https://www.dt.co.kr/rss/'},
    {'name': '매일경제',         'url': 'https://www.mk.co.kr/rss/30200030/'},
    {'name': '한국경제',         'url': 'https://rss.hankyung.com/economy.xml'},
]
SCM_FEEDS = [
    {'name': 'Supply Chain Dive',         'url': 'https://www.supplychaindive.com/feeds/news/'},
    {'name': 'FreightWaves',              'url': 'https://www.freightwaves.com/feed'},
    {'name': 'Modern Materials Handling', 'url': 'https://www.mmh.com/rss/articles'},
    {'name': 'Logistics Management',      'url': 'https://www.logisticsmgmt.com/rss/news.xml'},
    {'name': 'DC Velocity',              'url': 'https://www.dcvelocity.com/rss/news/'},
    {'name': '물류신문',                   'url': 'https://www.klnews.co.kr/rss/allArticle.xml'},
    {'name': '코리아쉬핑가제트',            'url': 'https://www.ksg.co.kr/rss/allArticle.xml'},
    {'name': '전자신문',                   'url': 'https://www.etnews.com/rss/article.xml'},
    {'name': '디지털타임스',               'url': 'https://www.dt.co.kr/rss/'},
    {'name': '매일경제',                   'url': 'https://www.mk.co.kr/rss/30200030/'},
    {'name': '한국경제',                   'url': 'https://rss.hankyung.com/economy.xml'},
]

HERO_KW = ['AI', '인공지능', 'SCM', '물류', '공급망', '자동화', '에이전트',
           '로봇', 'robot', 'agent', '이커머스', 'FBA', '수요예측', '재고',
           'supply chain', 'logistics', 'warehouse', 'automation', 'machine learning']

# 관련성 판단 키워드 — 이 중 하나도 없으면 뉴스레터에서 제외
_RELEVANCE_KW = [
    'ai', '인공지능', '머신러닝', '딥러닝', '자동화', '로봇', '에이전트', 'llm', 'gpt',
    'scm', '물류', '공급망', '배송', '유통', '창고', '재고', '운송', '해운', '항만',
    'fba', '이커머스', '전자상거래', '셀러', '아마존', '쿠팡', '관세', '무역', '수출', '수입',
    'supply chain', 'logistics', 'warehouse', 'automation', 'machine learning',
    '데이터', '클라우드', '반도체', '디지털', '플랫폼', '소프트웨어', '스타트업',
    '운임', '항공화물', '컨테이너', '물류비', '수요예측', '재고최적화',
]

def is_relevant(a):
    text = (a['title'] + ' ' + a['description']).lower()
    cfg_kw = [k.lower() for k in config.get('keywords', [])]
    return any(kw in text for kw in cfg_kw + _RELEVANCE_KW)

# 헤드라인 중요도 점수 — 히어로 선정 기준
_HEADLINE_POS = ['발표', '출시', '공개', '도입', '협약', '투자', '인수', '합병', '상장',
                 '규제', '정책', '법안', '급등', '급락', '폭등', '폭락', '사상 최',
                 '세계 최초', '국내 최초', '글로벌', '대규모', '파격', '혁신 발표']
_HEADLINE_NEG = ['학술대회', '세미나', '포럼', '심포지엄', '컨퍼런스', '워크숍',
                 '강연', '전시회', '박람회', '간담회', '시상식',
                 '취임', '임명', '부임', '퇴임', '수상']
_HIGH_AUTH_SOURCES = {'매일경제', '한국경제', '전자신문', '디지털타임스',
                      'TechCrunch AI', 'The Verge AI', 'VentureBeat AI'}

_KO_STOPWORDS = {'의', '에', '를', '이', '가', '은', '는', '과', '와', '로', '으로',
                 '에서', '까지', '부터', '에게', '한다', '있다', '됐다', '했다', '하는',
                 '위해', '통해', '대해', '관련', '따라', '대한', '위한', '등', '및',
                 '또한', '그리고', '하지만', '그러나', '이후', '지난', '오는', '다음'}

def _cross_source_score(a, all_arts):
    """다른 언론사가 같은 이슈를 얼마나 보도하는지 — 중복 보도일수록 중요한 뉴스."""
    words = {w for w in a['title'].split() if len(w) >= 2 and w not in _KO_STOPWORDS}
    if len(words) < 2:
        return 0
    seen = set()
    for other in all_arts:
        if other['link'] == a['link'] or other['source'] == a['source']:
            continue
        if other['source'] in seen:
            continue
        other_words = set(other['title'].split())
        if len(words & other_words) >= 2:
            seen.add(other['source'])
    return len(seen)

def _headline_score(a, all_arts=None):
    title = a['title'].lower()
    text  = (a['title'] + ' ' + a['description']).lower()
    score = _kw_score(a) * 2
    score += sum(1 for kw in _HEADLINE_POS if kw in text)
    score -= sum(3 for kw in _HEADLINE_NEG if kw in title)
    score -= sum(1 for kw in _HEADLINE_NEG if kw in text)
    if a['source'] in _HIGH_AUTH_SOURCES:
        score += 2
    # 피드 상단 노출 보너스 (0~4점)
    rank = a.get('feed_rank', 99)
    if rank < 5:
        score += (5 - rank) * 0.8
    # 크로스소스 보도 보너스 — 가장 강력한 중요도 신호 (언론사당 +3점)
    if all_arts:
        score += _cross_source_score(a, all_arts) * 3
    return score


# ── 일간 메인 ──────────────────────────────────────────────
def main():
    since    = datetime.now(timezone.utc) - timedelta(days=7)
    disabled = set(config.get('disabledFeeds', []))
    active_ai  = [f for f in AI_FEEDS  if f['name'] not in disabled]
    active_scm = [f for f in SCM_FEEDS if f['name'] not in disabled]

    print('Fetching feeds...')
    ai_raw  = [a for a in collect_articles(active_ai,  since) if is_relevant(a)]
    scm_raw = [a for a in collect_articles(active_scm, since) if is_relevant(a)]
    print(f'AI: {len(ai_raw)}건, SCM: {len(scm_raw)}건')
    if not ai_raw and not scm_raw:
        print('새 기사 없음.'); return

    ai_names = {f['name'] for f in AI_FEEDS}

    # ── 히어로: 오늘자(24h) 기사 중 가장 핫한 것 (없으면 7일 내 최신)
    today_since = datetime.now(timezone.utc) - timedelta(hours=24)
    all_pool    = ai_raw + scm_raw
    today_pool  = [a for a in all_pool if a['date'] >= today_since]
    hero_pool   = today_pool if today_pool else all_pool
    # 히어로는 반드시 국문 기사, 헤드라인 점수 기준으로 선정
    hero_pool_ko = [a for a in hero_pool if a['source'] not in EN_SOURCES]
    hero_base    = hero_pool_ko if hero_pool_ko else hero_pool
    hero_base.sort(key=lambda x: (_headline_score(x, all_pool), x['date'].timestamp()), reverse=True)
    hero_candidates = [a for a in hero_base if any(kw.lower() in (a['title']+' '+a['description']).lower() for kw in HERO_KW)]
    hero       = hero_candidates[0] if hero_candidates else hero_base[0]
    hero_color = AI_COLOR if hero['source'] in ai_names else SCM_COLOR

    # ── AI/SCM 카드: 히어로 제외, 각각 설정 숫자 그대로
    per_feed  = config.get('topPerFeed', 2)
    ai_top    = pick_top([a for a in ai_raw  if a['link'] != hero['link']], per_feed, config.get('maxAiCards',  4), max_en=1)
    scm_top   = pick_top([a for a in scm_raw if a['link'] != hero['link']], per_feed, config.get('maxScmCards', 4), max_en=1)
    q_hits    = pick_quick_hits(ai_raw + scm_raw, [hero] + ai_top + scm_top, config.get('maxQuickHits', 12))

    print('이미지 수집 중...')
    hero['og_image'] = fetch_og_image(hero['link'])
    for a in ai_top + scm_top:
        a['og_image'] = fetch_og_image(a['link'])

    print('인사이트 생성 중...')
    summarize_batch([hero], is_ai=(hero['source'] in ai_names))
    summarize_batch(ai_top,  is_ai=True)
    summarize_batch(scm_top, is_ai=False)

    print('에디터 노트 생성 중...')
    editor_note = gen_editor_note(ai_top, scm_top, q_hits)

    print('헤드라인 하이라이트 중...')
    gemini_highlight_qhits(q_hits, ai_names)

    html = build_html(editor_note, hero, hero_color, ai_top, scm_top, q_hits, len(ai_raw), len(scm_raw))
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
            for rank, e in enumerate(parsed.entries):   # rank: 피드 내 노출 순위
                pub = e.get('published_parsed') or e.get('updated_parsed')
                if not pub: continue
                date = datetime(*pub[:6], tzinfo=timezone.utc)
                if date < since: continue
                title = clean(e.get('title',''))
                if not title: continue
                desc = (e.get('summary') or (e.get('content') or [{}])[0].get('value',''))
                arts.append({'title':title, 'link':e.get('link',''), 'date':date,
                             'description':clean(desc)[:600], 'source':feed['name'],
                             'feed_rank': rank})
        except Exception as ex:
            print(f'  Skip {feed["name"]}: {ex}')
    return arts

def clean(s):
    s = re.sub(r'<[^>]+>',' ',str(s or ''))
    for o,n in [('&nbsp;',' '),('&amp;','&'),('&lt;','<'),('&gt;','>'),('&quot;','"'),('&#39;',"'")]:
        s = s.replace(o,n)
    return re.sub(r'\s+',' ',s).strip()

EN_SOURCES = {'TechCrunch AI', 'The Verge AI', 'VentureBeat AI', 'The Decoder',
              'Supply Chain Dive', 'FreightWaves', 'Modern Materials Handling',
              'Logistics Management', 'DC Velocity'}

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

    # 영문 max_en개 제한, 나머지는 한국어로 채우기
    # ko_reserve는 전체 arts에서 뽑아야 per_feed 제한에 걸려도 빈 자리를 채울 수 있음
    ko_reserve = sorted([a for a in arts if a['source'] not in EN_SOURCES],
                        key=lambda x: (_kw_score(x), x['date'].timestamp()), reverse=True)
    result, en_count = [], 0
    for a in picked:
        if len(result) >= max_total:
            break
        if a['source'] in EN_SOURCES:
            if en_count < max_en:
                result.append(a)
                en_count += 1
        else:
            result.append(a)
    # 빈 자리를 전체 풀의 한국어 기사로 채우기
    used = {a['link'] for a in result}
    for a in ko_reserve:
        if len(result) >= max_total:
            break
        if a['link'] not in used:
            result.append(a)
            used.add(a['link'])
    # 한국어 먼저, 영문 기사는 맨 아래
    ko = sorted([a for a in result if a['source'] not in EN_SOURCES],
                key=lambda x: (_kw_score(x), x['date'].timestamp()), reverse=True)
    en = [a for a in result if a['source'] in EN_SOURCES]
    return (ko + en)[:max_total]

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
    body = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'thinkingConfig': {'thinkingBudget': 0}},  # thinking 비활성화 → 속도 개선
    }
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
  ★ 각 기사에서 가장 중요한 구절 1~2개를 아래 HTML 태그로 감쌀 것.
  ★ 단순 키워드가 아닌, 기사의 핵심 팩트·수치·변화를 담은 구절을 골라야 함.
- insight: FBA 이커머스·SCM 물류 실무 활용 인사이트 1~2문장. 이모지 1개. 해당 없으면 "".

HTML 강조 태그 (반드시 이 두 가지만 사용):
- 핵심 구절: <strong style="color:{color}">구절</strong>
- 핵심 키워드/수치: <span style="background:{bg};padding:1px 6px;border-radius:3px;font-weight:600;color:{color}">텍스트</span>

{items}

JSON 배열로만 응답 (다른 텍스트 없이):
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

HTML 강조 (키워드 단순 매칭 금지 — 문장 안에서 실제로 핵심적인 어구·수치·변화를 담은 구절만 강조):
AI 문단 → <strong style="color:#C85A35">핵심 어구</strong> 또는 <span style="background:#FFF3E0;padding:1px 6px;border-radius:3px;font-weight:600;color:#C85A35;">핵심 어구</span>
SCM 문단 → <strong style="color:#175F7A">핵심 어구</strong> 또는 <span style="background:#E3F2F8;padding:1px 6px;border-radius:3px;font-weight:600;color:#175F7A;">핵심 어구</span>
각 문단에서 2~3개 어구만 강조. 위 태그만 사용. 문단 구분은 <br><br>.

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

def gemini_highlight_qhits(q_hits, ai_names):
    """Quick Hits 제목들을 Gemini로 핵심 어구 하이라이트 (1 API call)."""
    for a in q_hits:
        a['title_hl'] = esc(a['title'])  # 기본값
    if not q_hits or not GEMINI_ENABLED:
        return

    items = '\n'.join([
        f'{i+1}. [{"AI" if a["source"] in ai_names else "SCM"}] {a["title"]}'
        for i, a in enumerate(q_hits)
    ])
    prompt = f"""다음 뉴스 제목들 각각에서, 제목 안의 가장 핵심적인 어구 1개에만 HTML 강조 태그를 추가해줘.

규칙:
- 제목 원문을 그대로 유지하고 강조할 어구만 태그로 감쌀 것
- 키워드 단순 매칭 금지 (AI, 물류 등 일반 단어 단독 강조 금지)
- 회사명+행동, 수치, 핵심 변화를 담은 구절 우선 선택
- 정확히 1개 어구만 강조

AI 기사: <strong style="color:{AI_COLOR}">어구</strong>
SCM 기사: <strong style="color:{SCM_COLOR}">어구</strong>

{items}

JSON 배열로만 응답 (번호 순서 유지, 강조 태그 포함된 제목 전체):
["제목1", "제목2", ...]"""

    try:
        raw = call_gemini(prompt)
        if not raw:
            raise ValueError('빈 응답')
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        results = json.loads(m.group() if m else raw)
        for i, a in enumerate(q_hits):
            if i < len(results) and results[i]:
                a['title_hl'] = results[i]
        print('  Quick Hits 하이라이트 완료')
    except Exception as e:
        print(f'  Quick Hits 하이라이트 실패: {e}')


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

_MAJOR_COMPANIES = [
    '엔비디아', '구글', '아마존', '메타', '애플', '마이크로소프트', '테슬라',
    '오픈AI', 'OpenAI', '알파벳', '삼성전자', 'SK하이닉스', 'LG전자',
    '현대차', '기아', '롯데', 'CJ', 'GS', '쿠팡', '네이버', '카카오',
    'DHL', 'FedEx', 'UPS', 'Maersk', '머스크', 'CEVA', 'DB쉥커',
]

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
    """본문 강조: 핵심 내용 기반 (키워드 단순 매칭 제외)"""
    bg = AI_BG if color == AI_COLOR else SCM_BG
    result = esc(text)

    # 1. 따옴표 속 핵심 어구 (작은따옴표 ' 및 큰따옴표 " 모두)
    result = re.sub(
        r'&#39;([^&#]{4,25})&#39;',
        lambda m: f'<span style="background:{bg};padding:1px 5px;border-radius:3px;font-weight:700;color:{color};">&#39;{m.group(1)}&#39;</span>',
        result
    )
    result = re.sub(
        r'&quot;([^&]{4,25})&quot;',
        lambda m: f'<span style="background:{bg};padding:1px 5px;border-radius:3px;font-weight:700;color:{color};">&quot;{m.group(1)}&quot;</span>',
        result
    )

    # 2. 수치+단위 → 볼드
    result = re.sub(
        r'(\d[\d,]*(?:\.\d+)?(?:억|조|만|천)?(?:원|달러|위안|유로|%|퍼센트|배|건|명|개))',
        f'<strong style="color:{color};">\\1</strong>', result)

    # 3. 주요 기업명 (리스트 기반)
    for co in sorted(_MAJOR_COMPANIES, key=len, reverse=True):
        result = result.replace(esc(co), f'<strong style="color:{color};">{esc(co)}</strong>', 1)

    # 4. 기업명 접미사 패턴 (XX전자, XX그룹 등)
    result = re.sub(
        r'([가-힣A-Z][가-힣A-Za-z]{1,8}(?:전자|자동차|그룹|물산|네트워크|솔루션|시스템|테크|로보틱스|모빌리티|코리아|글로벌))',
        f'<strong style="color:{color};">\\1</strong>', result)

    # 5. 인물+직함 패턴 — 괄호 내용 무시하고 이름+직함만 매칭
    result = re.sub(
        r'([가-힣A-Za-z·]{1,6}(?:\s[가-힣A-Za-z·]{1,6})?)\s*(?:\([^)]{0,30}\)\s*)?(?:\([^)]{0,30}\)\s*)?\s*(CEO|CTO|CFO|COO|대표|회장|사장|부사장|의장)',
        lambda m: f'<strong style="color:{color};">{m.group(1)} {m.group(2)}</strong>',
        result)

    # 6. 임팩트 표현 → 볼드
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
        img_html = (
            f'<a href="{link}" style="display:block;text-decoration:none;">'
            f'<img src="{img}" alt="" width="100%" style="display:block;width:100%;height:320px;object-fit:cover;border:0;"></a>'
        )
    else:
        img_html = (
            f'<table width="100%" cellpadding="0" cellspacing="0" style="background:{color};opacity:0.15;height:200px;">'
            f'<tr><td></td></tr></table>'
        )

    insight_html = ''
    if insight:
        insight_html = (
            f'<div style="margin-top:14px;padding:12px 16px;background:{bg};border-left:3px solid {color};border-radius:0 6px 6px 0;">'
            f'<div style="font-size:11px;font-weight:700;color:{color};letter-spacing:1px;margin-bottom:5px;">💡 INSIGHT</div>'
            f'<div style="font-size:14px;color:#444;line-height:1.8;">{insight}</div>'
            f'</div>'
        )

    return (
        f'<div style="margin-bottom:0;overflow:hidden;">'
        f'{img_html}'
        f'<table width="100%" cellpadding="0" cellspacing="0" style="background:{color};">'
        f'<tr><td style="padding:22px 40px 26px;">'
        f'<div style="font-size:10px;letter-spacing:3px;color:rgba(255,255,255,0.55);font-weight:700;margin-bottom:10px;">🌟 오늘의 하이라이트</div>'
        f'<a href="{link}" style="text-decoration:none;">'
        f'<div style="font-size:24px;font-weight:800;color:#fff;line-height:1.3;">{hl}</div>'
        f'</a>'
        f'<div style="font-size:12px;color:rgba(255,255,255,0.45);margin-top:8px;">{src}</div>'
        f'</td></tr></table>'
        f'<div style="padding:26px 40px 32px;background:#fff;">'
        f'<div style="font-size:15px;color:#333;line-height:1.9;">{summary}</div>'
        f'{insight_html}'
        f'<div style="margin-top:18px;">'
        f'<a href="{link}" style="display:inline-block;padding:9px 22px;background:{color};color:#fff;'
        f'font-size:13px;font-weight:700;text-decoration:none;border-radius:4px;">기사 읽기 →</a>'
        f'</div>'
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
                 f'<img src="{img}" alt="" width="100%" style="display:block;width:100%;height:220px;object-fit:cover;border:0;border-radius:12px 12px 0 0;"></a>')
    else:
        thumb = (f'<table width="100%" cellpadding="0" cellspacing="0" '
                 f'style="background:{placeholder_bg};height:100px;border-radius:12px 12px 0 0;">'
                 f'<tr><td align="center" valign="middle">'
                 f'<div style="width:40px;height:3px;background:{color};opacity:0.25;border-radius:2px;margin:0 auto;"></div>'
                 f'</td></tr></table>')

    insight_html = ''
    if insight:
        insight_html = (
            f'<div style="margin-top:16px;padding:14px 16px;background:{bg};border-left:3px solid {color};border-radius:0 8px 8px 0;">'
            f'<div style="font-size:11px;font-weight:700;color:{color};letter-spacing:1.5px;margin-bottom:6px;">💡 INSIGHT</div>'
            f'<div style="font-size:14px;color:#444;line-height:1.85;">{insight}</div>'
            f'</div>'
        )

    return (
        f'<div style="margin-bottom:28px;border-radius:12px;overflow:hidden;border:1px solid #ebebeb;background:#fff;">'
        f'<a href="{link}" style="display:block;text-decoration:none;">{thumb}</a>'
        f'<div style="padding:22px 24px 24px;">'
        f'<div style="margin-bottom:10px;">'
        f'<span style="font-size:11px;font-weight:700;color:{color};letter-spacing:1px;">{src}</span>'
        f'</div>'
        f'<a href="{link}" style="text-decoration:none;">'
        f'<div style="font-size:18px;font-weight:700;color:#111;line-height:1.5;margin-bottom:12px;letter-spacing:-0.3px;">{hl}</div>'
        f'</a>'
        f'<div style="font-size:14px;color:#555;line-height:1.9;">{summary}</div>'
        f'{insight_html}'
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

def build_html(editor_note, hero, hero_color, ai_top, scm_top, q_hits, ai_total=0, scm_total=0):
    ai_names = {f['name'] for f in AI_FEEDS}

    W = ('max-width:780px;margin:0 auto;background:#fff;'
         'font-family:"Pretendard","Apple SD Gothic Neo","Malgun Gothic",sans-serif;'
         'color:#111;line-height:1.7;')

    H = (f'<body style="margin:0;padding:0;background:#e8e8e8;">'
         f'<style>@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css");</style>'
         f'<div style="{W}">')

    # ── 다크 헤더
    cfg_kw = config.get('keywords', [])
    kw_badge_html = ''
    if cfg_kw:
        kw_badge_html = '<div style="margin-top:14px;">' + ''.join(
            f'<span style="display:inline-block;margin:3px 4px 3px 0;padding:3px 12px;'
            f'background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.2);'
            f'border-radius:20px;font-size:11px;font-weight:600;color:rgba(255,255,255,0.7);">'
            f'{esc(kw)}</span>'
            for kw in cfg_kw
        ) + '</div>'

    _day_seed = int(datetime.now().strftime('%Y%m%d'))
    quote = MORNING_QUOTES[_day_seed % len(MORNING_QUOTES)]
    H += (f'<table width="100%" cellpadding="0" cellspacing="0" style="background:#111;">'
          f'<tr><td style="padding:36px 40px 30px;">'
          f'<div style="font-size:10px;letter-spacing:4px;color:#555;font-weight:600;margin-bottom:16px;">AI × SCM DAILY</div>'
          f'<div style="font-size:46px;font-weight:800;color:#fff;line-height:1.05;letter-spacing:-1.5px;">☕ 굿모닝!</div>'
          f'<div style="font-size:16px;color:#888;margin-top:14px;font-style:italic;line-height:1.7;">{quote}</div>'
          f'<div style="font-size:13px;color:#444;margin-top:10px;letter-spacing:0.3px;">{kr_date(datetime.now())}</div>'
          f'{kw_badge_html}'
          f'</td></tr></table>')

    # ── 에디터 노트 (크림 배경)
    if editor_note:
        H += (f'<div style="padding:30px 40px;background:#FFF8F3;border-bottom:1px solid #f0e8e0;">'
              f'<div style="font-size:10px;letter-spacing:3px;color:{AI_COLOR};font-weight:700;margin-bottom:14px;">📝 오늘의 한 마디</div>'
              f'<div style="font-size:15px;color:#333;line-height:2.1;">{editor_note}</div>'
              f'</div>')
    else:
        H += gen_briefing(ai_total, scm_total, ai_top + scm_top + q_hits)

    # ── 히어로 (풀블리드)
    H += render_hero(hero, hero_color)

    # ── AI 섹션
    H += (f'<div style="padding:36px 40px 8px;">'
          f'<div style="display:inline-block;font-size:11px;font-weight:800;color:{AI_COLOR};'
          f'letter-spacing:2px;border-bottom:2px solid {AI_COLOR};padding-bottom:6px;margin-bottom:24px;">🤖 AI 이슈</div>'
          f'</div>')
    H += f'<div style="padding:0 40px 12px;">{"".join(render_card(a, AI_COLOR, "#f5f0ec") for a in ai_top)}</div>'

    # ── SCM 섹션
    H += (f'<div style="padding:20px 40px 8px;border-top:1px solid #f0f0f0;">'
          f'<div style="display:inline-block;font-size:11px;font-weight:800;color:{SCM_COLOR};'
          f'letter-spacing:2px;border-bottom:2px solid {SCM_COLOR};padding-bottom:6px;margin-bottom:24px;">📦 SCM 이슈</div>'
          f'</div>')
    H += f'<div style="padding:0 40px 12px;">{"".join(render_card(a, SCM_COLOR, "#edf5f8") for a in scm_top)}</div>'

    # ── Quick Hits
    if q_hits:
        rows = ''
        for i, a in enumerate(q_hits):
            is_ai = a['source'] in ai_names
            tc  = AI_COLOR if is_ai else SCM_COLOR
            tl  = 'AI' if is_ai else 'SCM'
            bd  = 'border-bottom:1px solid #efefef;' if i < len(q_hits)-1 else ''
            ttl = a.get('title_hl') or esc(a['title'])
            rows += (
                f'<table width="100%" cellpadding="0" cellspacing="0" style="{bd}">'
                f'<tr>'
                f'<td width="44" style="padding:13px 10px 13px 0;vertical-align:middle;">'
                f'<span style="display:inline-block;width:36px;text-align:center;font-size:10px;'
                f'font-weight:700;color:#fff;background:{tc};padding:4px 0;border-radius:6px;">{tl}</span>'
                f'</td>'
                f'<td style="padding:13px 0;vertical-align:middle;">'
                f'<a href="{a["link"]}" style="font-size:14px;color:#222;text-decoration:none;line-height:1.6;">{ttl}</a>'
                f'</td>'
                f'</tr></table>'
            )
        H += (f'<div style="padding:28px 40px 32px;background:#f7f7f7;border-top:1px solid #ebebeb;">'
              f'<div style="font-size:10px;letter-spacing:3px;color:#aaa;font-weight:700;margin-bottom:18px;">⚡ 빠르게 보는 헤드라인</div>'
              f'{rows}</div>')

    H += (f'<table width="100%" cellpadding="0" cellspacing="0" style="background:#111;">'
          f'<tr><td style="padding:24px 40px;text-align:center;">'
          f'<div style="font-size:12px;color:#555;letter-spacing:0.5px;">📬 AI × SCM Daily &nbsp;·&nbsp; 좋은 하루 보내세요 ✨</div>'
          f'</td></tr></table>')
    H += '</div></body>'
    head = '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>'
    return f'<!DOCTYPE html><html>{head}{H}</html>'


# ── 주간 HTML ──────────────────────────────────────────────
def build_weekly_html(summary, ai_top, scm_top, top_kw, ai_cnt, scm_cnt):
    ai_names = {f['name'] for f in AI_FEEDS}
    now = datetime.now()
    W = ('max-width:900px;margin:0 auto;background:#fff;'
         'font-family:"Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif;'
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
    head = '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>'
    return f'<!DOCTYPE html><html>{head}{H}</html>'


# ── 실행 ───────────────────────────────────────────────────
if __name__ == '__main__':
    if '--weekly' in sys.argv:
        send_weekly()
    else:
        main()
