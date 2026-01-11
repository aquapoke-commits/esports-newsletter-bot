import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import feedparser
import html
import os
# [중요] 정확한 시간 계산을 위해 timezone 필수
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
    987654321098765432,  # 테스트용
]

# [설정] 검색어 목록
KEYWORDS = ["이스포츠", "LCK", "VCT", "이터널 리턴 이스포츠", "PUBG", "티원", "Faker", "Gen.G", "HLE", "kt Rolster", "디플러스 기아", "피어엑스", "농심 레드포스", "한진 브리온", "DRX", "DN SOOPers"]

# [설정] 차단할 단어 (소문자)
EXCLUDE_LIST = ["theqoo", "더쿠", "instiz", "fmkorea", "dcinside", "디시", "바카라"]

# [설정] 뉴스 유효 시간 (단위: 시간)
# 24시간이 너무 널널하면 18~20시간으로 줄이세요.
MAX_HOURS = 24

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------------------------------
# [크롤링 함수] - 작성 시간 로그 추가
# ---------------------------------------------------
def get_naver_news(keyword):
    news_list = []
    clean_keyword = keyword.replace(" ", "+")
    url = f"https://search.naver.com/search.naver?where=news&query={clean_keyword}&sort=1"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # [수정] 가장 안전한 방법: 리스트 항목(li.bx)을 먼저 찾습니다.
        items = soup.select('ul.list_news > li.bx')
        
        # print(f"🔍 [네이버] '{keyword}' 검색결과: {len(items)}개 발견") 
        
        for item in items:
            # 제목이 없으면 뉴스 아님 (패스)
            title_tag = item.select_one('a.news_tit')
            if not title_tag: continue
            
            title = title_tag.text
            link = title_tag['href']
            
            # [Naver 시간 정밀 검사]
            # info_group이 없을 수도 있어서 안전하게 처리
            info_group = item.select('.info_group .info')
            is_recent = False
            time_log = "알수없음"
            
            for info in info_group:
                text = info.text
                if "분 전" in text or "시간 전" in text:
                    time_log = text 
                    if "일 전" in text:
                        # print(f"⏰ [네이버|탈락] {keyword} | {title} (사유: '{text}' - 수정된 구 기사)")
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
                    "time_str": time_log 
                })

    except Exception as e:
        print(f"❌ 네이버 오류({keyword}): {e}")
        pass
    return news_list

def get_google_news(keyword):
    news_list = []
    clean_keyword = keyword.replace(" ", "+")
    url = f"https://news.google.com/rss/search?q={clean_keyword}+when:1d&hl=ko&gl=KR&ceid=KR:ko"
    
    # [연도 필터] 구글이 2026년인데 2025년 기사를 '오늘'로 착각해서 보낼 때 거르기 위함
    # 현재 연도(2026)가 아닌 과거 연도가 제목에 있으면 의심
    PAST_YEARS = ["2020", "2021", "2022", "2023", "2024", "2025"] 

    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if not hasattr(entry, 'published_parsed') or entry.published_parsed is None:
                continue
            
            try:
                # 1. 시간 계산 (UTC)
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

                # [시간 제한]
                if diff_hours > MAX_HOURS:
                    print(f"⏰ [구글|탈락] {keyword} | {entry.title} (작성시간: {time_str_kst})")
                    continue
                
                # [추가 필터] 제목에 과거 연도가 포함되어 있는지 검사 (예: 김정균 감독 2025...)
                is_old_title = False
                for year in PAST_YEARS:
                    # 제목에는 있는데, 문맥상 '2025 시즌 결산' 같은 건 통과시켜야 할 수도 있음.
                    # 하지만 지금처럼 '엉뚱한 옛날 기사'가 문제라면 과감히 거르는 게 낫습니다.
                    if year in entry.title:
                         # 현재가 2026년 1월이므로 '2025'는 놔둘지 고민되지만, 
                         # 명확한 과거 기사 재탕을 막으려면 거르는게 안전합니다.
                         # (필요시 리스트에서 "2025"는 빼세요)
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
    
    todays_news = collect_news()
    
    for channel_id in TARGET_CHANNELS:
        await send_newsletter(channel_id, todays_news)
    
    print("👋 임무 완료. 종료합니다.")
    await bot.close()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)







