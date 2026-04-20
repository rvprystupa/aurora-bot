import requests
import json
import hashlib
import os
import xml.etree.ElementTree as ET
from datetime import datetime

TOKEN = "8508934165:AAFs0k-TTbVqZj1A892KukwzkOsqXRUs1MY"
CHAT_ID = "692099904"
SEEN_FILE = "seen_vacancies.json"

# Аврора на robota.ua має ID компанії 3698
AURORA_COMPANY_ID = 3698

HEADERS_BROWSER = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "uk-UA,uk;q=0.9",
    "Content-Type": "application/json",
    "Origin": "https://robota.ua",
    "Referer": "https://robota.ua/ua/company/3698/vacancies",
    "X-Requested-With": "XMLHttpRequest",
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

def get_id(v):
    vid = str(v.get("id", "") or v.get("vacancyId", ""))
    if vid:
        return vid
    key = str(v.get("name", "")) + str(v.get("companyName", "")) + str(v.get("cityName", ""))
    return hashlib.md5(key.encode()).hexdigest()

def has_new_store(v):
    text = " ".join([
        str(v.get("name", "")),
        str(v.get("title", "")),
        str(v.get("shortDescription", "")),
        str(v.get("description", "")),
    ]).lower()
    return any(kw in text for kw in [
        "новий магазин", "нового магазину", "нового магазина"
    ])

def format_msg(v):
    vid = str(v.get("id", "") or v.get("vacancyId", ""))
    link = f"https://robota.ua/ua/vacancy/{vid}" if vid else f"https://robota.ua/ua/company/{AURORA_COMPANY_ID}/vacancies"
    city = v.get("cityName", "") or v.get("city", {}).get("name", "")
    salary = v.get("salary", "")
    published = v.get("publishedAt", v.get("datePosted", ""))
    parts = [
        "🆕 <b>Нова вакансія АВРОРА!</b>",
        f"📌 <b>{v.get('name', 'Без назви')}</b>",
        f"🏢 Аврора",
    ]
    if city: parts.append(f"📍 {city}")
    if salary: parts.append(f"💰 {salary}")
    if published: parts.append(f"📅 Опубліковано: {str(published)[:16].replace('T',' ')}")
    parts.append(f"🔗 <a href='{link}'>Переглянути вакансію</a>")
    parts.append(f"⏰ Знайдено: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    return "\n".join(parts)


# ── МЕТОД 1: Сторінка компанії Аврора напряму ──────────────────────────────
def fetch_company_page():
    """Отримуємо вакансії зі сторінки компанії — найсвіжіші дані"""
    vacancies = []
    url = f"https://api.robota.ua/company/{AURORA_COMPANY_ID}/vacancies"
    try:
        r = requests.get(url, headers=HEADERS_BROWSER, timeout=15)
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else (
                data.get("vacancies") or data.get("documents") or data.get("items") or []
            )
            print(f"[Метод 1 - сторінка компанії] {len(items)} вакансій")
            vacancies.extend(items)
    except Exception as e:
        print(f"[Метод 1] помилка: {e}")
    return vacancies


# ── МЕТОД 2: Новий API endpoint з сортуванням ──────────────────────────────
def fetch_api_sorted():
    """Пошук через API з примусовим сортуванням за датою"""
    vacancies = []
    
    # Варіант A: POST з фільтром по компанії
    try:
        payload = {
            "companyIds": [AURORA_COMPANY_ID],
            "page": 0,
            "count": 100,
            "sort": 0,  # 0 = новіші першими
            "period": 0,  # всі
        }
        r = requests.post(
            "https://api.robota.ua/vacancy/search",
            headers=HEADERS_BROWSER,
            json=payload,
            timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            items = data.get("documents") or data.get("vacancies") or data.get("items") or []
            print(f"[Метод 2A - companyIds] {len(items)} вакансій")
            vacancies.extend(items)
    except Exception as e:
        print(f"[Метод 2A] помилка: {e}")

    # Варіант B: GET запит
    if not vacancies:
        try:
            r = requests.get(
                "https://api.robota.ua/vacancy/search",
                headers=HEADERS_BROWSER,
                params={
                    "companyId": AURORA_COMPANY_ID,
                    "page": 0,
                    "count": 100,
                    "sort": 0,
                },
                timeout=15
            )
            if r.status_code == 200:
                data = r.json()
                items = data.get("documents") or data.get("vacancies") or data.get("items") or []
                print(f"[Метод 2B - GET companyId] {len(items)} вакансій")
                vacancies.extend(items)
        except Exception as e:
            print(f"[Метод 2B] помилка: {e}")

    return vacancies


# ── МЕТОД 3: RSS стрічка ────────────────────────────────────────────────────
def fetch_rss():
    """RSS оновлюється в реальному часі — без кешування"""
    vacancies = []
    rss_urls = [
        f"https://robota.ua/rss/company/{AURORA_COMPANY_ID}",
        "https://robota.ua/rss/vacancies?keywords=аврора+новий+магазин",
        f"https://robota.ua/ua/company/{AURORA_COMPANY_ID}/rss",
    ]
    for url in rss_urls:
        try:
            r = requests.get(url, headers={"User-Agent": HEADERS_BROWSER["User-Agent"]}, timeout=10)
            if r.status_code == 200 and "<rss" in r.text.lower():
                root = ET.fromstring(r.text)
                items = root.findall(".//item")
                print(f"[Метод 3 - RSS] {len(items)} вакансій з {url}")
                for item in items:
                    title = item.findtext("title", "")
                    link = item.findtext("link", "")
                    pub_date = item.findtext("pubDate", "")
                    vid = hashlib.md5(link.encode()).hexdigest()
                    vacancies.append({
                        "id": vid,
                        "name": title,
                        "companyName": "Аврора",
                        "link": link,
                        "publishedAt": pub_date,
                        "_from_rss": True,
                    })
                break
        except Exception as e:
            print(f"[Метод 3 RSS {url}] помилка: {e}")
    return vacancies


def fetch_all():
    """Пробуємо всі методи, об'єднуємо результати"""
    seen_ids = set()
    all_vacancies = []

    for fetch_fn in [fetch_company_page, fetch_api_sorted, fetch_rss]:
        try:
            items = fetch_fn()
            for v in items:
                vid = get_id(v)
                if vid not in seen_ids:
                    seen_ids.add(vid)
                    all_vacancies.append(v)
        except Exception as e:
            print(f"Помилка методу: {e}")

    print(f"Всього унікальних вакансій Аврори: {len(all_vacancies)}")
    return all_vacancies


def main():
    print(f"[{now()}] Запуск перевірки (пряме сканування сторінки Аврори)")
    seen = load_seen()
    print(f"[{now()}] Відомих вакансій: {len(seen)}")
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

        if not has_new_store(v):
            print(f"Аврора (не 'новий магазин'): {v.get('name', '')}")
            continue

        if send_telegram(format_msg(v)):
            print(f"✅ НАДІСЛАНО: {v.get('name', '')}")
            sent += 1

    save_seen(seen)

    if first_run:
        send_telegram(
            f"🤖 <b>Бот активовано!</b>\n"
            f"📋 Збережено {len(seen)} поточних вакансій Аврори\n"
            f"Слідкую за новими з 'новий магазин' ⏱\n"
            f"Перевірка кожні 5 хвилин"
        )
        print(f"Перший запуск: збережено {len(seen)} вакансій")
    else:
        print(f"Надіслано: {sent} | Перевірено: {len(items)}")


if __name__ == "__main__":
    main()

