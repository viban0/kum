import html
import os
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

# ==================== [설정 및 상수] ====================
DATA_FILE = "kmu_data.txt"

RAW_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# 토큰 'bot' 중복 입력 자동 보정
if RAW_TOKEN.startswith("bot"):
    TELEGRAM_BOT_TOKEN = RAW_TOKEN[3:]
else:
    TELEGRAM_BOT_TOKEN = RAW_TOKEN

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 1. 국민대학교 일반공지 게시판 설정
KMU_URL = (
    "https://www.kookmin.ac.kr/user/kmuNews/notice/7/index.do?currentPageNo=1"
)
KMU_BASE_URL = "https://www.kookmin.ac.kr"

# 2. 신규 대학 장학게시판 설정 (실제 사이트 주소에 맞게 수정하세요)
NEW_BOARD_BASE_URL = "https://www.hongik.ac.kr"  # 예: https://www.example.ac.kr
NEW_BOARD_URL = (
    "https://www.hongik.ac.kr/kr/education/notice-undergrad.do?mode=list&srCategoryId=24&srStartDt=&srEndDt=&srSearchKey=article_title&srSearchVal="  # 실제 장학 게시판 URL
)


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
def send_telegram_message(board_name, title, link):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[CONSOLE ONLY] [{board_name}] {title} | {link}")
        return

    safe_title = html.escape(title)
    message_text = f"<b>[{board_name}]</b>\n{safe_title}"

    telegram_url = (
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message_text,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [[{"text": "🔗 게시글 바로가기", "url": link}]]
        },
    }

    try:
        res = requests.post(telegram_url, json=payload, timeout=10)
        res_data = res.json()

        if res.status_code == 200 and res_data.get("ok"):
            print(f"[SUCCESS] 텔레그램 발송 성공: [{board_name}] {title}")
        else:
            description = res_data.get("description", res.text)
            print(
                f"[ERROR] 텔레그램 응답 에러 (코드 {res.status_code}): {description}"
            )
    except Exception as e:
        print(f"[ERROR] 네트워크 통신 실패: {e}")


# ==================== [크롤러 1: 국민대 일반공지] ====================
def fetch_kmu_notices():
    posts = []
    headers = {**HEADERS, "Referer": "https://www.kookmin.ac.kr/"}

    try:
        response = requests.get(KMU_URL, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] 국민대 서버 요청 실패: {e}")
        return posts

    soup = BeautifulSoup(response.text, "html.parser")
    a_tags = soup.find_all("a", href=lambda h: h and "view.do" in h)

    seen_links = set()

    for a in a_tags:
        raw_href = a.get("href", "").strip()
        if not raw_href:
            continue

        full_url = urljoin(KMU_BASE_URL, raw_href)

        # 기존 버그 수정: 쿼리 파라미터 잘라냄 없이 full_url 전체를 ID로 사용
        if full_url in seen_links:
            continue
        seen_links.add(full_url)

        title_el = a.select_one("p.title, .title, strong")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue

        posts.append(
            {
                "id": full_url,
                "title": title,
                "link": full_url,
                "board_name": "국민대 일반공지",
            }
        )

    return posts


# ==================== [크롤러 2: 신규 대학 장학게시판] ====================
def fetch_scholarship_notices():
    posts = []
    if "example.ac.kr" in NEW_BOARD_URL:
        # 기본 예시 주소인 경우 크롤링을 건너뜁니다.
        return posts

    try:
        response = requests.get(NEW_BOARD_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] 장학 게시판 서버 요청 실패: {e}")
        return posts

    soup = BeautifulSoup(response.text, "html.parser")
    rows = soup.select("tbody tr")

    seen_links = set()

    for row in rows:
        a_tag = row.select_one("div.b-title-box a")
        if not a_tag:
            continue

        raw_href = a_tag.get("href", "").strip()
        if not raw_href:
            continue

        full_url = urljoin(NEW_BOARD_BASE_URL, raw_href)

        if full_url in seen_links:
            continue
        seen_links.add(full_url)

        # title 속성의 " 자세히 보기" 문구 정제 및 fallback 처리
        title = a_tag.get("title", "").replace(" 자세히 보기", "").strip()
        if not title:
            title = a_tag.text.strip()

        if not title:
            continue

        posts.append(
            {
                "id": full_url,
                "title": title,
                "link": full_url,
                "board_name": "장학공지",
            }
        )

    return posts


# ==================== [메인 실행 로직] ====================
def main():
    processed_ids = load_processed_ids()
    is_first_run = len(processed_ids) == 0

    # 1. 각 게시판에서 파싱 데이터 수집
    all_parsed_posts = []
    all_parsed_posts.extend(fetch_kmu_notices())
    all_parsed_posts.extend(fetch_scholarship_notices())

    print(f"[INFO] 총 파싱된 게시글 개수: {len(all_parsed_posts)}개")

    # 2. 미처리 신규 게시글 필터링
    new_posts = [p for p in all_parsed_posts if p["id"] not in processed_ids]

    # 최신글이 나중에 오도록 역순 정렬 (텔레그램 순서 보정)
    new_posts.reverse()

    # 3. 알림 전송 및 ID 등록
    for p in new_posts:
        print(f"[신규 공지 발견] [{p['board_name']}] {p['title']}")
        if not is_first_run:
            send_telegram_message(
                board_name=p["board_name"], title=p["title"], link=p["link"]
            )
        processed_ids.add(p["id"])

    # 4. 최초 실행 처리
    if is_first_run and len(all_parsed_posts) > 0:
        print(
            f"[최초 실행 완료] 총 {len(all_parsed_posts)}개 게시글 URL을 {DATA_FILE}에 기록했습니다."
        )

    # 5. 상태 파일 저장
    if len(processed_ids) > 0:
        save_processed_ids(processed_ids)
        print("모니터링 작업 완료.")


if __name__ == "__main__":
    main()
