import asyncio
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone

# Ensure kso_bot directory is at the front of sys.path to avoid collisions
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from aiogram import BaseMiddleware, Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.filters.chat_member_updated import (
    JOIN_TRANSITION,
    LEAVE_TRANSITION,
    ChatMemberUpdatedFilter,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup

from config import ADMIN_IDS, BOT_TOKEN, CHECK_INTERVAL_SECONDS
from database import (
    add_subscriber,
    get_stats,
    get_subscribers,
    init_db,
    is_file_processed,
    mark_file_processed,
    remove_subscriber,
)
from drive_parser import (
    download_drive_file,
    fetch_drive_file_list,
    parse_pdf_substitutions,
)
from schedule_builder import build_schedule_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Timezone Minsk (UTC+3)
MINSK_TZ = timezone(timedelta(hours=3))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class AutoRegisterMiddleware(BaseMiddleware):
    """
    Automatically registers any chat (private, group, supergroup) as a subscriber
    whenever any message or button click occurs.
    """
    async def __call__(self, handler, event, data):
        chat = getattr(event, "chat", None)
        if not chat:
            msg = getattr(event, "message", None)
            if msg:
                chat = getattr(msg, "chat", None)
        if chat:
            title = chat.title or chat.full_name or ""
            add_subscriber(chat.id, chat.type, title)
        return await handler(event, data)


dp.message.outer_middleware(AutoRegisterMiddleware())
dp.callback_query.outer_middleware(AutoRegisterMiddleware())


class AdminStates(StatesGroup):
    waiting_for_broadcast = State()


def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Расписание на сегодня", callback_data="schedule_today"),
            InlineKeyboardButton(text="⏭ Расписание на завтра", callback_data="schedule_tomorrow")
        ]
    ])


def get_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Проверить замены сейчас", callback_data="admin_check_now"),
        ],
        [
            InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast"),
        ],
        [
            InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")
        ]
    ])


def get_schedule_for_date(target_dt: datetime) -> str:
    target_date_str = target_dt.strftime("%d.%m.%Y")
    target_day_index = target_dt.weekday()

    drive_files = fetch_drive_file_list()
    last_file_info = drive_files[0]['filename'].replace('.pdf', '') if drive_files else ""

    short_date_str = target_dt.strftime("%d.%m.%y")
    matching_file = None
    for f in drive_files:
        fname = f['filename']
        if target_date_str in fname or short_date_str in fname:
            matching_file = f
            break

    if matching_file:
        local_path = download_drive_file(matching_file['file_id'], matching_file['filename'])
        if local_path:
            parsed = parse_pdf_substitutions(local_path)
            return build_schedule_message(target_date_str, target_day_index, parsed)

    return build_schedule_message(
        target_date_str=target_date_str,
        target_day_index=target_day_index,
        parsed_substitutions=None,
        last_update_info=last_file_info
    )


# When bot is added to a group or channel
@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def on_bot_joined_chat(event: ChatMemberUpdated):
    chat = event.chat
    add_subscriber(chat.id, chat.type, chat.title or "")
    logging.info(f"Bot joined chat: {chat.title} ({chat.id})")
    try:
        await bot.send_message(
            chat_id=chat.id,
            text=(
                "👋 <b>Бот замен группы 02-24 подключен к беседе!</b>\n\n"
                "• Когда на Google Диске появятся новые замены — расписание автоматически придёт сюда и закрепится.\n"
                "• Чтобы узнать расписание прямо сейчас, используйте команду /today или /tomorrow."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logging.warning(f"Could not send welcome message to group {chat.id}: {e}")


@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=LEAVE_TRANSITION))
async def on_bot_left_chat(event: ChatMemberUpdated):
    remove_subscriber(event.chat.id)
    logging.info(f"Bot removed from chat: {event.chat.id}")


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    chat_type = message.chat.type
    title = message.chat.title or message.chat.full_name or ""
    add_subscriber(message.chat.id, chat_type, title)

    welcome_text = (
        f"👋 <b>Привет! Я бот замен и расписания для группы 02-24 РУБ.</b>\n\n"
        f"• Я автоматически отслеживаю Google Диск колледжа на наличие новых замен.\n"
        f"• Когда появляются новые замены — я присылаю готовое расписание и автоматически закрепляю его в чате.\n\n"
        f"Выбери нужный день кнопками ниже:"
    )
    await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())


@dp.message(Command("today"))
async def cmd_today(message: types.Message):
    now_minsk = datetime.now(MINSK_TZ)
    text = get_schedule_for_date(now_minsk)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())


@dp.message(Command("tomorrow"))
async def cmd_tomorrow(message: types.Message):
    tomorrow_minsk = datetime.now(MINSK_TZ) + timedelta(days=1)
    text = get_schedule_for_date(tomorrow_minsk)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())


@dp.callback_query(F.data == "schedule_today")
async def cb_today(call: types.CallbackQuery):
    now_minsk = datetime.now(MINSK_TZ)
    text = get_schedule_for_date(now_minsk)
    await call.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())
    await call.answer()


@dp.callback_query(F.data == "schedule_tomorrow")
async def cb_tomorrow(call: types.CallbackQuery):
    tomorrow_minsk = datetime.now(MINSK_TZ) + timedelta(days=1)
    text = get_schedule_for_date(tomorrow_minsk)
    await call.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())
    await call.answer()


# ================= ADMIN PANEL =================

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    stats = get_stats()
    files_str = "\n".join([f"• <code>{f[0]}</code> ({f[1]})" for f in stats['last_files']]) or "Нет данных"

    text = (
        f"👑 <b>Админ-панель бота замен 02-24</b>\n\n"
        f"📊 <b>Статистика подписчиков:</b>\n"
        f"• Всего чатов: <b>{stats['total']}</b>\n"
        f"• В личных сообщениях: <b>{stats['private']}</b>\n"
        f"• В группах/беседах: <b>{stats['groups']}</b>\n\n"
        f"📁 <b>Последние обработанные файлы:</b>\n{files_str}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_keyboard())


@dp.callback_query(F.data == "admin_close")
async def cb_admin_close(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.message.delete()
    await call.answer()


@dp.callback_query(F.data == "admin_check_now")
async def cb_admin_check_now(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return

    await call.answer("Проверяю Google Диск...", show_alert=False)
    processed_count = await check_and_broadcast_updates(force=True)
    stats = get_stats()
    files_str = "\n".join([f"• <code>{f[0]}</code> ({f[1]})" for f in stats['last_files']]) or "Нет данных"

    text = (
        f"👑 <b>Админ-панель бота замен 02-24</b>\n\n"
        f"✅ <b>Проверка завершена!</b> Новых файлов обработано: {processed_count}\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего чатов: <b>{stats['total']}</b> (ЛС: {stats['private']}, Групп: {stats['groups']})\n\n"
        f"📁 <b>Последние файлы:</b>\n{files_str}"
    )
    try:
        await call.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_admin_keyboard())
    except Exception:
        pass


@dp.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return

    await state.set_state(AdminStates.waiting_for_broadcast)
    await call.message.answer(
        "✍️ <b>Введи текст сообщения для рассылки всем подписчикам:</b>\n"
        "<i>(Или отправь /cancel для отмены)</i>",
        parse_mode=ParseMode.HTML
    )
    await call.answer()


@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.clear()
    await message.answer("❌ Действие отменено.")


@dp.message(AdminStates.waiting_for_broadcast)
async def process_broadcast_text(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    broadcast_text = message.text or message.caption or ""
    await state.clear()

    subscribers = get_subscribers()
    sent_count = 0
    fail_count = 0

    progress_msg = await message.answer(f"⏳ Отправка рассылки {len(subscribers)} чатам...")

    for chat_id, chat_type in subscribers:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=broadcast_text,
                parse_mode=ParseMode.HTML
            )
            sent_count += 1
        except Exception:
            fail_count += 1
        await asyncio.sleep(0.05)

    await progress_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"• Успешно отправлено: <b>{sent_count}</b>\n"
        f"• Ошибок отправки: <b>{fail_count}</b>",
        parse_mode=ParseMode.HTML
    )


# ================= BACKGROUND MONITORING =================

async def check_and_broadcast_updates(force: bool = False) -> int:
    processed_count = 0
    try:
        files = fetch_drive_file_list()
        for f in files:
            fname = f['filename']
            fid = f['file_id']

            if force or not is_file_processed(fname):
                logging.info(f"Processing substitutions file: {fname}")
                local_path = download_drive_file(fid, fname)
                if not local_path:
                    continue

                parsed = parse_pdf_substitutions(local_path)
                target_date_str = parsed.get('date_str', '')
                if not target_date_str:
                    m = re.match(r'(\d{2}\.\d{2}\.\d{4})', fname)
                    if m:
                        target_date_str = m.group(1)

                target_day_index = 0
                if target_date_str:
                    try:
                        if len(target_date_str.split('.')[-1]) == 4:
                            dt = datetime.strptime(target_date_str, "%d.%m.%Y")
                        else:
                            dt = datetime.strptime(target_date_str, "%d.%m.%y")
                        target_day_index = dt.weekday()
                    except Exception:
                        pass

                schedule_text = build_schedule_message(
                    target_date_str=target_date_str or fname.replace('.pdf', ''),
                    target_day_index=target_day_index,
                    parsed_substitutions=parsed
                )

                subscribers = get_subscribers()
                for chat_id, chat_type in subscribers:
                    try:
                        sent_msg = await bot.send_message(
                            chat_id=chat_id,
                            text=schedule_text,
                            parse_mode=ParseMode.HTML,
                            reply_markup=get_main_keyboard()
                        )
                        # ONLY auto-broadcasted messages are pinned
                        try:
                            await bot.pin_chat_message(
                                chat_id=chat_id,
                                message_id=sent_msg.message_id,
                                disable_notification=False
                            )
                        except Exception as pin_err:
                            logging.debug(f"Could not pin in chat {chat_id}: {pin_err}")
                    except Exception as send_err:
                        logging.error(f"Failed to send update to {chat_id}: {send_err}")

                mark_file_processed(fname, fid, target_date_str)
                processed_count += 1
                logging.info(f"File {fname} broadcasted and pinned in {len(subscribers)} chats.")
    except Exception as e:
        logging.error(f"Error in check_and_broadcast_updates: {e}")

    return processed_count


async def check_drive_updates_loop():
    while True:
        await check_and_broadcast_updates(force=False)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def main():
    init_db()
    logging.info("Starting KSO Bot...")
    asyncio.create_task(check_drive_updates_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
