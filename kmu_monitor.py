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

    try:
        response = requests.get(URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] 국민대 서버 요청 실패: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")

    # 핵심 개편: 상세페이지 URL 패턴(detail.do)을 가진 <a> 태그를 직접 추적
    a_tags = soup.find_all("a", href=lambda h: h and "detail.do" in h)
    
    seen_links = set()
    parsed_posts = []

    for a in a_tags:
        link = a.get("href", "").strip()
        if not link:
            continue

        if not link.startswith("http"):
            link = BASE_URL + link

        # 중복 링크 제외
        if link in seen_links:
            continue
        seen_links.add(link)

        # parent (li 또는 tr) 추출
        parent = a.find_parent("li") or a.find_parent("tr") or a.parent

        # 1. 제목 추출 (<strong class="title"> 또는 태그 내부 텍스트)
        title_el = a.select_one("strong.title, .title, strong")
        if title_el:
            title = title_el.get_text(strip=True)
        else:
            title = a.get_text(strip=True)

        if not title or len(title) < 2:
            continue

        # 2. 카테고리 추출
        cat_el = a.select_one(".category") or parent.select_one(".category")
        category = cat_el.get_text(strip=True) if cat_el else ""

        # 3. 날짜 추출
        date_el = a.select_one(".date") or parent.select_one(".date")
        date = date_el.get_text(strip=True) if date_el else "날짜 미상"

        # 4. 부서 추출
        dept_el = a.select_one(".department") or parent.select_one(".department")
        department = dept_el.get_text(strip=True) if dept_el else ""

        parsed_posts.append({
            "id": link,
            "title": title,
            "link": link,
            "date": date,
            "category": category,
            "department": department
        })

    print(f"[INFO] 파싱된 게시글 개수: {len(parsed_posts)}개")

    new_posts = [p for p in parsed_posts if p["id"] not in processed_ids]
    new_posts.reverse()  # 과거 순서부터 처리

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
