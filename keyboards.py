from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from config import REGIONS, CATEGORIES


def get_main_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="➕ Добавить мониторинг"),
            ],
            [
                KeyboardButton(text="📁 По категориям"),
                KeyboardButton(text="🎯 Ключ + категория"),
            ],
            [
                KeyboardButton(text="👤 Отслеживать продавца"),
                KeyboardButton(text="📋 Мои мониторинги"),
            ],
            [
                KeyboardButton(text="📢 Поделиться с другом"),
                KeyboardButton(text="⚙️ Настройки"),
            ],
            [
                KeyboardButton(text="⭐ Поддержать автора"),
            ],
        ],
        resize_keyboard=True,
    )


def get_share_kb(user_id: int) -> InlineKeyboardMarkup:
    import urllib.parse
    share_text = (
        "Привет! Нашел крутого бота для поиска квартир в Минске и товаров на Куфаре "
        "за 10 секунд до других (собирает Kufar + Onliner + Realt без агентов):"
    )
    encoded_text = urllib.parse.quote(share_text)
    share_url = f"https://t.me/kufar_radar_by_bot?start=ref_{user_id}"
    tg_share_link = f"https://t.me/share/url?url={share_url}&text={encoded_text}"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Отправить другу в Telegram",
                    url=tg_share_link,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Канал с квартирами в Минске",
                    url="https://t.me/minsk_rent_live",
                )
            ],
        ]
    )


def get_categories_wizard_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏠 Аренда квартир (Минск/РБ)", callback_data="wiz_cat:rent"),
            ],
            [
                InlineKeyboardButton(text="📱 Apple iPhone & Техника", callback_data="wiz_cat:apple"),
            ],
            [
                InlineKeyboardButton(text="🚗 Автомобили", callback_data="wiz_cat:auto"),
            ],
            [
                InlineKeyboardButton(text="💻 Компьютеры & Ноутбуки", callback_data="wiz_cat:pc"),
            ],
        ]
    )


def get_rent_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 Долгосрочная аренда", callback_data="rent_type:let"),
            ],
            [
                InlineKeyboardButton(text="🕒 Посуточная аренда", callback_data="rent_type:short"),
            ],
        ]
    )


def get_rent_rooms_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1-комнатная", callback_data="rent_rms:1"),
                InlineKeyboardButton(text="2-комнатная", callback_data="rent_rms:2"),
            ],
            [
                InlineKeyboardButton(text="3-комнатная", callback_data="rent_rms:3"),
                InlineKeyboardButton(text="4+ комнатная", callback_data="rent_rms:4,5"),
            ],
            [
                InlineKeyboardButton(text="🌟 1 или 2 комнатные (Хит)", callback_data="rent_rms:1,2"),
            ],
            [
                InlineKeyboardButton(text="Любое кол-во комнат", callback_data="rent_rms:all"),
            ],
        ]
    )


def get_rent_owner_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👤 Только собственники (Без комиссии)", callback_data="rent_own:1"),
            ],
            [
                InlineKeyboardButton(text="🏢 Все (включая агентства)", callback_data="rent_own:0"),
            ],
        ]
    )


def get_currency_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💵 В долларах ($)", callback_data="cur_choice:USD"),
                InlineKeyboardButton(text="🇧🇾 В рублях (BYN)", callback_data="cur_choice:BYN"),
            ]
        ]
    )


def get_apple_models_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="iPhone 15 / 15 Pro", callback_data="apple_mod:iPhone 15"),
                InlineKeyboardButton(text="iPhone 14 / 14 Pro", callback_data="apple_mod:iPhone 14"),
            ],
            [
                InlineKeyboardButton(text="iPhone 13 / 13 Pro", callback_data="apple_mod:iPhone 13"),
                InlineKeyboardButton(text="iPhone 11 / 12", callback_data="apple_mod:iPhone 11|12"),
            ],
            [
                InlineKeyboardButton(text="💻 Apple MacBook", callback_data="apple_mod:MacBook"),
                InlineKeyboardButton(text="🎧 AirPods", callback_data="apple_mod:AirPods"),
            ],
            [
                InlineKeyboardButton(text="🌟 Любой iPhone", callback_data="apple_mod:iPhone"),
            ],
        ]
    )


def get_regions_inline_kb() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for r_id, r_name in REGIONS.items():
        row.append(
            InlineKeyboardButton(
                text=r_name,
                callback_data=f"set_rgn:{r_id}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_my_tasks_kb(tasks: list) -> InlineKeyboardMarkup:
    """Генерирует инлайн-клавиатуру для единого сообщения 'Мои мониторинги'."""
    buttons = []

    # Кнопки с номерами задач
    if tasks:
        num_row = []
        for i, t in enumerate(tasks, 1):
            status = "🟢" if t["is_active"] else "⏸"
            num_row.append(
                InlineKeyboardButton(
                    text=f"{status} #{i}",
                    callback_data=f"view_task:{t['id']}",
                )
            )
            if len(num_row) == 4:
                buttons.append(num_row)
                num_row = []
        if num_row:
            buttons.append(num_row)

    # Кнопки массового управления
    buttons.append([
        InlineKeyboardButton(text="⏸ Стоп все", callback_data="tasks_all:stop"),
        InlineKeyboardButton(text="▶️ Запустить все", callback_data="tasks_all:start"),
    ])
    buttons.append([
        InlineKeyboardButton(text="➕ Добавить еще", callback_data="tasks_add_new"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_single_task_manage_kb(task_id: int, is_active: bool) -> InlineKeyboardMarkup:
    status_text = "⏸ Приостановить" if is_active else "▶️ Возобновить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=status_text, callback_data=f"toggle_task:{task_id}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_task:{task_id}"),
            ],
            [
                InlineKeyboardButton(text="◀️ Назад ко всем", callback_data="back_to_tasks"),
            ],
        ]
    )


def get_settings_kb(settings: dict, blocked_count: int = 0) -> InlineKeyboardMarkup:
    """Генерирует тумблеры настроек как на скриншоте 1."""
    photo_icon = "Вкл ✅" if settings.get("show_photo") else "Выкл ❌"
    desc_icon = "Вкл ✅" if settings.get("show_desc") else "Выкл ❌"
    smart_icon = "Вкл ✅" if settings.get("show_smart") else "Выкл ❌"
    sound_icon = "Со звуком 🔔" if settings.get("sound") else "Без звука 🔕"

    cur_val = settings.get("currency", "BOTH")
    cur_labels = {"BOTH": "Обе (BYN + $)", "BYN": "Только BYN", "USD": "Только USD ($)"}
    cur_text = cur_labels.get(cur_val, "Обе")

    buttons = [
        [
            InlineKeyboardButton(text=f"🖼 Фото в карточке: {photo_icon}", callback_data="set_toggle:show_photo"),
        ],
        [
            InlineKeyboardButton(text=f"📝 Цитата описания: {desc_icon}", callback_data="set_toggle:show_desc"),
        ],
        [
            InlineKeyboardButton(text=f"🔍 Анализ АКБ и нюансов: {smart_icon}", callback_data="set_toggle:show_smart"),
        ],
        [
            InlineKeyboardButton(text=f"💱 Валюта: {cur_text}", callback_data="set_toggle:currency"),
        ],
        [
            InlineKeyboardButton(text=f"🔔 Звук уведомлений: {sound_icon}", callback_data="set_toggle:sound"),
        ],
    ]

    if blocked_count > 0:
        buttons.append([
            InlineKeyboardButton(text=f"🚫 Скрытые продавцы: {blocked_count} (Сбросить)", callback_data="reset_blocked"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_stars_donate_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐ 50 Звёзд (~1.2 $)", callback_data="stars_pay:50"),
            ],
            [
                InlineKeyboardButton(text="⭐ 150 Звёзд (~3.5 $)", callback_data="stars_pay:150"),
            ],
            [
                InlineKeyboardButton(text="⭐ 300 Звёзд (~7 $)", callback_data="stars_pay:300"),
            ],
        ]
    )


def get_ad_card_kb(ad_url: str, seller_id: str = "") -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text="👉 Открыть на Куфаре",
                url=ad_url,
            )
        ]
    ]
    if seller_id and len(seller_id) > 4:
        buttons.append([
            InlineKeyboardButton(
                text="🚫 Скрыть продавца",
                callback_data=f"block_seller:{seller_id[:24]}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
