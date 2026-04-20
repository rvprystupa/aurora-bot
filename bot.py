import requests
import json
import time
import hashlib
import os
from datetime import datetime

TOKEN = "8508934165:AAFs0k-TTbVqZj1A892KukwzkOsqXRUs1MY"
CHAT_ID = "692099904"
CHECK_INTERVAL = 60
SEEN_FILE = "seen_vacancies.json"
SEARCH_URL = "https://api.robota.ua/vacancy/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://robota.ua",
    "Referer": "https://robota.ua/",
}

SEARCH_PAYLOAD = {
    "keyWords": "новий магазин",
    "page": 0,
    "count": 50,
    "sort": 0,
    "ukrainian": True,
    "period": 1,
}


def now():
    return datetime.now().strftime("%H:%M:%S")


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[{now()}] Telegram помилка: {e}")
        return False


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def is_aurora(v):
    company = str(v.get("companyName", "") or v.get("company", {}).get("name", "")).lower()
    return "аврора" in company or "aurora" in company


def has_new_store(v):
    text = " ".join([
        str(v.get("name", "")),
        str(v.get("title", "")),
        str(v.get("shortDescription", "")),
        str(v.get("description", "")),
    ]).lower()
    return any(kw in text for kw in ["новий магазин", "нового магазину", "нового магазина"])


def get_id(v):
    vid = str(v.get("id", "") or v.get("vacancyId", ""))
    if vid:
        return vid
    return hashlib.md5((str(v.get("name","")) + str(v.get("companyName","")) + str(v.get("cityName",""))).encode()).hexdigest()


def format_msg(v):
    vid = str(v.get("id", "") or v.get("vacancyId", ""))
    link = f"https://robota.ua/ua/vacancy/{vid}" if vid else "https://robota.ua/ua/company/3698/vacancies"
    city = v.get("cityName", "") or v.get("city", {}).get("name", "")
    salary = v.get("salary", "")
    published = v.get("publishedAt", v.get("datePosted", ""))
    parts = [
        "🆕 <b>Нова вакансія АВРОРА!</b>",
        f"📌 <b>{v.get('name', 'Без назви')}</b>",
        f"🏢 {v.get('companyName', 'Аврора')}",
    ]
    if city: parts.append(f"📍 {city}")
    if salary: parts.append(f"💰 {salary}")
    if published: parts.append(f"📅 {str(published)[:10]}")
    parts.append(f"🔗 <a href='{link}'>Переглянути вакансію</a>")
    parts.append(f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    return "\n".join(parts)


def fetch():
    try:
        r = requests.post(SEARCH_URL, headers=HEADERS, json=SEARCH_PAYLOAD, timeout=15)
        if r.status_code == 200:
            data = r.json()
            items = data.get("documents") or data.get("vacancies") or data.get("items") or []
            print(f"[{now()}] Отримано {len(items)} вакансій з API")
            return items
        print(f"[{now()}] HTTP {r.status_code}")
    except Exception as e:
        print(f"[{now()}] Помилка запиту: {e}")
    return []


def check(seen):
    items = fetch()
    sent = 0
    for v in items:
        vid = get_id(v)
        if vid in seen:
            continue
        seen.add(vid)
        if not is_aurora(v):
            continue
        if not has_new_store(v):
            print(f"[{now()}] Аврора (не 'новий магазин'): {v.get('name','')}")
            continue
        if send_telegram(format_msg(v)):
            print(f"[{now()}] ✅ НАДІСЛАНО: {v.get('name','')}")
            sent += 1
    return sent, len(items)


def main():
    print(f"[{now()}] 🤖 Бот запущено (v2 — виправлений фільтр)")
    send_telegram(
        "🤖 <b>Бот оновлено!</b>\n\n"
        "✅ Тільки вакансії <b>Аврора</b>\n"
        "✅ Тільки з 'новий магазин'\n"
        "✅ Сортування за датою\n"
        "⏱ Перевірка кожну хвилину"
    )

    seen = load_seen()
    print(f"[{now()}] Відомих вакансій: {len(seen)}")

    if len(seen) == 0:
        print(f"[{now()}] Перший запуск — зберігаємо поточні без надсилання")
        for v in fetch():
            seen.add(get_id(v))
        save_seen(seen)
        send_telegram(f"📋 Збережено {len(seen)} поточних вакансій. Чекаємо нових...")
        time.sleep(CHECK_INTERVAL)

    while True:
        try:
            sent, total = check(seen)
            save_seen(seen)
            if sent == 0:
                print(f"[{now()}] Нових немає (перевірено {total})")
        except Exception as e:
            print(f"[{now()}] Помилка: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()

