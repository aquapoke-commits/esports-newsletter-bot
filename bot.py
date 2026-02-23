import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import feedparser
import html
import os
import re 
from datetime import datetime, timedelta, timezone
import asyncio

# =====================================================================
# [보안 설정]
# =====================================================================
if 'DISCORD_TOKEN' in os.environ:
    DISCORD_TOKEN = os.environ['DISCORD_TOKEN']
else:
    print("⚠️ 에러: DISCORD_TOKEN 환경 변수가 없습니다.")
    exit()

# [설정] 채널 ID 리스트
TARGET_CHANNELS = [
    1447898781365567580, # GGX Proto
    1450833963278012558, # Hanta.GG
    # 987654321098765432, 
]

# =====================================================================
# [키워드 설정]
# =====================================================================

# 👑 1. 프리미엄 키워드 (1개만 있어도 합격)
PREMIUM_KEYWORDS = [
    "이스포츠", "e스포츠" #이스포츠 정의

]

# 🧢 2. 일반 키워드 (2개 이상 있어야 합격)
NORMAL_KEYWORDS = [
    "Esports", #전문
    "LoL", "League of Legends", "Valorant", "이터널 리턴", "PUBG", "FC Online", "스타크래프트", "나혼렙", "마블 라이벌즈", "리프트바운드", "섀도우버스" #종목명
    "라이엇", "넷마블", "크래프톤", "블리자드", "넥슨", #종목사
    "World Championship", "롤드컵", "MSI", "퍼스트 스탠드", "VCT", "PGS", "PGC", "EWC", "ENC", #국제 대회명
    "LCK", "LPL", "LEC", "LCS", "CBLOL", "LCP", #지역 리그명
    "T1", "젠지", "HLE", "한화생명", "DK", "디플러스", "KT", "DRX", "FOX", "NS", "BRO", #이스포츠 팀
    "학회", "IESF", "이코노미" #특정 키워드
    
]

SEARCH_KEYWORDS = list(set(PREMIUM_KEYWORDS + NORMAL_KEYWORDS))

# =====================================================================

# [설정] 차단할 단어 (아예 수집 제외)
EXCLUDE_LIST = ["theqoo", "더쿠", "instiz", "인스티즈", "fmkorea", "펨코", "dcinside", "디시", "바카라", "토토", "카지노", "슬롯", "MSN", "인벤", "보통주", "패치노트", "사모대출", "investing","vietnam", "ZUM", "포토"]

# [설정] ★중복 검사에서만 무시할 단어★ (이 단어들은 겹쳐도 중복으로 안 침)
IGNORE_DUPLICATE_WORDS = ["Esports", "이스포츠", "e스포츠", "2025", "2026", "경기", "리그", "vs", "오늘", "내일", "Insider" ]

# [설정] 뉴스 유효 시간
MAX_HOURS = 24

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------------------------------
# [함수 0] 과거 기록 불러오기 (최근 30시간 제한)
# ---------------------------------------------------
async def get_past_titles(channel_id):
    print("⏳ [검증] 디스코드 채널에 '실제로 업로드된' 최근 뉴스를 확인합니다...")
    past_titles = []
    channel = bot.get_channel(channel_id)
    
    if not channel:
        print("⚠️ 기록을 확인할 채널을 찾지 못했습니다.")
        return []

    # 최근 30시간 이내의 메시지만 확인
    check_limit_time = datetime.now(timezone.utc) - timedelta(hours=30)
    
    try:
        async for message in channel.history(limit=20): # 넉넉하게 20개 확인
            if message.author != bot.user:
                continue
            if message.created_at < check_limit_time:
                break

            for embed in message.embeds:
                if embed.description:
                    matches = re.findall(r"\[(.*?)\]\(http", embed.description)
                    past_titles.extend(matches)
                        
        print(f"🧠 기억 완료: 최근 30시간 내 업로드된 뉴스 {len(past_titles)}개를 확인했습니다.")
        return past_titles
    except Exception as e:
        print(f"⚠️ 과거 기록 조회 실패: {e}")
        return []

# ---------------------------------------------------
# [함수 0.5] 키워드 레벨 판독기
# ---------------------------------------------------
def check_keyword_level(title):
    for p_key in PREMIUM_KEYWORDS:
        if p_key.lower() in title.lower():
            return True, f"👑프리미엄({p_key})"

    count = 0
    matched = []
    for n_key in NORMAL_KEYWORDS:
        if n_key.lower() in title.lower():
            count += 1
            matched.append(n_key)
            
    if count >= 2:
        return True, f"🧢일반합격({', '.join(matched)})"

    return False, f"조건미달(일반 {count}개)"

# ---------------------------------------------------
# [함수 0.6] ★중복 검사용 문장 청소기★ (추가됨)
# ---------------------------------------------------
def clean_title_for_check(title):
    # 비교를 위해 잠시 특정 단어들을 지운 제목을 만듭니다.
    temp_title = title
    for word in IGNORE_DUPLICATE_WORDS:
        # 대소문자 구분 없이 제거하기 위해 replace 사용 (단순화)
        temp_title = temp_title.replace(word, "")
    return temp_title.strip()


# ---------------------------------------------------
# [크롤링 함수 1] 다음(Daum) 뉴스 (네이버 대체)
# ---------------------------------------------------
def get_daum_news(keyword):
    news_list = []
    clean_keyword = keyword.replace(" ", "+")
    
    # [설정] sort=recency: 최신순 정렬
    url = f"https://search.daum.net/search?w=news&q={clean_keyword}&sort=recency"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 다음 뉴스 리스트 선택자
        items = soup.select('ul.c-list-basic > li')
        
        for item in items:
            # 제목 및 링크 추출
            title_tag = item.select_one('.item-title a')
            if not title_tag: continue
            
            title = title_tag.text.strip()
            link = title_tag['href']
            
            # [Daum 시간 정밀 검사]
            # gem-subinfo 안에 "55분전", "1시간전" 등의 정보가 있음
            date_info = item.select_one('.gem-subinfo')
            is_recent = False
            time_log = "알수없음"
            
            if date_info:
                text = date_info.text.strip()
                # "분전", "시간전"이 포함되어야 진짜 최신 뉴스
                if "분전" in text or "시간전" in text:
                    time_log = text
                    # "1일전" 등은 탈락 (다음은 띄어쓰기 없이 '1시간전'으로 표기하기도 함)
                    if "일전" in text or "일 전" in text:
                        is_recent = False
                    else:
                        is_recent = True
            
            if is_recent:
                news_list.append({
                    "title": title, 
                    "link": link, 
                    "source": "Daum", 
                    "origin": "다음", # 출처 표기 변경
                    "time_str": time_log
                })

    except Exception as e:
        print(f"❌ 다음(Daum) 오류({keyword}): {e}")
        pass
        
    return news_list
    

# ---------------------------------------------------
# [크롤링 함수 2] 구글 뉴스
# ---------------------------------------------------
def get_google_news(keyword):
    news_list = []
    clean_keyword = keyword.replace(" ", "+")
    url = f"https://news.google.com/rss/search?q={clean_keyword}+when:1d&hl=ko&gl=KR&ceid=KR:ko&num=100"
    
    PAST_YEARS = ["2020", "2021", "2022", "2023", "2024"] 

    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if not hasattr(entry, 'published_parsed') or entry.published_parsed is None:
                continue
            
            try:
                pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                current_date = datetime.now(timezone.utc)
                
                diff_seconds = (current_date - pub_date).total_seconds()
                diff_hours = diff_seconds / 3600
                if diff_hours < 0: diff_hours = 0
                
                pub_date_kst = pub_date + timedelta(hours=9)
                time_str_kst = pub_date_kst.strftime("%Y-%m-%d %H:%M:%S")

                source_name = "Google"
                if hasattr(entry, 'source') and hasattr(entry.source, 'title'):
                    source_name = entry.source.title

                if diff_hours > MAX_HOURS:
                    continue
                
                is_old_title = False
                for year in PAST_YEARS:
                    if year in entry.title:
                         is_old_title = True
                         print(f"📅 [구글|연도탈락] {entry.title} (이유: 과거 연도 '{year}' 포함)")
                         break
                if is_old_title: continue

                news_list.append({
                    "title": entry.title,
                    "link": entry.link,
                    "source": source_name,
                    "origin": "구글",
                    "time_str": time_str_kst
                })
                
            except:
                continue
                
    except Exception as e:
        print(f"❌ 구글 오류({keyword}): {e}")
        pass
        
    return news_list

# ---------------------------------------------------
# [통합 함수] 뉴스 수집 및 선별
# ---------------------------------------------------
def collect_news(past_titles):
    print(f"\n📰 뉴스 수집 및 정밀 심사 시작 (제한: {MAX_HOURS}시간)")
    all_news = []
    seen_links = set()
    collected_titles = [] 
    
    MAX_TOTAL = 20        
    MAX_PER_KEYWORD = 8
    DUPLICATE_THRESHOLD = 9 
    
    for keyword in SEARCH_KEYWORDS:
        if len(all_news) >= MAX_TOTAL: 
            print("🛑 [전체제한] 총 20개를 모두 채워 수집을 종료합니다.")
            break
            
        n_res = get_daum_news(keyword)
        g_res = get_google_news(keyword)
        
        current_keyword_count = 0
        
        for news in n_res + g_res:
            if len(all_news) >= MAX_TOTAL: break
            if current_keyword_count >= MAX_PER_KEYWORD: break
            
            # [1] 차단 사이트 필터
            is_excluded = False
            check_target = (news['link'] + news['title'] + news.get('source', '')).lower()
            
            for ban_word in EXCLUDE_LIST:
                if ban_word.lower() in check_target:
                    is_excluded = True
                    print(f"🚫 [사이트차단][{news['origin']}] {news['title']} (이유: {ban_word})") 
                    break
            
            if is_excluded: continue 
            
            # [1.5] 키워드 레벨 필터
            is_qualified, qualify_reason = check_keyword_level(news['title'])
            if not is_qualified:
                continue

            # [2] 링크 중복 필터
            if news['link'] in seen_links: continue

            clean_title = html.unescape(news['title']).replace("[", "").replace("]", "").strip()
            
            # [★중요★] 중복 검사를 위해 '무시할 단어'를 지운 제목을 만듭니다.
            check_title = clean_title_for_check(clean_title)
            
            # [3] 제목 내용 중복 필터
            is_similar = False
            match_cause = "" 
            for existing_title in collected_titles:
                # 비교 대상도 '청소된 제목'으로 비교합니다.
                check_existing = clean_title_for_check(existing_title)
                
                if len(check_title) < DUPLICATE_THRESHOLD: break
                
                # 청소된 제목끼리 비교
                for i in range(len(check_title) - DUPLICATE_THRESHOLD + 1):
                    sub_string = check_title[i : i + DUPLICATE_THRESHOLD]
                    if sub_string in check_existing:
                        is_similar = True
                        match_cause = sub_string 
                        break 
                if is_similar: break
            
            if is_similar:
                print(f"🔗 [내용중복][{news['origin']}] {clean_title} (겹친단어: '{match_cause}')")
                continue
            
            # [4] 과거 기록 중복 필터
            is_past_duplicate = False
            past_match_cause = "" 
            matched_past_title = "" 
            
            for past_title in past_titles:
                # 과거 제목도 청소해서 비교
                check_past = clean_title_for_check(past_title)
                
                if len(check_title) < DUPLICATE_THRESHOLD or len(check_past) < DUPLICATE_THRESHOLD:
                    break
                
                for i in range(len(check_title) - DUPLICATE_THRESHOLD + 1):
                    sub_string = check_title[i : i + DUPLICATE_THRESHOLD]
                    if sub_string in check_past:
                        is_past_duplicate = True
                        past_match_cause = sub_string 
                        matched_past_title = past_title 
                        break
                if is_past_duplicate: break
                
            if is_past_duplicate:
                print(f"🧟 [어제뉴스중복] {clean_title} (겹친단어: '{past_match_cause}' / 대상: {matched_past_title})")
                continue

            # [5] 최종 합격
            print(f"✅ [{qualify_reason}][{news['origin']}] {clean_title}")
            
            all_news.append({"title": clean_title, "link": news['link']})
            seen_links.add(news['link'])
            collected_titles.append(clean_title)
            current_keyword_count += 1
                
    print(f"📊 최종 결과: {len(all_news)}개 뉴스 전송 준비 완료\n")
    return all_news

# ---------------------------------------------------
# [전송 로직]
# ---------------------------------------------------
async def send_newsletter(target_channel_id, news_data):
    channel = bot.get_channel(target_channel_id)
    if not channel:
        print(f"❌ 채널 없음: {target_channel_id}")
        return

    if not news_data:
        return

    today = datetime.now().strftime("%Y년 %m월 %d일")
    MAX_DESCRIPTION_LEN = 3500
    current_description = ""
    page_count = 1
    
    embed = discord.Embed(title=f"🎮 {today} 이스포츠 주요 소식", color=0x00ff00)

    for idx, news in enumerate(news_data):
        one_line = f"` {idx+1}. ` [{news['title']}]({news['link']})\n\n"
        
        if len(current_description) + len(one_line) > MAX_DESCRIPTION_LEN:
            embed.description = current_description
            embed.set_footer(text=f"HantaGG NewsBot • {page_count}페이지")
            await channel.send(embed=embed)
            page_count += 1
            current_description = ""
            embed = discord.Embed(color=0x00ff00)
            
        current_description += one_line

    if current_description:
        embed.description = current_description
        embed.set_footer(text=f"HantaGG NewsBot • 마지막 페이지 (총 {len(news_data)}건)")
        await channel.send(embed=embed)

    print(f"✅ 전송 완료: {target_channel_id}")

# ---------------------------------------------------
# [봇 실행]
# ---------------------------------------------------
@bot.event
async def on_ready():
    print(f"✅ 봇 로그인: {bot.user}")
    
    try:
        past_titles = []
        if TARGET_CHANNELS:
            past_titles = await get_past_titles(TARGET_CHANNELS[0])
            
        todays_news = collect_news(past_titles)
        
        for channel_id in TARGET_CHANNELS:
            await send_newsletter(channel_id, todays_news)
            
    except Exception as e:
        print(f"❌ 실행 중 치명적 오류 발생: {e}")
    
    print("👋 임무 완료. 종료합니다.")
    await bot.close()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)















