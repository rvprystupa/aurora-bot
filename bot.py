import requests
import json
import hashlib
import os
import re
from datetime import datetime

TOKEN = "8508934165:AAFs0k-TTbVqZj1A892KukwzkOsqXRUs1MY"
CHAT_ID = "692099904"
SEEN_FILE = "seen_vacancies.json"

# ID Аврори на robota.ua
AURORA_ID = 3698
AURORA_PAGE_URL = f"https://robota.ua/ua/company/{AURORA_ID}/vacancies"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def now():
    return datetime.now().strftime("%H:%M:%S")


def send_telegram(text):
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"Telegram помилка: {e}")
        return False


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


# ── Метод 1: HTML сторінка Аврори (бачимо в реальному часі) ──
def fetch_html():
    vacancies = []
    try:
        r = requests.get(AURORA_PAGE_URL, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"HTML: HTTP {r.status_code}")
            return vacancies

        html = r.text
        print(f"HTML розмір: {len(html)} байт")

        # Шукаємо JSON дані, вбудовані в сторінку (Next.js/Angular передають дані в <script>)
        # Робота.ua використовує Angular - шукаємо TransferState або прямі JSON блоки
        patterns = [
            r'"vacancies"\s*:\s*(\[.*?\])',
            r'"documents"\s*:\s*(\[.*?\])',
            r'"items"\s*:\s*(\[.*?\])',
            r'"totalCount".*?"documents"\s*:\s*(\[.*?\])',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, html, re.DOTALL)
            for m in matches:
                try:
                    items = json.loads(m)
                    if isinstance(items, list) and len(items) > 0:
                        # Перевіряємо що це схоже на вакансії
                        if any(k in items[0] for k in ['name', 'title', 'id', 'vacancyId']):
                            print(f"[HTML] Знайдено {len(items)} вакансій в JSON")
                            vacancies.extend(items)
                            break
                except Exception:
                    continue
            if vacancies:
                break

        # Fallback: парсимо HTML картки вакансій
        if not vacancies:
            # Шукаємо блоки з посиланнями на вакансії
            vacancy_links = re.findall(
                r'<a[^>]*href="/ua/vacancy/(\d+)"[^>]*>(.*?)</a>',
                html,
                re.DOTALL
            )
            for vid, title_html in vacancy_links[:50]:
                # Очищаємо HTML теги з назви
                title = re.sub(r'<[^>]+>', '', title_html).strip()
                if title:
                    vacancies.append({
                        "id": vid,
                        "name": title,
                        "companyName": "Аврора",
                        "_from_html": True,
                    })
            if vacancies:
                print(f"[HTML parse] Знайдено {len(vacancies)} вакансій")

    except Exception as e:
        print(f"HTML помилка: {e}")
    return vacancies


# ── Метод 2: API з cache-busting ──
def fetch_api_fresh():
    vacancies = []
    # Додаємо timestamp щоб обійти кеш
    ts = int(datetime.now().timestamp() * 1000)
    urls = [
        f"https://api.robota.ua/vacancy/search?_t={ts}",
        f"https://dracula.robota.ua/vacancies/search?_t={ts}",
    ]
    payload = {
        "companyIds": [AURORA_ID],
        "page": 0,
        "count": 100,
        "sort": 0,
        "period": 0,
        "ukrainian": True,
    }
    api_headers = {
        **HEADERS,
        "Content-Type": "application/json",
        "Origin": "https://robota.ua",
        "Referer": AURORA_PAGE_URL,
        "X-Requested-With": "XMLHttpRequest",
        "Cache-Control": "no-cache, no-store, must-revalidate",
    }
    for url in urls:
        try:
            r = requests.post(url, headers=api_headers, json=payload, timeout=15)
            if r.status_code == 200:
                data = r.json()
                items = data.get("documents") or data.get("vacancies") or data.get("items") or []
                if items:
                    print(f"[API {url.split('/')[2]}] {len(items)} вакансій")
                    vacancies.extend(items)
                    break
        except Exception as e:
            print(f"[API {url}] {e}")
    return vacancies


def get_id(v):
    vid = str(v.get("id", "") or v.get("vacancyId", ""))
    if vid:
        return vid
    key = str(v.get("name", "")) + str(v.get("companyName", ""))
    return hashlib.md5(key.encode()).hexdigest()


def has_new_store(v):
    text = " ".join([
        str(v.get("name", "")),
        str(v.get("title", "")),
        str(v.get("shortDescription", "")),
        str(v.get("description", "")),
    ]).lower()
    return any(kw in text for kw in [
        "новий магазин", "нового магазину", "нового магазина", "new store"
    ])


def is_aurora(v):
    if v.get("_from_html"):
        return True
    company = str(v.get("companyName", "") or v.get("company", {}).get("name", "")).lower()
    return "аврора" in company or "aurora" in company


def format_msg(v):
    vid = str(v.get("id", "") or v.get("vacancyId", ""))
    link = f"https://robota.ua/ua/vacancy/{vid}" if vid else AURORA_PAGE_URL
    city = v.get("cityName", "") or (v.get("city", {}) or {}).get("name", "")
    salary = v.get("salary", "")
    published = v.get("publishedAt", v.get("datePosted", ""))

    parts = [
        "🆕 <b>Нова вакансія АВРОРА!</b>",
        f"📌 <b>{v.get('name', 'Без назви')}</b>",
        f"🏢 Аврора",
    ]
    if city: parts.append(f"📍 {city}")
    if salary: parts.append(f"💰 {salary}")
    if published: parts.append(f"📅 {str(published)[:16].replace('T', ' ')}")
    parts.append(f"🔗 <a href='{link}'>Відкрити вакансію</a>")
    parts.append(f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    return "\n".join(parts)


def fetch_all():
    seen_ids = set()
    all_items = []
    for fn in [fetch_html, fetch_api_fresh]:
        try:
            for v in fn():
                vid = get_id(v)
                if vid not in seen_ids:
                    seen_ids.add(vid)
                    all_items.append(v)
        except Exception as e:
            print(f"Помилка методу: {e}")
    print(f"Всього унікальних: {len(all_items)}")
    return all_items


def main():
    print(f"[{now()}] Запуск v3 (HTML scraping)")
    seen = load_seen()
    first_run = len(seen) == 0
    items = fetch_all()
    sent = 0

    for v in items:
        vid = get_id(v)
        if first_run:
            seen.add(vid)
            continue
        if vid in seen:
            continue
        seen.add(vid)
        if not is_aurora(v):
            continue
        if not has_new_store(v):
            print(f"Аврора (без 'новий магазин'): {v.get('name', '')}")
            continue
        if send_telegram(format_msg(v)):
            print(f"✅ НАДІСЛАНО: {v.get('name', '')}")
            sent += 1

    save_seen(seen)

    if first_run:
        send_telegram(
            f"🤖 <b>Бот v3 активовано!</b>\n"
            f"📋 Збережено {len(seen)} поточних вакансій\n"
            f"🔍 Скануємо HTML сторінку напряму (без кешу API)"
        )
    else:
        print(f"Надіслано: {sent}")


if __name__ == "__main__":
    main()
