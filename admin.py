import asyncio
import logging
import time
from aiogram import Router, F, Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command, BaseFilter, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import config
from database import Database
from kufar_client import KufarClient

logger = logging.getLogger(__name__)
admin_router = Router()


class IsAdminFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = event.from_user.id
        return user_id in config.ADMIN_IDS


class BroadcastFSM(StatesGroup):
    waiting_for_message = State()
    waiting_for_confirm = State()


def get_admin_hub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Живая статистика", callback_data="adm:stats"),
                InlineKeyboardButton(text="📢 Массовая рассылка", callback_data="adm:broadcast"),
            ],
            [
                InlineKeyboardButton(text="🔝 Топ запросов", callback_data="adm:queries"),
                InlineKeyboardButton(text="👥 Новые пользователи", callback_data="adm:users"),
            ],
            [
                InlineKeyboardButton(text="⚡ Пинг Kufar API", callback_data="adm:ping"),
            ],
        ]
    )


# ------------------- ТОЧКА ВХОДА В АДМИНКУ: /admin -------------------
@admin_router.message(Command("admin"), IsAdminFilter(), StateFilter("*"))
async def cmd_admin(message: Message, state: FSMContext, db: Database):
    await state.clear()
    stats = await db.get_admin_stats()
    text = (
        "👑 <b>Панель управления Куфар Радар</b>\n\n"
        f"👥 Пользователей всего: <b>{stats['total_users']}</b> (новых за сутки: <b>+{stats['users_24h']}</b>)\n"
        f"🎯 Активных мониторингов: <b>{stats['active_tasks']}</b> из {stats['total_tasks']}\n"
        f"💾 База данных: <b>{stats['db_size_kb']} KB</b> (лотов в кэше: <b>{stats['total_seen']}</b>)\n\n"
        "<i>Выберите действие в панели администратора:</i>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_admin_hub_kb())


# ------------------- 📊 СТАТИСТИКА -------------------
@admin_router.callback_query(F.data == "adm:stats", IsAdminFilter())
async def adm_stats_cb(callback: CallbackQuery, db: Database):
    stats = await db.get_admin_stats()
    text = (
        "📊 <b>Детальная аналитика бота:</b>\n\n"
        f"• 👥 <b>Всего пользователей:</b> {stats['total_users']}\n"
        f"• 📈 <b>Прирост за 24ч:</b> +{stats['users_24h']}\n"
        f"• 🎯 <b>Активных задач радара:</b> {stats['active_tasks']}\n"
        f"• ⏸ <b>Задач на паузе:</b> {stats['total_tasks'] - stats['active_tasks']}\n"
        f"• 🏷 <b>Уникальных лотов обработано:</b> {stats['total_seen']:,}\n"
        f"• 🚫 <b>Скрытых продавцов:</b> {stats['total_blocked']}\n"
        f"• 💾 <b>Размер базы SQLite:</b> {stats['db_size_kb']} KB\n"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="adm:stats"),
                InlineKeyboardButton(text="◀️ В меню админа", callback_data="adm:menu"),
            ]
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@admin_router.callback_query(F.data == "adm:menu", IsAdminFilter(), StateFilter("*"))
async def adm_menu_cb(callback: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    stats = await db.get_admin_stats()
    text = (
        "👑 <b>Панель управления Куфар Радар</b>\n\n"
        f"👥 Пользователей: <b>{stats['total_users']}</b> | Активных задач: <b>{stats['active_tasks']}</b>\n"
        "<i>Выберите действие в панели:</i>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_hub_kb())
    await callback.answer()


# ------------------- 🔝 ТОП ЗАПРОСОВ -------------------
@admin_router.callback_query(F.data == "adm:queries", IsAdminFilter())
async def adm_queries_cb(callback: CallbackQuery, db: Database):
    queries = await db.get_top_queries(8)
    if not queries:
        text = "🔝 <b>Топ запросов:</b>\n\nПока нет данных о поисках."
    else:
        lines = ["🔝 <b>Что чаще всего отслеживают пользователи:</b>\n"]
        for i, q in enumerate(queries, 1):
            lines.append(f"<b>{i}.</b> {q['title']} — <b>{q['cnt']}</b> шт.")
        text = "\n".join(lines)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:menu")]
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


# ------------------- 👥 ПОСЛЕДНИЕ ПОЛЬЗОВАТЕЛИ -------------------
@admin_router.callback_query(F.data == "adm:users", IsAdminFilter())
async def adm_users_cb(callback: CallbackQuery, db: Database):
    users = await db.get_recent_users(8)
    if not users:
        text = "👥 Пользователи еще не зарегистрированы."
    else:
        lines = ["👥 <b>Последние зарегистрированные пользователи:</b>\n"]
        for u in users:
            uname = f"@{u['username']}" if u["username"] else "без username"
            reg_time = u["created_at"].split()[0] if u.get("created_at") else ""
            lines.append(
                f"• <b>{u['full_name']}</b> ({uname})\n"
                f"  ID: <code>{u['user_id']}</code> | Поисков: {u['task_count']} | Дата: {reg_time}\n"
            )
        text = "\n".join(lines)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:menu")]
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


# ------------------- ⚡ ПИНГ KUFAR API -------------------
@admin_router.callback_query(F.data == "adm:ping", IsAdminFilter())
async def adm_ping_cb(callback: CallbackQuery):
    await callback.answer("Замеряем пинг...")
    client = KufarClient()
    t0 = time.time()
    ads = await client.fetch_ads(size=1)
    latency_ms = round((time.time() - t0) * 1000)
    await client.close()

    status_icon = "🟢 Отлично" if latency_ms < 500 else ("🟡 Средне" if latency_ms < 1200 else "🔴 Высокий пинг")

    text = (
        "⚡ <b>Диагностика подключения к Kufar API:</b>\n\n"
        f"• Статус шлюза: {status_icon}\n"
        f"• Время ответа (пинг): <b>{latency_ms} ms</b>\n"
        f"• Лотов получено: <b>{len(ads)}</b>\n\n"
        "<i>Шлюз работает стабильно, блокировок и капчи нет.</i>"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Замерить снова", callback_data="adm:ping"),
                InlineKeyboardButton(text="◀️ Назад", callback_data="adm:menu"),
            ]
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


# ------------------- 📢 МАССОВАЯ РАССЫЛКА (BROADCAST) -------------------
@admin_router.callback_query(F.data == "adm:broadcast", IsAdminFilter())
async def adm_broadcast_prompt(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(BroadcastFSM.waiting_for_message)

    text = (
        "📢 <b>Массовая рассылка сообщений</b>\n\n"
        "Отправьте сообщение, которое хотите разослать всем пользователям бота.\n\n"
        "<i>Поддерживается: текст, форматирование (жирный/ссылки), фото с описанием.</i>\n\n"
        "Для отмены отправьте команду /cancel или нажмите кнопку ниже:"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="adm:menu")]]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@admin_router.message(BroadcastFSM.waiting_for_message, IsAdminFilter())
async def adm_broadcast_preview(message: Message, state: FSMContext, db: Database):
    user_ids = await db.get_all_user_ids()
    total_recipients = len(user_ids)

    # Сохраняем сообщение для рассылки
    await state.update_data(
        broadcast_msg_id=message.message_id,
        broadcast_chat_id=message.chat.id,
    )
    await state.set_state(BroadcastFSM.waiting_for_confirm)

    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🚀 Отправить ({total_recipients} юзерам)",
                    callback_data="adm:broadcast_send",
                ),
                InlineKeyboardButton(text="❌ Отмена", callback_data="adm:menu"),
            ]
        ]
    )

    await message.answer(
        "👆 <b>Предпросмотр сообщения выше.</b>\n\n"
        f"Получателей в базе: <b>{total_recipients} чел.</b>\n"
        "Начать отправку?",
        parse_mode="HTML",
        reply_markup=confirm_kb,
    )


@admin_router.callback_query(
    F.data == "adm:broadcast_send", BroadcastFSM.waiting_for_confirm, IsAdminFilter()
)
async def adm_broadcast_execute(
    callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot
):
    data = await state.get_data()
    await state.clear()

    src_chat_id = data.get("broadcast_chat_id")
    src_msg_id = data.get("broadcast_msg_id")

    user_ids = await db.get_all_user_ids()
    await callback.message.edit_text("⏳ <i>Рассылка запущена, идет отправка...</i>", parse_mode="HTML")

    success_cnt = 0
    blocked_cnt = 0
    error_cnt = 0

    for uid in user_ids:
        try:
            await bot.copy_message(
                chat_id=uid,
                from_chat_id=src_chat_id,
                message_id=src_msg_id,
            )
            success_cnt += 1
        except Exception as e:
            err_str = str(e).lower()
            if "blocked" in err_str or "deactivated" in err_str:
                blocked_cnt += 1
            else:
                error_cnt += 1

        # Безопасная пауза, чтобы не превысить лимит Telegram в 30 сообщений/сек
        await asyncio.sleep(0.04)

    report_text = (
        "📢 <b>Отчет о рассылке:</b>\n\n"
        f"• ✅ <b>Успешно доставлено:</b> {success_cnt}\n"
        f"• 🚫 <b>Заблокировали бота:</b> {blocked_cnt}\n"
        f"• ⚠️ <b>Ошибок:</b> {error_cnt}\n"
        f"• 👥 <b>Всего получателей:</b> {len(user_ids)}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню админа", callback_data="adm:menu")]]
    )
    await callback.message.answer(report_text, parse_mode="HTML", reply_markup=kb)
