import asyncio
import logging
from typing import Dict, Any, List, Set
from aiogram import Bot
from database import Database
from kufar_client import KufarClient, KufarAd
from keyboards import get_ad_card_kb

logger = logging.getLogger(__name__)


def build_ad_message(ad: KufarAd, task_title: str, user_settings: dict) -> str:
    # 1. Валюта
    cur_pref = user_settings.get("currency", "BOTH")
    if cur_pref == "BYN":
        price_line = ad.price_byn_str
    elif cur_pref == "USD":
        price_line = ad.price_usd_str
    else:
        price_line = f"{ad.price_byn_str} <i>({ad.price_usd_str})</i>"

    owner_badge = " [Собственник]" if not ad.is_company else ""

    # 2. Умные детали перекупа/арендатора
    smart_part = ""
    if user_settings.get("show_smart", 1) and ad.smart_details:
        smart_part = f"\n{ad.smart_details}\n"

    # 3. Описание в blockquote
    quote_part = ""
    if user_settings.get("show_desc", 1) and ad.body:
        clean_body = ad.body.strip().replace("<", "&lt;").replace(">", "&gt;")
        if len(clean_body) > 300:
            clean_body = clean_body[:300] + "..."
        quote_part = f"\n<blockquote>{clean_body}</blockquote>"

    text = (
        f"⚡ <b>Новое объявление на Куфаре!</b>\n"
        f"🎯 Поиск: <code>{task_title}</code>\n\n"
        f"🏷 <b><a href=\"{ad.link}\">{ad.title}</a></b>{owner_badge}\n"
        f"💰 <b>Цена:</b> {price_line}\n"
        f"📍 <b>Локация:</b> {ad.location}\n"
        f"🕒 <b>Опубликовано:</b> {ad.time_str}"
        f"{smart_part}"
        f"{quote_part}"
    )
    return text


class KufarWatcher:
    def __init__(self, bot: Bot, db: Database, poll_interval: int = 20):
        self.bot = bot
        self.db = db
        self.poll_interval = poll_interval
        self.client = KufarClient()
        self._running = False
        self._initialized_tasks: Set[int] = set()

    async def start(self):
        self._running = True
        logger.info("Starting KufarWatcher with %s s interval", self.poll_interval)
        while self._running:
            try:
                await self._check_cycle()
            except Exception as e:
                logger.error("Error in watcher cycle: %s", e, exc_info=True)
            await asyncio.sleep(self.poll_interval)

    def stop(self):
        self._running = False

    async def _check_cycle(self):
        tasks = await self.db.get_all_active_tasks()
        if not tasks:
            return

        for task in tasks:
            task_id = task["id"]
            user_id = task["user_id"]
            title = task["title"]

            ads = await self.client.fetch_ads(
                query=task.get("query"),
                category_id=task.get("category_id"),
                region_id=task.get("region_id"),
                min_price=task.get("min_price"),
                max_price=task.get("max_price"),
                currency=task.get("currency", "BYN"),
                rooms=task.get("rooms"),
                seller_id=task.get("seller_id"),
                only_owner=bool(task.get("only_owner")),
                size=10,
            )

            if not ads:
                continue

            ad_ids = [ad.ad_id for ad in ads]

            # Если задача проверяется впервые — прогреваем кэш
            if task_id not in self._initialized_tasks:
                await self.db.mark_ads_seen(ad_ids)
                self._initialized_tasks.add(task_id)
                logger.info("Initialized search '%s' (id: %s) with %s ads", title, task_id, len(ads))
                continue

            unseen_ids = await self.db.filter_unseen_ads(ad_ids)
            if not unseen_ids:
                continue

            # Получаем настройки конкретного пользователя
            user_settings = await self.db.get_user_settings(user_id)
            mute = not bool(user_settings.get("sound", 1))
            show_photo = bool(user_settings.get("show_photo", 1))

            new_ads = [ad for ad in ads if ad.ad_id in unseen_ids]
            new_ads.reverse()

            for ad in new_ads:
                # Проверяем, не заблокирован ли продавец пользователем
                if ad.account_id and await self.db.is_seller_blocked(user_id, ad.account_id):
                    await self.db.mark_ads_seen([ad.ad_id])
                    continue

                # Подгружаем реальное описание со страницы объявления для цитаты и анализа
                if user_settings.get("show_desc", 1):
                    full_body = await self.client.fetch_ad_body(ad.link)
                    if full_body:
                        ad.body = full_body
                        from kufar_client import extract_smart_details
                        ad.smart_details = extract_smart_details(ad.title, full_body, [], task.get("category_id") or 0)

                msg_text = build_ad_message(ad, title, user_settings)
                reply_markup = get_ad_card_kb(ad.link, ad.account_id)

                sent = False
                if show_photo and ad.image_url:
                    try:
                        await self.bot.send_photo(
                            chat_id=user_id,
                            photo=ad.image_url,
                            caption=msg_text,
                            parse_mode="HTML",
                            reply_markup=reply_markup,
                            disable_notification=mute,
                        )
                        sent = True
                    except Exception as img_err:
                        logger.warning("Failed to send photo: %s, fallback to text", img_err)

                if not sent:
                    try:
                        await self.bot.send_message(
                            chat_id=user_id,
                            text=msg_text,
                            parse_mode="HTML",
                            reply_markup=reply_markup,
                            disable_web_page_preview=False,
                            disable_notification=mute,
                        )
                    except Exception as send_err:
                        logger.error("Failed to deliver alert to %s: %s", user_id, send_err)

                await self.db.mark_ads_seen([ad.ad_id])
                await asyncio.sleep(0.3)
