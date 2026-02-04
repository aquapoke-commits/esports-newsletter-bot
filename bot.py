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
# [★중요★] 키워드 레벨 설정
# =====================================================================

# 👑 1. 프리미엄 키워드 (제목에 1개만 있어도 무조건 선별)
# -> 핵심 선수, 인기 팀, 매우 중요한 대회 명칭 등
PREMIUM_KEYWORDS = [
    "Faker", "페이커", "T1", "티원", 
    "World Championship", "롤드컵", "MSI", 
    "Zeus", "Oner", "Gumayusi", "Keria", # 제오구케
    "Chovy", "ShowMaker", "Ruler", "Viper" # 슈퍼스타
]

# 🧢 2. 일반 키워드 (제목에 2개 이상 있어야 선별)
# -> 리그 이름, 일반 팀명, 흔한 이스포츠 용어
NORMAL_KEYWORDS = [
    "이스포츠", "e-sports", "LoL", "League of Legends",
    "LCK", "LPL", "LEC", "LCS", "VCT", "발로란트", "PUBG", "배틀그라운드", "이터널 리턴",
    "Gen.G", "젠지", "HLE", "한화생명", "DK", "디플러스", "KT", "DRX", "FOX", "NS", "BRO",
    "우승", "결승", "플레이오프", "개막", "인터뷰", "단독", "속보", "오피셜"
]

# (검색용) 봇은 이 두 리스트를 합쳐서 검색에 사용합니다.
SEARCH_KEYWORDS = list(set(PREMIUM_KEYWORDS + NORMAL_KEYWORDS))

# =====================================================================

# [설정] 차단할 단어
EXCLUDE_LIST = ["theqoo", "더쿠", "instiz", "인스티즈", "fmkorea", "펨코", "dcinside", "디시", "바카라", "토토", "카지노", "슬롯", "MSN", "인벤", "보통주", "패치노트", "사모대출", "investing","vietnam", "ZUM"]

# [설정] 뉴스 유효 시간
MAX_HOURS = 24

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------------------------------
# [함수 0] 과거 기록 불러오기
# ---------------------------------------------------
async def get_past_titles(channel_id):
    print("⏳ 어제 보낸 뉴스 기록을 확인하는 중...")
    past_titles = []
    channel = bot.get_channel(channel_id)
    
    if not channel:
        print("⚠️ 기록을 확인할 채널을 찾지 못했습니다.")
        return []

    try:
        async for message in channel.history(limit=10):
            if message.author == bot.user:
                for embed in message.embeds:
                    if embed.description:
                        matches = re.findall(r"\[(.*?)\]\(http", embed.description)
                        past_titles.extend(matches)
        print(f"🧠 기억 완료: 과거 뉴스 제목 {len(past_titles)}개를 로드했습니다.")
        return past_titles
    except Exception as e:
        print(f"⚠️ 과거 기록 조회 실패: {e}")
        return []

# ---------------------------------------------------
# [함수 0.5] 키워드 레벨 판독기 (핵심 알고리즘)
# ---------------------------------------------------
def check_keyword_level(title):
    # 1. 프리미엄 키워드 검사 (1개만 있어도 합격)
    for p_key in PREMIUM_KEYWORDS:
        # 대소문자 구분 없이 검사하려면 lower() 사용
        if p_key.lower() in title.lower():
            return True, f"👑프리미엄({p_key})"

    # 2. 일반 키워드 검사 (2개 이상 있어야 합격)
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
# [크롤링 함수 1] 네이버 뉴스
# ---------------------------------------------------
def get_naver_news(keyword):
    news_list = []
    clean_keyword = keyword.replace(" ", "+")
    url = f"https://search.naver.com/search.naver?where=news&query={clean_keyword}&sort=1"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        items = soup.select('ul.list_news > li.bx')
        
        for item in items:
            title_tag = item.select_one('a.news_tit')
            if not title_tag: continue
            
            title = title_tag.text
            link = title_tag['href']
            
            info_group = item.select('.info_group .info')
            is_recent = False
            time_log = "알수없음"
            
            for info in info_group:
                text = info.text
                if "분 전" in text or "시간 전" in text:
                    time_log = text 
                    if "일 전" in text:
                        is_recent = False
                        break
                    is_recent = True
                    break
            
            if is_recent:
                news_list.append({
                    "title": title, 
                    "link": link, 
                    "source": "Naver", 
                    "origin": "네이버",
                    "time_str": time_log,
                    "search_keyword": keyword
                })

    except Exception as e:
        print(f"❌ 네이버 오류({keyword}): {e}")
        pass
    return news_list

# ---------------------------------------------------
# [크롤링 함수 2] 구글 뉴스
# ---------------------------------------------------
def get_google_news(keyword):
    news_list = []
    clean_keyword = keyword.replace(" ", "+")
    url = f"https://news.google.com/rss/search?q={clean_keyword}+when:1d&hl=ko&gl=KR&ceid=KR:ko"
    
    PAST_YEARS = ["2020", "2021", "2022", "2023", "2024", "2025"] 

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
                    "time_str": time_str_kst,
                    "search_keyword": keyword
                })
                
            except:
                continue
                
    except Exception as e:
        print(f"❌ 구글 오류({keyword}): {e}")
        pass
        
    return news_list

# ---------------------------------------------------
# [통합 함수] 뉴스 수집 및 선별 (키워드 레벨 적용)
# ---------------------------------------------------
def collect_news(past_titles):
    print(f"\n📰 뉴스 수집 및 정밀 심사 시작 (제한: {MAX_HOURS}시간)")
    all_news = []
    seen_links = set()
    collected_titles = [] 
    
    MAX_TOTAL = 20        
    MAX_PER_KEYWORD = 4
    DUPLICATE_THRESHOLD = 9 
    
    # 검색은 모든 키워드(SEARCH_KEYWORDS)로 수행
    for keyword in SEARCH_KEYWORDS:
        if len(all_news) >= MAX_TOTAL: 
            print("🛑 [전체제한] 총 20개를 모두 채워 수집을 종료합니다.")
            break
            
        n_res = get_naver_news(keyword)
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
            
            # [1.5] ★ 키워드 레벨(Premium/Normal) 필터 ★
            # 여기서 제목을 검사해서 합격 여부를 결정합니다.
            is_qualified, qualify_reason = check_keyword_level(news['title'])
            
            if not is_qualified:
                # 로그가 너무 많으면 이 줄을 주석 처리하세요
                # print(f"📉 [조건미달] {news['title']} (사유: {qualify_reason})")
                continue

            # [2] 링크 중복 필터
            if news['link'] in seen_links: continue

            clean_title = html.unescape(news['title']).replace("[", "").replace("]", "").strip()
            
            # [3] 제목 내용 중복 필터
            is_similar = False
            match_cause = "" 
            for existing_title in collected_titles:
                if len(clean_title) < DUPLICATE_THRESHOLD: break
                for i in range(len(clean_title) - DUPLICATE_THRESHOLD + 1):
                    sub_string = clean_title[i : i + DUPLICATE_THRESHOLD]
                    if sub_string in existing_title:
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
                if len(clean_title) < DUPLICATE_THRESHOLD or len(past_title) < DUPLICATE_THRESHOLD:
                    break
                
                for i in range(len(clean_title) - DUPLICATE_THRESHOLD + 1):
                    sub_string = clean_title[i : i + DUPLICATE_THRESHOLD]
                    if sub_string in past_title:
                        is_past_duplicate = True
                        past_match_cause = sub_string 
                        matched_past_title = past_title 
                        break
                if is_past_duplicate: break
                
            if is_past_duplicate:
                print(f"🧟 [어제뉴스중복] {clean_title} (겹친단어: '{past_match_cause}')")
                continue

            # [5] 최종 합격 (합격 사유 함께 출력)
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
