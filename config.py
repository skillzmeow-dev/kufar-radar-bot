import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))
DB_PATH = str(BASE_DIR / os.getenv("DB_NAME", "kufar_bot.db"))
ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "1462879969").split(",")
    if x.strip().isdigit()
]
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@minsk_rent_live").strip()

REGIONS = {
    7: "г. Минск",
    5: "Минская обл.",
    1: "Брестская обл.",
    6: "Витебская обл.",
    2: "Гомельская обл.",
    3: "Гродненская обл.",
    4: "Могилевская обл.",
    0: "Вся Беларусь",
}

CATEGORIES = {
    0: "Все категории",
    1010: "Аренда жилья (длительно)",
    17010: "Телефоны и смартфоны",
    16000: "Компьютеры и ноутбуки",
    2010: "Автомобили",
    15000: "Бытовая техника",
    8000: "Одежда и обувь",
}

PRESETS = [
    {
        "id": "preset_iphone",
        "title": "📱 iPhone (до 900 BYN)",
        "query": "iphone",
        "category_id": 17010,
        "region_id": 0,
        "min_price": 0,
        "max_price": 900,
        "only_owner": False,
    },
    {
        "id": "preset_rent_minsk",
        "title": "🏠 Аренда Минск (от собственника, до $350)",
        "query": "",
        "category_id": 1010,
        "region_id": 7,
        "min_price": 0,
        "max_price": 1150,  # ~350 USD
        "only_owner": True,
    },
    {
        "id": "preset_playstation",
        "title": "🎮 PlayStation 4/5 (до 1300 BYN)",
        "query": "playstation",
        "category_id": 0,
        "region_id": 0,
        "min_price": 0,
        "max_price": 1300,
        "only_owner": False,
    },
    {
        "id": "preset_macbook",
        "title": "💻 MacBook (до 1800 BYN)",
        "query": "macbook",
        "category_id": 16000,
        "region_id": 0,
        "min_price": 0,
        "max_price": 1800,
        "only_owner": False,
    },
]
