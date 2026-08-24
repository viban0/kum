import os
import html
import requests
from bs4 import BeautifulSoup

# ==================== [설정 및 상수] ====================
DATA_FILE = "kmu_data.txt"
URL = "https://www.kookmin.ac.kr/user/kmuNews/notice/7/index.do?currentPageNo=1"
BASE_URL = "https://www.kookmin.ac.kr"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 실제 PC 브라우저와 동일한 완벽한 헤더 구성 (차단 방지)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.kookmin.ac.kr/",
    "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin"
}

def load_processed_ids():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_processed_ids(processed_ids):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        for pid in sorted(processed_ids):
            f.write(f"{pid}\n")

def send_telegram_message(title, link, date="", category="", department=""):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[CONSOLE ONLY] [{category}] {title} | {date} | {link}")
        return

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

def crawl_kmu_notice():
    processed_ids = load_processed_ids()
    is_first_run = len(processed_ids) == 0

    session = requests.Session()
    try:
        response = session.get(URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] 국민대 서버 요청 실패: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")

    # 1. 다중 선택자 지원 (ul.board-list 내 li 우선 탐색 후 fallback)
    posts = soup.select("ul.board-list > li")
    if not posts:
        posts = soup.select(".board-list li")
    if not posts:
        # li 단계 없이 a.board-item을 직접 감싸는 요소 탐색
        items = soup.select("a.board-item")
        posts = [item.parent for item in items]

    print(f"[INFO] 파싱된 게시글 개수: {len(posts)}개")

    # 게시글을 전혀 찾지 못한 경우 디버깅 정보 출력
    if len(posts) == 0:
        print(f"[DEBUG] 응답 상태 코드: {response.status_code}")
        print(f"[DEBUG] 최종 URL: {response.url}")
        print(f"[DEBUG] 수신된 HTML 일부 (최대 1000자):\n{response.text[:1000]}")
        return

    new_posts = []

    for post in posts:
        a_tag = post.select_one("a.board-item") if post.name != "a" else post
        if not a_tag:
            a_tag = post.select_one("a")
        if not a_tag:
            continue

        link = a_tag.get("href", "").strip()
        if not link or link.startswith("javascript"):
            continue

        if not link.startswith("http"):
            link = BASE_URL + link

        category_el = post.select_one(".category")
        category = category_el.get_text(strip=True) if category_el else ""

        title_el = post.select_one("strong.title, .title")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            # a 태그 내부의 전체 텍스트 fallback
            title = a_tag.get_text(strip=True)
        if not title:
            continue

        date_el = post.select_one(".info .date, .date")
        date = date_el.get_text(strip=True) if date_el else "날짜 미상"

        dept_el = post.select_one(".info .department, .department")
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

    if is_first_run and len(new_posts) > 0:
        print(f"[최초 실행 완료] 총 {len(new_posts)}개 게시글 URL을 {DATA_FILE}에 최초 기록했습니다. (스팸 방지로 알림은 미발송)")

    if len(processed_ids) > 0:
        save_processed_ids(processed_ids)
        print("모니터링 작업 완료.")

if __name__ == "__main__":
    crawl_kmu_notice()
