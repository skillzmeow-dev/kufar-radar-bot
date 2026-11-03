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

from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import BOT_TOKEN, CHECK_INTERVAL_SECONDS
from database import (
    add_subscriber,
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
dp = Dispatcher()

def get_main_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Расписание на сегодня", callback_data="schedule_today"),
            InlineKeyboardButton(text="⏭ Расписание на завтра", callback_data="schedule_tomorrow")
        ]
    ])
    return kb


def get_schedule_for_date(target_dt: datetime) -> str:
    """
    Finds if substitutions exist on Drive for target_dt.
    If yes, parses and merges with regular schedule.
    If no, returns standard regular schedule with note about latest file on Drive.
    """
    target_date_str = target_dt.strftime("%d.%m.%Y")
    target_day_index = target_dt.weekday()

    # Fetch file list from Google Drive
    drive_files = fetch_drive_file_list()
    last_file_info = drive_files[0]['filename'].replace('.pdf', '') if drive_files else ""

    # Look for matching file for target_date_str
    # Handles both '02.11.2026.pdf' and '02.11.26.pdf'
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

    # Fallback to standard schedule
    return build_schedule_message(
        target_date_str=target_date_str,
        target_day_index=target_day_index,
        parsed_substitutions=None,
        last_update_info=last_file_info
    )


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    # Register chat for auto notifications
    chat_type = message.chat.type
    title = message.chat.title or message.chat.full_name or ""
    add_subscriber(message.chat.id, chat_type, title)

    welcome_text = (
        f"👋 <b>Привет! Я бот замен и расписания для группы 02-24 РУБ.</b>\n\n"
        f"• Я автоматически отслеживаю Google Диск колледжа на наличие новых замен.\n"
        f"• Когда появляются новые замены — я присылаю готовое расписание и закрепляю его в чате.\n\n"
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


async def check_drive_updates_loop():
    """
    Background worker that checks Google Drive every CHECK_INTERVAL_SECONDS.
    When a new substitutions file is uploaded, builds schedule and broadcasts to all chats,
    then automatically pins the message.
    """
    while True:
        try:
            files = fetch_drive_file_list()
            for f in files:
                fname = f['filename']
                fid = f['file_id']

                if not is_file_processed(fname):
                    logging.info(f"New file found on Google Drive: {fname}")
                    local_path = download_drive_file(fid, fname)
                    if not local_path:
                        continue

                    parsed = parse_pdf_substitutions(local_path)
                    
                    # Determine date and day index
                    target_date_str = parsed.get('date_str', '')
                    # If date_str is missing or short, try parse from filename e.g. 02.11.2026.pdf
                    if not target_date_str:
                        m = re.match(r'(\d{2}\.\d{2}\.\d{4})', fname)
                        if m:
                            target_date_str = m.group(1)

                    target_day_index = 0
                    if target_date_str:
                        try:
                            # Try 4-digit year or 2-digit year
                            if len(target_date_str.split('.')[-1]) == 4:
                                dt = datetime.strptime(target_date_str, "%d.%m.%Y")
                            else:
                                dt = datetime.strptime(target_date_str, "%d.%m.%y")
                            target_day_index = dt.weekday()
                        except Exception:
                            pass

                    # Build schedule
                    schedule_text = build_schedule_message(
                        target_date_str=target_date_str or fname.replace('.pdf', ''),
                        target_day_index=target_day_index,
                        parsed_substitutions=parsed
                    )

                    # Broadcast to subscribers
                    subscribers = get_subscribers()
                    for chat_id, chat_type in subscribers:
                        try:
                            sent_msg = await bot.send_message(
                                chat_id=chat_id,
                                text=schedule_text,
                                parse_mode=ParseMode.HTML,
                                reply_markup=get_main_keyboard()
                            )
                            # Automatically pin message as requested by user
                            try:
                                await bot.pin_chat_message(
                                    chat_id=chat_id,
                                    message_id=sent_msg.message_id,
                                    disable_notification=False
                                )
                            except Exception as pin_err:
                                # Pinning might fail if bot lacks admin rights in a group, ignore
                                logging.debug(f"Could not pin in chat {chat_id}: {pin_err}")
                        except Exception as send_err:
                            logging.error(f"Failed to send update to {chat_id}: {send_err}")

                    # Mark file as processed
                    mark_file_processed(fname, fid, target_date_str)
                    logging.info(f"File {fname} processed and broadcasted to {len(subscribers)} chats.")
        except Exception as e:
            logging.error(f"Error in check_drive_updates_loop: {e}")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def main():
    init_db()
    logging.info("Starting KSO Bot...")
    # Start background polling task
    asyncio.create_task(check_drive_updates_loop())
    # Start bot polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
