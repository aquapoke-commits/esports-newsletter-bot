import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import feedparser
import html
import os  # ★ 필수: 운영체제(OS)의 기능을 쓰기 위해 추가
from datetime import datetime
import asyncio

# =====================================================================
# [보안 설정] 토큰을 코드에 적지 않고 환경 변수에서 가져옵니다.
# 깃허브 Settings > Secrets 에 저장해둔 'DISCORD_TOKEN'을 여기서 불러옵니다.
# =====================================================================
if 'DISCORD_TOKEN' in os.environ:
    DISCORD_TOKEN = os.environ['DISCORD_TOKEN']
else:
    # 깃허브가 아니라 내 컴퓨터에서 테스트할 때를 위한 안내
    print("⚠️ 에러: DISCORD_TOKEN 환경 변수가 없습니다.")
    print("   (깃허브 Actions에서 실행 중이라면 Secrets 설정을 확인하세요.)")
    exit()

# [설정] 채널 ID 리스트 (여기는 숫자니까 공개돼도 괜찮습니다)
# 콤마(,)로 구분해서 여러 개 추가 가능
TARGET_CHANNELS = [
    1447898781365567580, # 첫 번째 서버
    987654321098765432, # 두 번째 서버 (필요하면 추가)
]
# =====================================================================

KEYWORDS = ["이스포츠", "LCK", "T1", "Faker", "롤드컵", "발로란트", "젠지", "HLE", "LoL"]

# 봇 권한 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------------------------------
# [크롤링 함수] (기존과 동일)
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
            news_list.append({"title": entry.title, "link": entry.link})
    except: pass
    return news_list

def collect_news():
    print("📰 뉴스 수집 중...")
    all_news = []
    seen_links = set()
    
    # [설정] 개수 제한
    MAX_TOTAL = 20       
    MAX_PER_KEYWORD = 4  
    
    for keyword in KEYWORDS:
        if len(all_news) >= MAX_TOTAL: break
            
        n_res = get_naver_news(keyword)
        g_res = get_google_news(keyword)
        
        current_keyword_count = 0
        
        for news in n_res + g_res:
            if len(all_news) >= MAX_TOTAL: break
            if current_keyword_count >= MAX_PER_KEYWORD: break
                
            if news['link'] not in seen_links:
                clean_title = html.unescape(news['title']).replace("[", "").replace("]", "")
                all_news.append({"title": clean_title, "link": news['link']})
                seen_links.add(news['link'])
                current_keyword_count += 1
                
    print(f"📊 수집 완료: 총 {len(all_news)}개")
    return all_news

# ---------------------------------------------------
# [전송 로직] (기존과 동일)
# ---------------------------------------------------
async def send_newsletter(target_channel_id):
    channel = bot.get_channel(target_channel_id)
    if not channel:
        print(f"❌ 채널을 찾을 수 없습니다. (ID: {target_channel_id})")
        return

    news_data = collect_news()
    
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
    
    # 등록된 모든 채널에 전송
    for channel_id in TARGET_CHANNELS:
        await send_newsletter(channel_id)
    
    print("👋 임무 완료. 봇을 종료합니다.")
    await bot.close()

if __name__ == "__main__":
    # 여기서 환경변수에 저장된 진짜 토큰을 불러와서 실행합니다.
    bot.run(DISCORD_TOKEN)

