import asyncio
import json
import os
import hashlib
import re
from datetime import datetime
from playwright.async_api import async_playwright
import requests

TOKEN = "8508934165:AAFs0k-TTbVqZj1A892KukwzkOsqXRUs1MY"
CHAT_ID = "692099904"
AURORA_ID = 3698
AURORA_URL = f"https://robota.ua/ua/company/{AURORA_ID}/vacancies"
SEEN_FILE = "seen_vacancies.json"
CHECK_INTERVAL = 60  # секунд

KEYWORDS = [
    "новий магазин", "нового магазину", "нового магазина",
    "нова точка", "нової точки",
    "відкриття магазин", "відкритті магазин", "відкритт", 
    "новий магаз",
]


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
        print(f"[{now()}] Telegram: {e}")
        return False


def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_seen(seen):
    try:
        with open(SEEN_FILE, "w") as f:
            json.dump(list(seen), f)
    except Exception as e:
        print(f"[{now()}] Save error: {e}")


def has_keyword(title):
    t = title.lower()
    return any(kw in t for kw in KEYWORDS)


def format_msg(title, link, city=""):
    parts = [
        "🆕 <b>Нова вакансія АВРОРА!</b>",
        f"📌 <b>{title}</b>",
    ]
    if city:
        parts.append(f"📍 {city}")
    parts.append(f"🔗 <a href='{link}'>Відкрити вакансію</a>")
    parts.append(f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    return "\n".join(parts)


async def fetch_vacancies(page):
    """Парсимо сторінку Аврори через Playwright (JS рендериться)"""
    try:
        await page.goto(AURORA_URL, wait_until="networkidle", timeout=30000)
        # Чекаємо появи карток вакансій
        await page.wait_for_selector("a[href*='/vacancy/']", timeout=15000)
        
        # Витягуємо всі вакансії
        vacancies = await page.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll("a[href*='/vacancy/']"));
                const result = [];
                const seen = new Set();
                for (const a of links) {
                    const href = a.getAttribute('href');
                    const match = href.match(/\\/vacancy\\/(\\d+)/);
                    if (!match) continue;
                    const vid = match[1];
                    if (seen.has(vid)) continue;
                    seen.add(vid);
                    
                    // Шукаємо назву - в самій посилалці або в батьківському блоці
                    let title = a.innerText.trim();
                    if (!title || title.length < 5) {
                        const parent = a.closest('[class*="vacancy"]') || a.closest('article') || a.parentElement;
                        if (parent) title = parent.innerText.trim().split('\\n')[0];
                    }
                    
                    // Шукаємо місто
                    let city = '';
                    const parent = a.closest('[class*="vacancy"]') || a.closest('article') || a.parentElement;
                    if (parent) {
                        const text = parent.innerText;
                        const cityMatch = text.match(/[А-Яа-яЇїІіЄєҐґ\\s]+,\\s*вул/);
                        if (cityMatch) city = cityMatch[0].replace(/,\\s*вул.*/, '').trim();
                    }
                    
                    result.push({ id: vid, title: title, city: city, url: 'https://robota.ua' + href });
                }
                return result;
            }
        """)
        return vacancies
    except Exception as e:
        print(f"[{now()}] Fetch error: {e}")
        return []


async def check_loop():
    seen = load_seen()
    first_run = len(seen) == 0
    print(f"[{now()}] Старт. Відомих: {len(seen)}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="uk-UA",
        )
        page = await context.new_page()

        while True:
            try:
                vacancies = await fetch_vacancies(page)
                print(f"[{now()}] Отримано {len(vacancies)} вакансій")

                sent = 0
                for v in vacancies:
                    if v['id'] in seen:
                        continue
                    seen.add(v['id'])

                    if first_run:
                        continue

                    if not has_keyword(v['title']):
                        print(f"[{now()}] Не підходить: {v['title'][:60]}")
                        continue

                    if send_telegram(format_msg(v['title'], v['url'], v['city'])):
                        print(f"[{now()}] ✅ НАДІСЛАНО: {v['title'][:60]}")
                        sent += 1

                save_seen(seen)

                if first_run:
                    send_telegram(
                        f"🤖 <b>Бот активовано!</b>\n"
                        f"📋 Відстежується {len(seen)} вакансій\n"
                        f"⏱ Перевірка кожну хвилину\n"
                        f"🔍 Фільтр: новий магазин, відкриття магазину, нова точка"
                    )
                    first_run = False
                else:
                    print(f"[{now()}] Надіслано: {sent}")

            except Exception as e:
                print(f"[{now()}] Loop error: {e}")

            await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(check_loop())
