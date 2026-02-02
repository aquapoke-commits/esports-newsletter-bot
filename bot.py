import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import feedparser
import html
import os
import re # [추가] 정규표현식 (메시지에서 제목만 뽑아내기 위해 필요)
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
    # 987654321098765432,  # 테스트용
]

# [설정] 검색어 목록
KEYWORDS = ["이스포츠", "LCK", "VCT", "이터널 리턴 이스포츠", "PUBG", "티원", "Faker", "Gen.G", "HLE", "kt Rolster", "디플러스 기아", "피어엑스", "농심 레드포스", "한진 브리온", "DRX", "DN SOOPers"]

# [설정] 차단할 단어
EXCLUDE_LIST = ["theqoo", "더쿠", "instiz", "인스티즈", "fmkorea", "펨코", "dcinside", "디시", "바카라", "토토", "카지노", "슬롯", "MSN", "인벤", "보통주", "패치노트", "사모대출", "investing","vietnam", "ZUM"]

# [설정] 뉴스 유효 시간
MAX_HOURS = 24

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------------------------------
# [함수 0] 과거 기록 불러오기 (기억력 추가)
# ---------------------------------------------------
async def get_past_titles(channel_id):
    print("⏳ 어제 보낸 뉴스 기록을 확인하는 중...")
    past_titles = []
    channel = bot.get_channel(channel_id)
    
    if not channel:
        print("⚠️ 기록을 확인할 채널을 찾지 못했습니다.")
        return []

    try:
        # 최근 메시지 5개만 읽어와도 충분함 (어제 뉴스레터가 그 안에 있을 테니까)
        async for message in channel.history(limit=5):
            # 봇이 보낸 메시지만 확인
            if message.author == bot.user:
                for embed in message.embeds:
                    if embed.description:
                        # 정규식으로 [제목](링크) 형태에서 '제목'만 추출
                        # 패턴: [글자] -> 글자만 뽑아냄
                        matches = re.findall(r"\[(.*?)\]\(http", embed.description)
                        past_titles.extend(matches)
                        
        print(f"🧠 기억 완료: 과거 뉴스 제목 {len(past_titles)}개를 로드했습니다.")
        return past_titles
        
    except Exception as e:
        print(f"⚠️ 과거 기록 조회 실패: {e}")
        return []

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
                    "keyword": keyword
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
                    "keyword": keyword
                })
                
            except:
                continue
                
    except Exception as e:
        print(f"❌ 구글 오류({keyword}): {e}")
        pass
        
    return news_list

# ---------------------------------------------------
# [통합 함수] 뉴스 수집 및 선별 (과거 기록 비교 추가)
# ---------------------------------------------------
def collect_news(past_titles):
    print(f"\n📰 뉴스 수집 및 정밀 심사 시작 (제한: {MAX_HOURS}시간)")
    all_news = []
    seen_links = set()
    collected_titles = [] 
    
    MAX_TOTAL = 20        
    MAX_PER_KEYWORD = 4
    DUPLICATE_THRESHOLD = 6
    
    for keyword in KEYWORDS:
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
                    print(f"🚫 [사이트차단][{news['origin']}][키워드:{news['keyword']}] {news['title']} (이유: {ban_word})") 
                    break
            
            if is_excluded: continue 

            # [2] 링크 중복 필터
            if news['link'] in seen_links: continue

            clean_title = html.unescape(news['title']).replace("[", "").replace("]", "").strip()
            
            # [3] 제목 내용 중복 필터 (오늘 수집한 것들끼리 비교)
            is_similar = False
            for existing_title in collected_titles:
                if len(clean_title) < DUPLICATE_THRESHOLD: break
                for i in range(len(clean_title) - DUPLICATE_THRESHOLD + 1):
                    sub_string = clean_title[i : i + DUPLICATE_THRESHOLD]
                    if sub_string in existing_title:
                        is_similar = True
                        break 
                if is_similar: break
            
            if is_similar:
                print(f"🔗 [내용중복][{news['origin']}][키워드:{news['keyword']}] {clean_title}")
                continue
            
            # [4] ★ 과거 기록(어제 뉴스) 중복 필터 (추가됨) ★
            is_past_duplicate = False
            for past_title in past_titles:
                # 과거 제목이 너무 짧으면 패스
                if len(clean_title) < DUPLICATE_THRESHOLD or len(past_title) < DUPLICATE_THRESHOLD:
                    break
                
                # 10글자 이상 겹치는지 확인
                for i in range(len(clean_title) - DUPLICATE_THRESHOLD + 1):
                    sub_string = clean_title[i : i + DUPLICATE_THRESHOLD]
                    if sub_string in past_title:
                        is_past_duplicate = True
                        break
                if is_past_duplicate: break
                
            if is_past_duplicate:
                print(f"🧟 [어제뉴스중복] {clean_title} (어제 이미 전송됨)")
                continue

            # [5] 최종 합격
            print(f"✅ [최종선별][{news['origin']}][키워드:{news['keyword']}] {clean_title} (작성시간: {news.get('time_str', '알수없음')})")
            
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
        # 1. 봇이 기억을 되살립니다 (어제 보낸 뉴스 제목 가져오기)
        # TARGET_CHANNELS의 첫 번째 채널을 기준으로 기록을 확인합니다.
        past_titles = []
        if TARGET_CHANNELS:
            past_titles = await get_past_titles(TARGET_CHANNELS[0])
            
        # 2. 어제 기록(past_titles)을 전달하여 뉴스를 수집합니다.
        todays_news = collect_news(past_titles)
        
        # 3. 전송
        for channel_id in TARGET_CHANNELS:
            await send_newsletter(channel_id, todays_news)
            
    except Exception as e:
        print(f"❌ 실행 중 치명적 오류 발생: {e}")
    
    print("👋 임무 완료. 종료합니다.")
    await bot.close()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)




