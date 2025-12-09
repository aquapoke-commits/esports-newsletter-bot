import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import feedparser
import html
import os
from datetime import datetime
import asyncio

# ==========================================
# [설정] 깃허브 시크릿에서 토큰을 가져옵니다 (수정 X)
# ==========================================
DISCORD_TOKEN = os.environ['DISCORD_TOKEN']

# [설정] 채널 ID는 여기에 직접 적어주세요 (숫자만)
CHANNEL_ID = 1447898781365567580 
# ==========================================

KEYWORDS = ["이스포츠", "LCK", "T1", "Faker", "롤드컵", "발로란트", "젠지", "HLE", "LoL"]

# 봇 권한 설정
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
        if len(all_news) >= MAX_TOTAL:
            break
            
        n_res = get_naver_news(keyword)
        g_res = get_google_news(keyword)
        
        current_keyword_count = 0
        
        for news in n_res + g_res:
            if len(all_news) >= MAX_TOTAL:
                break
            
            if current_keyword_count >= MAX_PER_KEYWORD:
                break
                
            if news['link'] not in seen_links:
                # 특수문자(&quot; 등)를 사람이 읽을 수 있게 변환
                clean_title = html.unescape(news['title'])
                # 보기 싫은 대괄호 제거 (선택사항)
                clean_title = clean_title.replace("[", "").replace("]", "")
                
                all_news.append({"title": clean_title, "link": news['link']})
                seen_links.add(news['link'])
                
                current_keyword_count += 1
                
    print(f"📊 수집 완료: 총 {len(all_news)}개")
    return all_news

# ---------------------------------------------------
# [전송 로직]
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
    
    # 임베드 설명 길이 제한 (디스코드 최대 4096자, 안전하게 3500자)
    MAX_DESCRIPTION_LEN = 3500
    
    current_description = ""
    page_count = 1
    
    # 첫 표지 생성
    embed = discord.Embed(
        title=f"🎮 {today} 이스포츠 주요 소식",
        color=0x00ff00 # 네온 그린
    )

    for idx, news in enumerate(news_data):
        # 한 줄 포맷: `번호.` [제목](링크)
        one_line = f"` {idx+1}. ` [{news['title']}]({news['link']})\n\n"
        
        # 글자 수 초과 시 전송하고 새 페이지
        if len(current_description) + len(one_line) > MAX_DESCRIPTION_LEN:
            embed.description = current_description
            embed.set_footer(text=f"HantaGG NewsBot • {page_count}페이지")
            await channel.send(embed=embed)
            
            page_count += 1
            current_description = ""
            embed = discord.Embed(color=0x00ff00) # 새 임베드
            
        current_description += one_line

    # 마지막 페이지 전송
    if current_description:
        embed.description = current_description
        embed.set_footer(text=f"HantaGG NewsBot • 마지막 페이지 (총 {len(news_data)}건)")
        await channel.send(embed=embed)

    print("✅ 뉴스레터 발송 완료!")

# ---------------------------------------------------
# [봇 실행 및 자동 종료]
# ---------------------------------------------------
@bot.event
async def on_ready():
    print(f"✅ 깃허브 액션 봇 로그인: {bot.user}")
    
    # 뉴스 전송 시작
    await send_newsletter(CHANNEL_ID)
    
    # 전송이 끝나면 봇을 끕니다 (깃허브 액션용 필수 코드)
    print("👋 임무 완료. 봇을 종료합니다.")
    await bot.close()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)