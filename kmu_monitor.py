import os
import html
import requests
from bs4 import BeautifulSoup

# ==================== [설정 및 상수] ====================
DATA_FILE = "kmu_data.txt"
URL = "https://www.kookmin.ac.kr/user/kmuNews/notice/7/index.do?currentPageNo=1"
BASE_URL = "https://www.kookmin.ac.kr"

# GitHub Actions Secrets 또는 환경변수에서 토큰/아이디를 읽어옵니다.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ==================== [유틸리티 함수] ====================
def load_processed_ids():
    """기존에 발송했던 공지 ID/링크 목록을 파일에서 불러옵니다."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_processed_ids(processed_ids):
    """업데이트된 공지 ID/링크 목록을 파일에 저장합니다."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        for pid in sorted(processed_ids):
            f.write(f"{pid}\n")

def send_telegram_message(title, link, date=""):
    """텔레그램 API를 사용하여 메시지를 전송합니다."""
    if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN" or not TELEGRAM_BOT_TOKEN:
        print(f"[CONSOLE NOTICE] 텔레그램 정보가 없어 콘솔로 출력합니다:\n제목: {title}\n날짜: {date}\n링크: {link}\n")
        return

    # HTML 태그 파싱 오류 방지를 위해 특수문자 이스케이프 적용
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
        print(f"[ERROR] 텔레그램 메시지 전송 실패: {e}")

# ==================== [메인 크롤링 로직] ====================
def crawl_kmu_notice():
    processed_ids = load_processed_ids()
    is_first_run = len(processed_ids) == 0  # 처음 실행 시 기존 글 전체 알림 스팸 방지

    try:
        response = requests.get(URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] 웹 페이지 요청 실패: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")

    # 게시글 목록 선택 (테이블 구조 및 ul/li 구조 모두 대응)
    posts = soup.select("ul.board-list > li, table.board-list tbody tr, table.board_list tbody tr")
    if not posts:
        posts = soup.select("ul.board_list > li, .board-list li, .board_list tr")

    new_posts = []

    for post in posts:
        # 제목 및 상세 링크 추출
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

        # 날짜 추출
        date_element = post.select_one(".date, td.date, .reg_date, .time")
        date = date_element.get_text(strip=True) if date_element else "날짜 미상"

        # 고유 식별자로 URL 사용
        post_id = link

        if post_id not in processed_ids:
            new_posts.append({
                "id": post_id,
                "title": title,
                "link": link,
                "date": date
            })

    # 최신 공지가 리스트 상단에 오므로 과거 순서대로 메시지를 보낼 수 있도록 역순 정렬
    new_posts.reverse()

    for p in new_posts:
        print(f"[새 공지 발견] {p['title']} ({p['date']})")
        if not is_first_run:
            send_telegram_message(p["title"], p["link"], p["date"])
        processed_ids.add(p["id"])

    if is_first_run:
        print(f"[최초 실행 완료] 현재 게시글 {len(new_posts)}개의 상태를 기록했습니다. (스팸 방지를 위해 메시지는 전송하지 않음)")

    save_processed_ids(processed_ids)
    print("크롤링 및 상태 업데이트가 완료되었습니다.")

if __name__ == "__main__":
    crawl_kmu_notice()
