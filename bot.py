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
EXCLUDE_LIST = ["theqoo", "더쿠", "instiz", "fmkorea", "dcinside"]

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
        items = soup.select('.news_wrap')
        
        for item in items:
            title = item.select_one('.news_tit').text
            link = item.select_one('.news_tit')['href']
            
            # [Naver 시간 정밀 검사]
            info_group = item.select('.info_group .info')
            is_recent = False
            time_log = "알수없음" # 로그용 변수
            
            for info in info_group:
                text = info.text
                if "분 전" in text or "시간 전" in text:
                    time_log = text # 예: "1시간 전" 저장
                    if "일 전" in text:
                        print(f"⏰ [네이버|탈락] {keyword} | {title} (작성시간: {text} - 수정된 구 기사)")
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
                    "time_str": time_log # 작성 시간 정보 저장
                })

    except Exception as e:
        print(f"❌ 네이버 오류({keyword}): {e}")
        pass
    return news_list

def get_google_news(keyword):
    news_list = []
    clean_keyword = keyword.replace(" ", "+")
    url = f"https://news.google.com/rss/search?q={clean_keyword}+when:1d&hl=ko&gl=KR&ceid=KR:ko"
    
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if not hasattr(entry, 'published_parsed') or entry.published_parsed is None:
                continue
            
            try:
                # 1. 시간 계산 (UTC 기준)
                pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                current_date = datetime.now(timezone.utc)
                
                diff_seconds = (current_date - pub_date).total_seconds()
                diff_hours = diff_seconds / 3600
                if diff_hours < 0: diff_hours = 0
                
                # 2. 로그 출력을 위해 한국 시간(KST)으로 변환
                pub_date_kst = pub_date + timedelta(hours=9)
                time_str_kst = pub_date_kst.strftime("%Y-%m-%d %H:%M:%S")

                source_name = "Google"
                if hasattr(entry, 'source') and hasattr(entry.source, 'title'):
                    source_name = entry.source.title

                if diff_hours > MAX_HOURS:
                    print(f"⏰ [구글|탈락] {keyword} | {entry.title} (작성시간: {time_str_kst} | {diff_hours:.1f}시간 전)")
                    continue
                
                news_list.append({
                    "title": entry.title,
                    "link": entry.link,
                    "source": source_name,
                    "origin": "구글",
                    "time_str": time_str_kst # 한국 시간 문자열 저장
                })
                
            except:
                continue
                
    except Exception as e:
        print(f"❌ 구글 오류({keyword}): {e}")
        pass
        
    return news_list

def collect_news():
    print(f"\n📰 뉴스 수집 및 정밀 심사 시작 (제한: {MAX_HOURS}시간)")
    all_news = []
    seen_links = set()
    collected_titles = [] 
    
    MAX_TOTAL = 20        
    MAX_PER_KEYWORD = 4
    DUPLICATE_THRESHOLD = 10
    
    for keyword in KEYWORDS:
        if len(all_news) >= MAX_TOTAL: 
            print("🛑 [전체제한] 총 20개를 모두 채워 수집을 종료합니다.")
            break
            
        n_res = get_naver_news(keyword)
        g_res = get_google_news(keyword)
        
        current_keyword_count = 0
        
        for news in n_res + g_res:
            if len(all_news) >= MAX_TOTAL: break
            
            if current_keyword_count >= MAX_PER_KEYWORD: 
                break
            
            # [1] 차단 사이트 필터
            is_excluded = False
            check_target = (news['link'] + news['title'] + news.get('source', '')).lower()
            
            for ban_word in EXCLUDE_LIST:
                if ban_word.lower() in check_target:
                    is_excluded = True
                    print(f"🚫 [사이트차단][{news['origin']}] {news['title']} (이유: {ban_word})") 
                    break
            
            if is_excluded: continue 

            # [2] 링크 중복 필터
            if news['link'] in seen_links: 
                continue

            clean_title = html.unescape(news['title']).replace("[", "").replace("]", "").strip()
            
            # [3] 제목 내용 중복 필터
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
                print(f"🔗 [내용중복][{news['origin']}] {clean_title}")
                continue

            # [4] 최종 합격 - 작성 시간 정보(time_str) 함께 출력
            print(f"✅ [최종선별][{news['origin']}] {clean_title} (작성시간: {news.get('time_str', '알수없음')})")
            
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
    
    todays_news = collect_news()
    
    for channel_id in TARGET_CHANNELS:
        await send_newsletter(channel_id, todays_news)
    
    print("👋 임무 완료. 종료합니다.")
    await bot.close()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)





