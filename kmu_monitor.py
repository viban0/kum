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
def send_telegram_message(title, link, date="", category="", department=""):
    """텔레그램 메시지 발송"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[CONSOLE ONLY] 토큰 미설정 - [{category}] {title} | {date} | {link}")
        return

    # HTML 태그 깨짐 방지용 이스케이프
    safe_title = html.escape(title)
    safe_date = html.escape(date)
    safe_category = html.escape(category) if category else "장학"
    safe_dept = html.escape(department) if department else ""

    message = f"<b>[{safe_category} 공지]</b>\n\n"
    message += f"<b>제목:</b> {safe_title}\n"
    message += f"<b>날짜:</b> {safe_date}\n"
    if safe_dept:
        message += f"<b>작성부서:</b> {safe_dept}\n"
    message += f"<b>링크:</b> <a href=\"{link}\">게시글 바로가기</a>"

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
        print(f"[ERROR] 국민대 서버 요청 실패: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")

    # ul.board-list 내의 개별 li 선택
    posts = soup.select("ul.board-list > li")
    print(f"[INFO] 파싱된 게시글 개수: {len(posts)}개")

    new_posts = []

    for post in posts:
        # <a> 태그 파싱
        a_tag = post.select_one("a.board-item") or post.select_one("a")
        if not a_tag:
            continue

        link = a_tag.get("href", "").strip()
        if not link or link.startswith("javascript"):
            continue

        if not link.startswith("http"):
            link = BASE_URL + link

        # 카테고리 추출 (<span class="category">)
        category_el = post.select_one(".category")
        category = category_el.get_text(strip=True) if category_el else ""

        # 제목 추출 (<strong class="title">)
        title_el = post.select_one("strong.title") or post.select_one(".title")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue

        # 날짜 및 작성부서 추출
        date_el = post.select_one(".info .date") or post.select_one(".date")
        date = date_el.get_text(strip=True) if date_el else "날짜 미상"

        dept_el = post.select_one(".info .department") or post.select_one(".department")
        department = dept_el.get_text(strip=True) if dept_el else ""

        post_id = link

        if post_id not in processed_ids:
            new_posts.append({
                "id": post_id,
                "title": title,
                "link": link,
                "date": date,
                "category": category,
                "department": department
            })

    # 과거 순서부터 메시지 발송 (역순 정렬)
    new_posts.reverse()

    for p in new_posts:
        print(f"[신규 공지 발견] [{p['category']}] {p['title']} ({p['date']})")
        if not is_first_run:
            send_telegram_message(
                title=p["title"],
                link=p["link"],
                date=p["date"],
                category=p["category"],
                department=p["department"]
            )
        processed_ids.add(p["id"])

    if is_first_run:
        print(f"[최초 실행 완료] 총 {len(new_posts)}개 게시글 URL을 {DATA_FILE}에 최초 기록했습니다. (스팸 방지로 알림은 미발송)")

    save_processed_ids(processed_ids)
    print("모니터링 작업 완료.")

if __name__ == "__main__":
    crawl_kmu_notice()
