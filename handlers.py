import logging
import re
from aiogram import Router, F, Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    PreCheckoutQuery,
    LabeledPrice,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import CommandStart, CommandObject, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import Database
from config import REGIONS, CATEGORIES
from keyboards import (
    get_main_reply_kb,
    get_categories_wizard_kb,
    get_rent_type_kb,
    get_rent_rooms_kb,
    get_rent_owner_kb,
    get_currency_choice_kb,
    get_apple_models_kb,
    get_regions_inline_kb,
    get_my_tasks_kb,
    get_single_task_manage_kb,
    get_settings_kb,
    get_stars_donate_kb,
    get_share_kb,
)

logger = logging.getLogger(__name__)
router = Router()

MENU_BUTTONS = {
    "➕ Добавить мониторинг",
    "📁 По категориям",
    "🎯 Ключ + категория",
    "👤 Отслеживать продавца",
    "📋 Мои мониторинги",
    "📢 Поделиться с другом",
    "⚙️ Настройки",
    "⭐ Поддержать автора",
}


# FSM состояния
class ManualSearchFSM(StatesGroup):
    waiting_for_query = State()
    waiting_for_cat = State()
    waiting_for_rgn = State()
    waiting_for_cur = State()
    waiting_for_price = State()


class RentWizardFSM(StatesGroup):
    waiting_for_type = State()
    waiting_for_rooms = State()
    waiting_for_owner = State()
    waiting_for_rgn = State()
    waiting_for_cur = State()
    waiting_for_price = State()


class AppleWizardFSM(StatesGroup):
    waiting_for_model = State()
    waiting_for_rgn = State()
    waiting_for_cur = State()
    waiting_for_price = State()


class SellerTrackFSM(StatesGroup):
    waiting_for_url = State()


# ------------------- ПРИВЕТСТВИЕ -------------------
@router.message(CommandStart(), StateFilter("*"))
async def cmd_start(message: Message, command: CommandObject, db: Database, state: FSMContext):
    await state.clear()
    user = message.from_user
    await db.add_user(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name or "Пользователь",
    )

    # При переходе из канала аренды (по диплинку ?start=channel_minsk или rent)
    if command.args and any(x in command.args.lower() for x in ("channel", "rent")):
        rent_welcome = (
            f"👋 <b>Радар аренды в Минске подключён, {user.first_name}!</b>\n\n"
            "Я собираю объявления об аренде с <b>Kufar, Realt и Onliner</b> в одном месте.\n\n"
            "Осталось настроить фильтры: укажите цену и количество комнат, "
            "и я начну присылать подходящие варианты от собственников в личные сообщения "
            "за <b>10–15 секунд</b> до того, как их увидят другие!\n\n"
            "👇 <i>Нажмите кнопку ниже для настройки:</i>"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎯 Настроить фильтры аренды",
                        callback_data="wiz_cat:rent",
                    )
                ]
            ]
        )
        await message.answer(rent_welcome, parse_mode="HTML", reply_markup=get_main_reply_kb())
        await message.answer("Готовы настроить параметры поиска?", reply_markup=kb)
        return

    welcome_text = (
        f"🎯 <b>Добро пожаловать в Куфар Радар, {user.first_name}!</b>\n\n"
        "Я непрерывно сканирую базу Куфара и моментально перехватываю новые лоты "
        "за <b>10–15 секунд</b> после публикации.\n\n"
        "⚡ <b>Как начать поиск:</b>\n"
        "• <b>📁 По категориям</b> — пошаговый подбор (Аренда квартир, iPhone, Авто)\n"
        "• <b>🎯 Ключ + категория</b> — любой ручной запрос с фильтрами цен\n"
        "• <b>👤 Отслеживать продавца</b> — ловить новинки конкретного профиля\n"
        "• <b>📋 Мои мониторинги</b> — список ваших активных задач\n\n"
        "<i>Используйте кнопки меню внизу экрана для управления:</i>"
    )
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_reply_kb())


# ------------------- ЕДИНОЕ СООБЩЕНИЕ 'МОИ МОНИТОРИНГИ' -------------------
async def render_my_tasks_message(user_id: int, db: Database) -> tuple[str, any]:
    tasks = await db.get_user_tasks(user_id)
    if not tasks:
        text = (
            "📋 <b>Ваши мониторинги:</b>\n\n"
            "У вас пока нет активных отслеживаний.\n"
            "Нажмите <b>📁 По категориям</b> или <b>🎯 Ключ + категория</b>, чтобы запустить радар!"
        )
        return text, get_my_tasks_kb([])

    active_cnt = sum(1 for t in tasks if t["is_active"])
    text_lines = [
        f"📋 <b>Ваши мониторинги (Всего: {len(tasks)} | Активно: {active_cnt}):</b>\n"
    ]

    for i, t in enumerate(tasks, 1):
        status = "🟢" if t["is_active"] else "⏸"
        cur = t.get("currency", "BYN")
        price_str = ""
        if t["max_price"]:
            price_str = f" • до {t['max_price']} {cur}"
        elif t["min_price"]:
            price_str = f" • от {t['min_price']} {cur}"

        owner_tag = " • [Собственник]" if t["only_owner"] else ""
        text_lines.append(f"<b>#{i}</b> {status} <b>{t['title']}</b>{price_str}{owner_tag}")

    text_lines.append("\n<i>Нажмите на номер ниже для управления конкретным поиском:</i>")
    return "\n".join(text_lines), get_my_tasks_kb(tasks)


@router.message(F.text == "📋 Мои мониторинги", StateFilter("*"))
async def show_my_tasks(message: Message, db: Database, state: FSMContext):
    await state.clear()
    text, kb = await render_my_tasks_message(message.from_user.id, db)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "back_to_tasks")
async def back_to_tasks_cb(callback: CallbackQuery, db: Database):
    text, kb = await render_my_tasks_message(callback.from_user.id, db)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("view_task:"))
async def view_single_task_cb(callback: CallbackQuery, db: Database):
    task_id = int(callback.data.split(":")[1])
    task = await db.get_task_by_id(task_id, callback.from_user.id)
    if not task:
        await callback.answer("Поиск не найден", show_alert=True)
        return

    status = "🟢 Активен (радар работает)" if task["is_active"] else "⏸ Приостановлен"
    reg = REGIONS.get(task["region_id"], "Вся Беларусь")
    cur = task.get("currency", "BYN")

    details = (
        f"🎯 <b>Параметры поиска #{task['id']}:</b>\n\n"
        f"📌 <b>Название:</b> {task['title']}\n"
        f"📊 <b>Статус:</b> {status}\n"
        f"🔎 <b>Ключ:</b> <code>{task['query'] or 'без слова'}</code>\n"
        f"📍 <b>Регион:</b> {reg}\n"
        f"💰 <b>Бюджет:</b> {task['min_price']} - {task['max_price']} {cur}\n"
        f"🚪 <b>Комнаты:</b> {task.get('rooms') or 'любое'}\n"
        f"👤 <b>Только собственники:</b> {'Да' if task['only_owner'] else 'Нет'}\n"
    )
    await callback.message.edit_text(
        details,
        parse_mode="HTML",
        reply_markup=get_single_task_manage_kb(task_id, bool(task["is_active"])),
    )


@router.callback_query(F.data.startswith("toggle_task:"))
async def toggle_single_task_cb(callback: CallbackQuery, db: Database):
    task_id = int(callback.data.split(":")[1])
    res = await db.toggle_task(task_id, callback.from_user.id)
    if res is None:
        await callback.answer("Ошибка", show_alert=True)
        return
    status_str = "возобновлен ▶️" if res else "приостановлен ⏸"
    await callback.answer(f"Поиск {status_str}")
    await view_single_task_cb(callback, db)


@router.callback_query(F.data.startswith("del_task:"))
async def del_single_task_cb(callback: CallbackQuery, db: Database):
    task_id = int(callback.data.split(":")[1])
    await db.delete_task(task_id, callback.from_user.id)
    await callback.answer("🗑 Поиск удален")
    text, kb = await render_my_tasks_message(callback.from_user.id, db)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("tasks_all:"))
async def tasks_all_cb(callback: CallbackQuery, db: Database):
    action = callback.data.split(":")[1]
    activate = action == "start"
    await db.toggle_all_tasks(callback.from_user.id, activate)
    await callback.answer("Все задачи обновлены")
    text, kb = await render_my_tasks_message(callback.from_user.id, db)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


# ------------------- 📁 ВОРОНКА ПО КАТЕГОРИЯМ -------------------
@router.message(F.text.in_(["📁 По категориям", "➕ Добавить мониторинг"]), StateFilter("*"))
@router.callback_query(F.data == "tasks_add_new")
async def start_category_wizard(event: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "📁 <b>Выберите категорию для настройки мониторинга:</b>\n\n"
        "Мы собрали точные фильтры для самых прибыльных и востребованных ниш:"
    )
    if isinstance(event, CallbackQuery):
        await event.message.answer(text, parse_mode="HTML", reply_markup=get_categories_wizard_kb())
        await event.answer()
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=get_categories_wizard_kb())


# ВЕТКА: АРЕНДА КВАРТИР
@router.callback_query(F.data == "wiz_cat:rent")
async def rent_step_1(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(RentWizardFSM.waiting_for_type)
    text = "🔑 <b>Аренда жилья:</b>\n\nВыберите тип аренды:"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_rent_type_kb())


@router.callback_query(RentWizardFSM.waiting_for_type, F.data.startswith("rent_type:"))
async def rent_step_2(callback: CallbackQuery, state: FSMContext):
    rent_type = callback.data.split(":")[1]
    await state.update_data(rent_type=rent_type)
    await state.set_state(RentWizardFSM.waiting_for_rooms)
    text = "🚪 <b>Укажите количество комнат:</b>"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_rent_rooms_kb())


@router.callback_query(RentWizardFSM.waiting_for_rooms, F.data.startswith("rent_rms:"))
async def rent_step_3(callback: CallbackQuery, state: FSMContext):
    rms = callback.data.split(":")[1]
    rooms_val = "" if rms == "all" else rms
    await state.update_data(rooms=rooms_val)
    await state.set_state(RentWizardFSM.waiting_for_owner)
    text = "👥 <b>Кто сдает:</b>"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_rent_owner_kb())


@router.callback_query(RentWizardFSM.waiting_for_owner, F.data.startswith("rent_own:"))
async def rent_step_4(callback: CallbackQuery, state: FSMContext):
    only_owner = callback.data.split(":")[1] == "1"
    await state.update_data(only_owner=only_owner)
    await state.set_state(RentWizardFSM.waiting_for_rgn)
    text = "📍 <b>Выберите город или область:</b>"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_regions_inline_kb())


@router.callback_query(RentWizardFSM.waiting_for_rgn, F.data.startswith("set_rgn:"))
async def rent_step_5(callback: CallbackQuery, state: FSMContext):
    rgn_id = int(callback.data.split(":")[1])
    await state.update_data(region_id=rgn_id)
    await state.set_state(RentWizardFSM.waiting_for_cur)
    text = "💱 <b>В какой валюте вам удобнее указать бюджет?</b>"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_currency_choice_kb())


@router.callback_query(RentWizardFSM.waiting_for_cur, F.data.startswith("cur_choice:"))
async def rent_step_6(callback: CallbackQuery, state: FSMContext):
    cur = callback.data.split(":")[1]
    await state.update_data(currency=cur)
    await state.set_state(RentWizardFSM.waiting_for_price)
    sign = "$" if cur == "USD" else "BYN"
    text = (
        f"💰 <b>Максимальная стоимость аренды (в {sign}):</b>\n\n"
        f"Напишите сумму (например: <code>350</code> или <code>500</code>)\n"
        f"<i>Или отправьте 0, если ограничений нет</i>"
    )
    await callback.message.edit_text(text, parse_mode="HTML")


@router.message(RentWizardFSM.waiting_for_price)
async def rent_finish(message: Message, state: FSMContext, db: Database):
    if message.text in MENU_BUTTONS:
        await state.clear()
        return
    raw = re.sub(r"\D", "", message.text)
    max_p = int(raw) if raw else 0
    data = await state.get_data()
    await state.clear()

    cur = data.get("currency", "USD")
    rms = data.get("rooms", "")
    rgn_id = data.get("region_id", 7)
    only_owner = data.get("only_owner", True)

    rooms_label = f"{rms}-комн. " if rms else ""
    title = f"Аренда: {rooms_label}{REGIONS.get(rgn_id, 'Минск')}"
    if max_p:
        title += f" (до {max_p} {cur})"

    await db.add_task(
        user_id=message.from_user.id,
        title=title,
        query="",
        category_id=1010,
        region_id=rgn_id,
        min_price=0,
        max_price=max_p,
        currency=cur,
        rooms=rms,
        only_owner=only_owner,
    )

    await message.answer(
        f"🎉 <b>Мониторинг аренды запущен!</b>\n\n"
        f"🎯 <b>{title}</b>\n"
        f"👤 Только собственники: {'Да' if only_owner else 'Все'}\n\n"
        f"Бот уведомит вас о новых объявлениях за секунды!",
        parse_mode="HTML",
        reply_markup=get_main_reply_kb(),
    )


# ВЕТКА: APPLE ТЕХНИКА
@router.callback_query(F.data == "wiz_cat:apple")
async def apple_step_1(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AppleWizardFSM.waiting_for_model)
    text = "🍏 <b>Мониторинг Apple техники:</b>\n\nВыберите модель устройства:"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_apple_models_kb())


@router.callback_query(AppleWizardFSM.waiting_for_model, F.data.startswith("apple_mod:"))
async def apple_step_2(callback: CallbackQuery, state: FSMContext):
    model = callback.data.split(":")[1]
    await state.update_data(model=model)
    await state.set_state(AppleWizardFSM.waiting_for_rgn)
    text = "📍 <b>Выберите регион поиска:</b>"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_regions_inline_kb())


@router.callback_query(AppleWizardFSM.waiting_for_rgn, F.data.startswith("set_rgn:"))
async def apple_step_3(callback: CallbackQuery, state: FSMContext):
    rgn_id = int(callback.data.split(":")[1])
    await state.update_data(region_id=rgn_id)
    await state.set_state(AppleWizardFSM.waiting_for_cur)
    text = "💱 <b>В какой валюте указать предельную цену?</b>"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_currency_choice_kb())


@router.callback_query(AppleWizardFSM.waiting_for_cur, F.data.startswith("cur_choice:"))
async def apple_step_4(callback: CallbackQuery, state: FSMContext):
    cur = callback.data.split(":")[1]
    await state.update_data(currency=cur)
    await state.set_state(AppleWizardFSM.waiting_for_price)
    sign = "$" if cur == "USD" else "BYN"
    text = (
        f"💰 <b>Максимальная цена покупки (в {sign}):</b>\n\n"
        f"Напишите сумму (например: <code>1500</code>)\n"
        f"<i>Или отправьте 0, если цена не важна</i>"
    )
    await callback.message.edit_text(text, parse_mode="HTML")


@router.message(AppleWizardFSM.waiting_for_price)
async def apple_finish(message: Message, state: FSMContext, db: Database):
    if message.text in MENU_BUTTONS:
        await state.clear()
        return
    raw = re.sub(r"\D", "", message.text)
    max_p = int(raw) if raw else 0
    data = await state.get_data()
    await state.clear()

    model = data.get("model", "iPhone")
    cur = data.get("currency", "BYN")
    rgn_id = data.get("region_id", 0)

    title = f"{model}"
    if max_p:
        title += f" (до {max_p} {cur})"

    await db.add_task(
        user_id=message.from_user.id,
        title=title,
        query=model if "|" not in model else "",
        category_id=17010 if "iPhone" in model else 16000,
        region_id=rgn_id,
        min_price=0,
        max_price=max_p,
        currency=cur,
        only_owner=False,
    )

    await message.answer(
        f"🎉 <b>Радар на технику запущен!</b>\n\n"
        f"🎯 <b>{title}</b>\n"
        f"📍 Регион: {REGIONS.get(rgn_id, 'Вся Беларусь')}\n"
        f"Мы будем выцеплять самые сочные предложения с АКБ и состоянием!",
        parse_mode="HTML",
        reply_markup=get_main_reply_kb(),
    )


# ------------------- 👤 ОТСЛЕЖИВАНИЕ ПРОДАВЦА -------------------
@router.message(F.text == "👤 Отслеживать продавца", StateFilter("*"))
async def start_seller_track(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(SellerTrackFSM.waiting_for_url)
    text = (
        "👤 <b>Отслеживание конкретного продавца на Куфаре:</b>\n\n"
        "Отправьте ссылку на профиль продавца (например:\n"
        "<code>https://www.kufar.by/user/O0wAEmhP6uqheO4mMwozAyc</code>)\n\n"
        "<i>Или просто отправьте его ID из ссылки.</i>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(SellerTrackFSM.waiting_for_url)
async def process_seller_url(message: Message, state: FSMContext, db: Database):
    if message.text in MENU_BUTTONS:
        await state.clear()
        return
    text = message.text.strip()
    match = re.search(r"user/([A-Za-z0-9_-]+)", text)
    if match:
        seller_id = match.group(1)
    else:
        seller_id = text.split("/")[-1].split("?")[0]

    if len(seller_id) < 5:
        await message.answer("❌ Неверный формат ссылки. Попробуйте еще раз.")
        return

    await state.clear()
    title = f"Продавец: {seller_id[:12]}..."
    await db.add_task(
        user_id=message.from_user.id,
        title=title,
        seller_id=seller_id,
    )

    await message.answer(
        f"✅ <b>Продавец добавлен в радар!</b>\n\n"
        f"🎯 ID: <code>{seller_id}</code>\n"
        f"Как только он выложит любой новый товар, вы первым получите уведомление!",
        parse_mode="HTML",
        reply_markup=get_main_reply_kb(),
    )


# ------------------- 🎯 КЛЮЧ + КАТЕГОРИЯ (РУЧНОЙ ПОИСК) -------------------
@router.message(F.text == "🎯 Ключ + категория", StateFilter("*"))
async def start_manual_search(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ManualSearchFSM.waiting_for_query)
    text = (
        "🎯 <b>Ручной поиск по ключевому слову:</b>\n\n"
        "Напишите, что именно вы ищете (например: <code>RTX 4070</code> или <code>коляска Anex</code>):"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(ManualSearchFSM.waiting_for_query)
async def manual_step_2(message: Message, state: FSMContext):
    if message.text in MENU_BUTTONS:
        await state.clear()
        return
    query = message.text.strip()
    await state.update_data(query=query)
    await state.set_state(ManualSearchFSM.waiting_for_rgn)
    text = f"📍 Запрос: <b>{query}</b>\n\nВыберите регион поиска:"
    await message.answer(text, parse_mode="HTML", reply_markup=get_regions_inline_kb())


@router.callback_query(ManualSearchFSM.waiting_for_rgn, F.data.startswith("set_rgn:"))
async def manual_step_3(callback: CallbackQuery, state: FSMContext):
    rgn_id = int(callback.data.split(":")[1])
    await state.update_data(region_id=rgn_id)
    await state.set_state(ManualSearchFSM.waiting_for_cur)
    text = "💱 <b>Выберите валюту:</b>"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_currency_choice_kb())


@router.callback_query(ManualSearchFSM.waiting_for_cur, F.data.startswith("cur_choice:"))
async def manual_step_4(callback: CallbackQuery, state: FSMContext):
    cur = callback.data.split(":")[1]
    await state.update_data(currency=cur)
    await state.set_state(ManualSearchFSM.waiting_for_price)
    sign = "$" if cur == "USD" else "BYN"
    text = f"💰 <b>Максимальная цена (в {sign}):</b>\n\nОтправьте число или 0 (без ограничений):"
    await callback.message.edit_text(text, parse_mode="HTML")


@router.message(ManualSearchFSM.waiting_for_price)
async def manual_finish(message: Message, state: FSMContext, db: Database):
    if message.text in MENU_BUTTONS:
        await state.clear()
        return
    raw = re.sub(r"\D", "", message.text)
    max_p = int(raw) if raw else 0
    data = await state.get_data()
    await state.clear()

    query = data.get("query", "")
    rgn_id = data.get("region_id", 0)
    cur = data.get("currency", "BYN")

    title = query
    if max_p:
        title += f" (до {max_p} {cur})"

    await db.add_task(
        user_id=message.from_user.id,
        title=title,
        query=query,
        region_id=rgn_id,
        min_price=0,
        max_price=max_p,
        currency=cur,
    )

    await message.answer(
        f"✅ <b>Мониторинг запущен:</b> <code>{title}</code>\n"
        f"📍 Регион: {REGIONS.get(rgn_id, 'Вся Беларусь')}",
        parse_mode="HTML",
        reply_markup=get_main_reply_kb(),
    )


# ------------------- ⚙️ НАСТРОЙКИ УВЕДОМЛЕНИЙ (СКРИНШОТ 1) -------------------
@router.message(F.text == "⚙️ Настройки", StateFilter("*"))
async def show_settings(message: Message, db: Database, state: FSMContext):
    await state.clear()
    settings = await db.get_user_settings(message.from_user.id)
    blocked_cnt = await db.get_blocked_sellers_count(message.from_user.id)
    text = (
        "⚙️ <b>Настройки уведомлений</b>\n"
        "<i>Относятся ко всем вашим мониторингам:</i>\n\n"
        "Нажимайте на кнопки, чтобы включать или отключать нужные опции:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_settings_kb(settings, blocked_cnt))


@router.callback_query(F.data.startswith("set_toggle:"))
async def toggle_setting_cb(callback: CallbackQuery, db: Database):
    setting_name = callback.data.split(":")[1]
    await db.toggle_setting(callback.from_user.id, setting_name)
    settings = await db.get_user_settings(callback.from_user.id)
    blocked_cnt = await db.get_blocked_sellers_count(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=get_settings_kb(settings, blocked_cnt))
    await callback.answer("Настройка обновлена")


@router.callback_query(F.data.startswith("block_seller:"))
async def block_seller_cb(callback: CallbackQuery, db: Database):
    seller_id = callback.data.split(":")[1]
    await db.block_seller(callback.from_user.id, seller_id)
    await callback.answer("🚫 Продавец скрыт! Вы больше не получите от него объявлений.", show_alert=True)


@router.callback_query(F.data == "reset_blocked")
async def reset_blocked_cb(callback: CallbackQuery, db: Database):
    cnt = await db.clear_blocked_sellers(callback.from_user.id)
    await callback.answer(f"Сброшено {cnt} скрытых продавцов", show_alert=True)
    settings = await db.get_user_settings(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=get_settings_kb(settings, 0))


# ------------------- 🔗 РАСПОЗНАВАНИЕ ССЫЛОК С KUFAR.BY -------------------
import urllib.parse

def parse_kufar_url(url_str: str) -> dict:
    parsed = urllib.parse.urlparse(url_str)
    qs = urllib.parse.parse_qs(parsed.query)
    path = parsed.path.lower()
    netloc = parsed.netloc.lower()

    # 1. Ссылка на пользователя
    if "/user/" in path:
        seller_id = path.split("/user/")[-1].split("/")[0].split("?")[0]
        return {"type": "seller", "seller_id": seller_id}

    # 2. Категория
    category_id = 0
    if "re.kufar.by" in netloc or "snyat/kvartiru" in path or "arenda" in path:
        category_id = 1010
    elif "auto.kufar.by" in netloc or "avtomobil" in path:
        category_id = 2010
    elif "cat" in qs:
        try:
            category_id = int(qs["cat"][0])
        except Exception:
            category_id = 0

    # 3. Регион по URL
    region_id = 0
    if "minsk" in path or qs.get("rgn") == ["7"]:
        region_id = 7
    elif "brest" in path or qs.get("rgn") == ["1"]:
        region_id = 1
    elif "vitebsk" in path or qs.get("rgn") == ["6"]:
        region_id = 6
    elif "gomel" in path or qs.get("rgn") == ["2"]:
        region_id = 2
    elif "grodno" in path or qs.get("rgn") == ["3"]:
        region_id = 3
    elif "mogilev" in path or qs.get("rgn") == ["4"]:
        region_id = 4

    # 4. Цены
    min_p, max_p = 0, 0
    if "prc" in qs:
        m = re.search(r"r:(\d*),(\d*)", qs["prc"][0])
        if m:
            min_p = int(m.group(1)) if m.group(1) else 0
            max_p = int(m.group(2)) if m.group(2) else 0
            # Если цена передана в копейках (>1000)
            if min_p > 1000:
                min_p //= 100
            if max_p > 1000:
                max_p //= 100

    cur = qs.get("cur", ["BYN"])[0].upper()
    query = qs.get("query", [""])[0] or qs.get("ot", [""])[0]
    rooms = qs.get("rms", [""])[0].replace("v.or:", "")
    only_owner = qs.get("cmp", [""])[0] == "0"

    title_parts = []
    if query:
        title_parts.append(query)
    elif category_id == 1010:
        rooms_lbl = f"{rooms}-комн. " if rooms else ""
        title_parts.append(f"Аренда {rooms_lbl}{REGIONS.get(region_id, 'Минск')}")
    elif category_id == 2010:
        title_parts.append("Авто")
    else:
        title_parts.append("Поиск по ссылке")

    if max_p:
        title_parts.append(f"(до {max_p} {cur})")

    return {
        "type": "search",
        "title": " ".join(title_parts),
        "query": query,
        "category_id": category_id,
        "region_id": region_id,
        "min_price": min_p,
        "max_price": max_p,
        "currency": cur,
        "rooms": rooms,
        "only_owner": only_owner,
    }


@router.message(F.text.contains("kufar.by"))
async def handle_kufar_link(message: Message, db: Database, state: FSMContext):
    await state.clear()
    url_match = re.search(r"https?://[^\s]+kufar\.by[^\s]*", message.text)
    if not url_match:
        return

    url = url_match.group(0)
    data = parse_kufar_url(url)

    if data.get("type") == "seller":
        seller_id = data["seller_id"]
        title = f"Продавец: {seller_id[:12]}..."
        await db.add_task(user_id=message.from_user.id, title=title, seller_id=seller_id)
        await message.answer(
            f"🔗 <b>Ссылка распознана!</b>\n\n"
            f"👤 Отслеживание продавца <code>{seller_id}</code> успешно включено!\n"
            f"Как только он выложит новый лот, вы сразу получите уведомление.",
            parse_mode="HTML",
            reply_markup=get_main_reply_kb(),
        )
    else:
        title = data["title"]
        await db.add_task(
            user_id=message.from_user.id,
            title=title,
            query=data["query"],
            category_id=data["category_id"],
            region_id=data["region_id"],
            min_price=data["min_price"],
            max_price=data["max_price"],
            currency=data["currency"],
            rooms=data["rooms"],
            only_owner=data["only_owner"],
        )
        await message.answer(
            f"🔗 <b>Ссылка с Куфара успешно распознана!</b>\n\n"
            f"🎯 <b>Создан мониторинг:</b> <code>{title}</code>\n"
            f"📍 Регион: {REGIONS.get(data['region_id'], 'Вся Беларусь')}\n"
            f"💰 Бюджет: {data['min_price']} - {data['max_price']} {data['currency']}\n"
            f"👤 Только собственники: {'Да' if data['only_owner'] else 'Все'}\n\n"
            f"Радар уже запущен и проверяет новые лоты!",
            parse_mode="HTML",
            reply_markup=get_main_reply_kb(),
        )


# ------------------- 📢 ПОДЕЛИТЬСЯ С ДРУГОМ -------------------
@router.message(F.text == "📢 Поделиться с другом", StateFilter("*"))
async def handle_share(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "🎁 <b>Поделитесь Куфар Радаром с друзьями!</b>\n\n"
        "Если ваши друзья или знакомые ищут квартиру без посредников в Минске "
        "или охотятся за выгодными предложениями на Куфаре — перешлите им ссылку на бота.\n\n"
        "👇 <i>Нажмите кнопку ниже, чтобы отправить рекомендацию в 1 клик:</i>"
    )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_share_kb(message.from_user.id),
    )


# ------------------- ⭐ ПОДДЕРЖАТЬ АВТОРА (TELEGRAM STARS) -------------------
@router.message(F.text == "⭐ Поддержать автора", StateFilter("*"))
async def show_donate_stars(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "⭐ <b>Поддержка проекта Куфар Радар</b>\n\n"
        "Если бот помогает вам находить выгодные лоты, квартиры или экономить время — "
        "вы можете поддержать разработку и оплату серверов через <b>Telegram Stars</b>!\n\n"
        "Выберите сумму поддержки в звёздах:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_stars_donate_kb())


@router.callback_query(F.data.startswith("stars_pay:"))
async def create_stars_invoice(callback: CallbackQuery, bot: Bot):
    amount = int(callback.data.split(":")[1])
    await callback.answer()

    prices = [LabeledPrice(label="Звёзды", amount=amount)]

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Поддержка Куфар Радар",
        description=f"Добровольная поддержка автора бота на {amount} Звёзд. Спасибо за вклад!",
        payload=f"donate_{amount}_stars",
        currency="XTR",  # Telegram Stars
        prices=prices,
        provider_token="",  # Для Telegram Stars provider_token всегда пустая строка!
    )


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    # Одобряем платеж звездами мгновенно
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    stars = message.successful_payment.total_amount
    await message.answer(
        f"❤️ <b>Огромное спасибо за поддержку ({stars} ⭐)!</b>\n"
        "Ваш вклад помогает развивать скорость и стабильность серверов Куфар Радара.",
        parse_mode="HTML",
    )


# ------------------- ОБРАБОТЧИК ЛЮБОГО ДРУГОГО ТЕКСТА (В САМОМ КОНЦЕ) -------------------
@router.message()
async def fallback_text_handler(message: Message):
    if message.text in MENU_BUTTONS:
        return
    text = (
        "👋 <b>Куфар Радар слушает!</b>\n\n"
        "• Отправьте мне любую <b>ссылку с Куфара</b> — и я сразу начну её отслеживать.\n"
        "• Или выберите нужное действие в <b>меню кнопками ниже</b>:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_reply_kb())
