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

    # 실제 구조: view.do 경로가 포함된 <a> 태그 수집
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

        # ?currentPageNo=... 쿼리 파라미터를 제거하여 고유 ID 식별
        unique_id = full_url.split("?")[0]

        if unique_id in seen_links:
            continue
        seen_links.add(unique_id)

        # 1. 제목 추출 (<p class="title">)
        title_el = a.select_one("p.title, .title")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue

        # 2. 카테고리 추출 (<span class="ctg_name">)
        ctg_el = a.select_one("span.ctg_name, .ctg_name")
        category = ctg_el.get_text(strip=True) if ctg_el else ""

        # 3. 날짜 및 부서 추출 (<div class="board_etc"> 내 span 태그)
        etc_spans = a.select("div.board_etc > span")
        date = etc_spans[0].get_text(strip=True) if len(etc_spans) > 0 else "날짜 미상"
        department = etc_spans[1].get_text(strip=True) if len(etc_spans) > 1 else ""

        parsed_posts.append({
            "id": unique_id,
            "title": title,
            "link": full_url,
            "date": date,
            "category": category,
            "department": department
        })

    print(f"[INFO] 파싱된 게시글 개수: {len(parsed_posts)}개")

    new_posts = [p for p in parsed_posts if p["id"] not in processed_ids]
    new_posts.reverse()  # 과거 순서부터 발송

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

    if is_first_run and len(parsed_posts) > 0:
        print(f"[최초 실행 완료] 총 {len(parsed_posts)}개 게시글 URL을 {DATA_FILE}에 최초 기록했습니다. (스팸 방지로 알림은 미발송)")

    if len(processed_ids) > 0:
        save_processed_ids(processed_ids)
        print("모니터링 작업 완료.")

if __name__ == "__main__":
    crawl_kmu_notice()
