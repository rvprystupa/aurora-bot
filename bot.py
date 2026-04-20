import requests
import json
import time
import hashlib
import os
from datetime import datetime

TOKEN = "8508934165:AAFs0k-TTbVqZj1A892KukwzkOsqXRUs1MY"
CHAT_ID = "692099904"
CHECK_INTERVAL = 60  # секунд
SEEN_FILE = "seen_vacancies.json"

SEARCH_URL = "https://api.robota.ua/vacancy/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://robota.ua",
    "Referer": "https://robota.ua/",
}
SEARCH_PAYLOAD = {
    "keyWords": "новий магазин",
    "companyIds": [],
    "employerName": "Аврора",
    "page": 0,
    "count": 20,
    "ukrainian": True,
}


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[{now()}] Помилка Telegram: {e}")
        return False


def now():
    return datetime.now().strftime("%H:%M:%S")


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def fetch_vacancies():
    try:
        resp = requests.post(
            SEARCH_URL,
            headers=HEADERS,
            json=SEARCH_PAYLOAD,
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("documents", []) or data.get("vacancies", []) or []
        else:
            print(f"[{now()}] HTTP {resp.status_code}")
            return []
    except Exception as e:
        print(f"[{now()}] Помилка запиту: {e}")
        return []


def format_vacancy(v):
    title = v.get("name", v.get("title", "Без назви"))
    company = v.get("companyName", v.get("company", {}).get("name", "Аврора"))
    city = v.get("cityName", v.get("city", {}).get("name", ""))
    salary = v.get("salary", "")
    vacancy_id = str(v.get("id", v.get("vacancyId", "")))
    link = f"https://robota.ua/ua/vacancy/{vacancy_id}" if vacancy_id else "https://robota.ua"

    parts = [
        f"🆕 <b>Нова вакансія Аврора!</b>",
        f"📌 <b>{title}</b>",
        f"🏢 {company}",
    ]
    if city:
        parts.append(f"📍 {city}")
    if salary:
        parts.append(f"💰 {salary}")
    parts.append(f"🔗 <a href='{link}'>Переглянути вакансію</a>")
    parts.append(f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    return "\n".join(parts)


def get_vacancy_id(v):
    vid = str(v.get("id", v.get("vacancyId", "")))
    if vid:
        return vid
    # Якщо немає id — хешуємо назву+місто
    key = str(v.get("name", "")) + str(v.get("cityName", ""))
    return hashlib.md5(key.encode()).hexdigest()


def check_vacancies(seen):
    vacancies = fetch_vacancies()
    new_count = 0

    for v in vacancies:
        vid = get_vacancy_id(v)
        if vid not in seen:
            title = v.get("name", v.get("title", "")).lower()
            # Додаткова перевірка на "новий магазин" якщо API повернув зайве
            if "новий магазин" in title or "новий магазин" in str(v).lower():
                msg = format_vacancy(v)
                if send_telegram(msg):
                    print(f"[{now()}] ✅ Надіслано: {v.get('name', vid)}")
                seen.add(vid)
                new_count += 1
            else:
                # Зберігаємо щоб не перевіряти знову
                seen.add(vid)

    return new_count


def main():
    print(f"[{now()}] 🤖 Бот запущено. Перевірка кожні {CHECK_INTERVAL} сек.")
    print(f"[{now()}] Шукаємо: Аврора + 'новий магазин'")

    send_telegram(
        "🤖 <b>Бот запущено!</b>\n"
        "Слідкую за вакансіями <b>Аврора</b> з 'новий магазин'\n"
        f"⏱ Перевірка кожну хвилину"
    )

    seen = load_seen()
    print(f"[{now()}] Завантажено {len(seen)} відомих вакансій")

    while True:
        try:
            new = check_vacancies(seen)
            save_seen(seen)
            if new == 0:
                print(f"[{now()}] Нових вакансій немає ({len(seen)} відомих)")
        except Exception as e:
            print(f"[{now()}] Помилка циклу: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
