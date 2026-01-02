import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import feedparser
import html
import os
from datetime import datetime, timedelta  # [수정] time delta -> timedelta (띄어쓰기 제거)
import time
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
    987654321098765432,  # 테스트용
]

KEYWORDS = ["이스포츠", "VCT", "LCK", "PUBG", "티원", "Faker", "젠지", "HLE", "KT롤스터", "농심 레드포스", "DN SOOPers"]

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------------------------------
# [크롤링 함수]
# ---------------------------------------------------
def get_naver_news(keyword):
    news_list = []
    url = f"https://search.naver.com/search.naver?where=news&query={keyword}&sort=1"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        items = soup.select('.news_wrap')
        for item in items:
            title = item.select_one('.news_tit').text
            link = item.select_one('.news_tit')['href']
            date_info = item.select_one('.info_group .info')
            
            if date_info:
                time_text = date_info.text
                if "분 전" in time_text or "시간 전" in time_text:
                    news_list.append({"title": title, "link": link})
    except: pass
    return news_list

def get_google_news(keyword):
    news_list = []
    url = f"https://news.google.com/rss/search?q={keyword}+when:1d&hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if hasattr(entry, 'published_parsed'):
                pub_time = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                # 24시간 지난 뉴스 필터링
                if datetime.now() - pub_time > timedelta(days=1):
                    continue
            news_list.append({"title": entry.title, "link": entry.link})
    except: pass
    return news_list

def collect_news():
    print("📰 뉴스 수집 및 필터링 중...")
    all_news = []
    seen_links = set()
    collected_titles = [] 
    
    MAX_TOTAL = 20        
    MAX_PER_KEYWORD = 4
    DUPLICATE_THRESHOLD = 10
    
    for keyword in KEYWORDS:
        if len(all_news) >= MAX_TOTAL: break
            
        n_res = get_naver_news(keyword)
        g_res = get_google_news(keyword)
        
        current_keyword_count = 0
        
        for news in n_res + g_res:
            if len(all_news) >= MAX_TOTAL: break
            if current_keyword_count >= MAX_PER_KEYWORD: break
            
            if news['link'] in seen_links: continue

            clean_title = html.unescape(news['title']).replace("[", "").replace("]", "").strip()
            
            is_similar = False
            for existing_title in collected_titles:
                if len(clean_title) < DUPLICATE_THRESHOLD: break
                for i in range(len(clean_title) - DUPLICATE_THRESHOLD + 1):
                    sub_string = clean_title[i : i + DUPLICATE_THRESHOLD]
                    if sub_string in existing_title:
                        is_similar = True
                        break 
                if is_similar: break

            if not is_similar:
                all_news.append({"title": clean_title, "link": news['link']})
                seen_links.add(news['link'])
                collected_titles.append(clean_title)
                current_keyword_count += 1
                
    print(f"📊 수집 완료: 총 {len(all_news)}개")
    return all_news
    
# ---------------------------------------------------
# [전송 로직] - 뉴스를 인자로 받도록 수정
# ---------------------------------------------------
async def send_newsletter(target_channel_id, news_data):
    channel = bot.get_channel(target_channel_id)
    if not channel:
        print(f"❌ 채널을 찾을 수 없습니다. (ID: {target_channel_id})")
        return

    if not news_data:
        await channel.send("💤 지난 24시간 동안 새로운 이스포츠 뉴스가 없습니다.")
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
    print(f"✅ 깃허브 액션 봇 로그인: {bot.user}")
    
    # 1. 뉴스 수집은 딱 한 번만 실행! (효율성 UP)
    todays_news = collect_news()
    
    # 2. 수집된 뉴스를 가지고 각 채널에 배달
    for channel_id in TARGET_CHANNELS:
        await send_newsletter(channel_id, todays_news)
    
    print("👋 임무 완료. 봇을 종료합니다.")
    await bot.close()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)

