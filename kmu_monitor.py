import os
import html
import requests
from bs4 import BeautifulSoup

# ==================== [설정 및 상수] ====================
DATA_FILE = "kmu_data.txt"
URL = "https://www.kookmin.ac.kr/user/kmuNews/notice/7/index.do?currentPageNo=1"
BASE_URL = "https://www.kookmin.ac.kr"

# GitHub Actions Secrets 환경변수
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ==================== [상태 저장소 로직] ====================
def load_processed_ids():
    """기존 처리한 공지 URL 목록 불러오기"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_processed_ids(processed_ids):
    """처리된 공지 URL 목록 저장하기"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        for pid in sorted(processed_ids):
            f.write(f"{pid}\n")

# ==================== [텔레그램 알림 전송] ====================
def send_telegram_message(title, link, date=""):
    """텔레그램 메시지 발송"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[CONSOLE ONLY] 토큰 미설정 - 제목: {title} | 날짜: {date} | 링크: {link}")
        return

    # HTML 태그 깨짐 방지용 이스케이프
    safe_title = html.escape(title)
    safe_date = html.escape(date)

    message = (
        f"<b>[국민대학교 장학공지]</b>\n\n"
        f"<b>제목:</b> {safe_title}\n"
        f"<b>날짜:</b> {safe_date}\n"
        f"<b>링크:</b> <a href=\"{link}\">게시글 바로가기</a>"
    )

    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    try:
        res = requests.post(telegram_url, json=payload, timeout=10)
        res.raise_for_status()
    except Exception as e:
        print(f"[ERROR] 텔레그램 전송 실패: {e}")

# ==================== [크롤링 메인 로직] ====================
def crawl_kmu_notice():
    processed_ids = load_processed_ids()
    is_first_run = len(processed_ids) == 0  # 첫 실행 시 스팸 방지

    try:
        response = requests.get(URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] KMU 서버 요청 실패: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")

    # 게시글 선택자 대응
    posts = soup.select("ul.board-list > li, table.board-list tbody tr, table.board_list tbody tr")
    if not posts:
        posts = soup.select("ul.board_list > li, .board-list li, .board_list tr")

    new_posts = []

    for post in posts:
        title_element = post.select_one(".title a, a.title, td.title a, .subject a") or post.select_one("a")
        if not title_element:
            continue

        title = title_element.get_text(strip=True)
        if not title:
            continue

        link = title_element.get("href", "")
        if not link or link.startswith("javascript"):
            continue

        if not link.startswith("http"):
            link = BASE_URL + link

        date_element = post.select_one(".date, td.date, .reg_date, .time")
        date = date_element.get_text(strip=True) if date_element else "날짜 미상"

        post_id = link

        if post_id not in processed_ids:
            new_posts.append({
                "id": post_id,
                "title": title,
                "link": link,
                "date": date
            })

    # 과거 순서부터 메시지 발송
    new_posts.reverse()

    for p in new_posts:
        print(f"[신규 공지] {p['title']} ({p['date']})")
        if not is_first_run:
            send_telegram_message(p["title"], p["link"], p["date"])
        processed_ids.add(p["id"])

    if is_first_run:
        print(f"[최초 실행 완료] 기존 공지 {len(new_posts)}개 상태 저장 (알림 미발송)")

    save_processed_ids(processed_ids)
    print("모니터링 작업 완료.")

if __name__ == "__main__":
    crawl_kmu_notice()
