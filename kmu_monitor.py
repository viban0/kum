import os
import html
import requests
from bs4 import BeautifulSoup

# ==================== [설정 및 상수] ====================
DATA_FILE = "kmu_data.txt"
URL = "https://www.kookmin.ac.kr/user/kmuNews/notice/7/index.do?currentPageNo=1"
BASE_URL = "https://www.kookmin.ac.kr"

RAW_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# 토큰 'bot' 중복 입력 자동 보정
if RAW_TOKEN.startswith("bot"):
    TELEGRAM_BOT_TOKEN = RAW_TOKEN[3:]
else:
    TELEGRAM_BOT_TOKEN = RAW_TOKEN

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.kookmin.ac.kr/"
}

# ==================== [상태 저장소 로직] ====================
def load_processed_ids():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_processed_ids(processed_ids):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        for pid in sorted(processed_ids):
            f.write(f"{pid}\n")

# ==================== [텔레그램 알림 전송] ====================
def send_telegram_message(title, link):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[CONSOLE ONLY] {title} | {link}")
        return

    safe_title = html.escape(title)

    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"<b>{safe_title}</b>",
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "🔗 게시글 바로가기", "url": link}]
            ]
        }
    }

    try:
        res = requests.post(telegram_url, json=payload, timeout=10)
        res_data = res.json()
        
        if res.status_code == 200 and res_data.get("ok"):
            print(f"[SUCCESS] 텔레그램 발송 성공: {title}")
        else:
            description = res_data.get("description", res.text)
            print(f"[ERROR] 텔레그램 응답 에러 (코드 {res.status_code}): {description}")
    except Exception as e:
        print(f"[ERROR] 네트워크 통신 실패: {e}")

# ==================== [크롤링 메인 로직] ====================
def crawl_kmu_notice():
    processed_ids = load_processed_ids()
    is_first_run = len(processed_ids) == 0

    try:
        response = requests.get(URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] 국민대 서버 요청 실패: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")

    a_tags = soup.find_all("a", href=lambda h: h and "view.do" in h)
    
    seen_links = set()
    parsed_posts = []

    for a in a_tags:
        raw_href = a.get("href", "").strip()
        if not raw_href:
            continue

        if not raw_href.startswith("http"):
            full_url = BASE_URL + raw_href
        else:
            full_url = raw_href

        unique_id = full_url.split("?")[0]

        if unique_id in seen_links:
            continue
        seen_links.add(unique_id)

        title_el = a.select_one("p.title, .title, strong")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue

        parsed_posts.append({
            "id": unique_id,
            "title": title,
            "link": full_url
        })

    print(f"[INFO] 파싱된 게시글 개수: {len(parsed_posts)}개")

    new_posts = [p for p in parsed_posts if p["id"] not in processed_ids]
    new_posts.reverse()

    for p in new_posts:
        print(f"[신규 공지 발견] {p['title']}")
        if not is_first_run:
            send_telegram_message(title=p["title"], link=p["link"])
        processed_ids.add(p["id"])

    if is_first_run and len(parsed_posts) > 0:
        print(f"[최초 실행 완료] 총 {len(parsed_posts)}개 게시글 URL을 {DATA_FILE}에 최초 기록했습니다.")

    if len(processed_ids) > 0:
        save_processed_ids(processed_ids)
        print("모니터링 작업 완료.")

if __name__ == "__main__":
    crawl_kmu_notice()
