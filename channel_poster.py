import asyncio
import logging
from typing import Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import config
from database import Database
from rental_aggregator import RentalAggregator, RentalListing
from kufar_client import KufarClient

logger = logging.getLogger(__name__)


def build_channel_post(ad: RentalListing) -> tuple[str, InlineKeyboardMarkup]:
    quote_part = ""
    if ad.description:
        clean_body = ad.description.strip().replace("<", "&lt;").replace(">", "&gt;")
        if len(clean_body) > 300:
            clean_body = clean_body[:300] + "..."
        quote_part = f"\n<blockquote>{clean_body}</blockquote>"

    text = (
        f"🏠 <b>Новая квартира в Минске [Собственник]</b>\n\n"
        f"🏷 <b><a href=\"{ad.link}\">{ad.title}</a></b>\n"
        f"💰 <b>Цена:</b> {ad.price_usd_str} <i>({ad.price_byn_str})</i>\n"
        f"📍 <b>Адрес:</b> {ad.location}\n"
        f"🏢 <b>Комнат:</b> {ad.rooms_str}\n"
        f"🌐 <b>Источник:</b> {ad.source_badge}"
        f"{quote_part}\n\n"
        f"⚡ <i>Хотите получать такие квартиры за 10 секунд до публикации на канале? Подключите личный радар:</i> @kufar_radar_by_bot"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡ Настроить поиск под себя в боте",
                    url="https://t.me/kufar_radar_by_bot?start=channel_minsk",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"👉 Открыть на {ad.source}",
                    url=ad.link,
                )
            ],
        ]
    )
    return text, kb


class ChannelAutoPoster:
    def __init__(self, bot: Bot, db: Database, channel_username: str, poll_interval: int = 30):
        self.bot = bot
        self.db = db
        self.channel_username = channel_username
        self.poll_interval = poll_interval
        self.aggregator = RentalAggregator()
        self.kufar_client = KufarClient()
        self._running = False
        self._initialized = False

    async def start(self):
        if not self.channel_username:
            logger.info("Channel auto-poster disabled (no channel username specified)")
            return

        self._running = True
        logger.info(
            "Starting Multi-Source ChannelAutoPoster (Kufar + Onliner + Realt) for %s with %s s interval",
            self.channel_username,
            self.poll_interval,
        )

        while self._running:
            try:
                await self._post_cycle()
            except Exception as e:
                logger.error("Error in multi-source channel poster cycle: %s", e, exc_info=True)
            await asyncio.sleep(self.poll_interval)

    def stop(self):
        self._running = False

    async def _post_cycle(self):
        # Собираем свежие объявления со всех 3 площадок (только собственники)
        ads = await self.aggregator.fetch_all_fresh()
        if not ads:
            return

        ad_uids = [ad.uid for ad in ads]

        # При первом запуске бота
        if not self._initialized:
            unseen = await self.db.filter_unseen_channel_ads(ad_uids)
            if unseen:
                # Находим по одному свежему объявлению от каждого источника для приветственного запуска
                seen_sources = set()
                sample_ads = []
                for uid in unseen:
                    item = next((a for a in ads if a.uid == uid), None)
                    if item and item.source not in seen_sources:
                        seen_sources.add(item.source)
                        sample_ads.append(item)
                    if len(sample_ads) >= 2:
                        break

                for sample_ad in sample_ads:
                    await self._publish_ad(sample_ad)
                    await self.db.mark_channel_ads_seen([sample_ad.uid])
                    await asyncio.sleep(2)

            await self.db.mark_channel_ads_seen(ad_uids)
            self._initialized = True
            logger.info(
                "Multi-Source ChannelAutoPoster initialized successfully for %s (%d ads tracked)",
                self.channel_username,
                len(ad_uids),
            )
            return

        unseen_uids = await self.db.filter_unseen_channel_ads(ad_uids)
        if not unseen_uids:
            return

        new_ads = [ad for ad in ads if ad.uid in unseen_uids]
        # Публикуем от более старых к самым свежим
        new_ads.reverse()

        for ad in new_ads:
            await self._publish_ad(ad)
            await self.db.mark_channel_ads_seen([ad.uid])
            await asyncio.sleep(2)

    async def _publish_ad(self, ad: RentalListing):
        try:
            # Для Куфара подтягиваем описание со страницы, если его еще нет
            if ad.source == "Kufar" and not ad.description:
                try:
                    full_body = await self.kufar_client.fetch_ad_body(ad.link)
                    if full_body:
                        ad.description = full_body
                except Exception:
                    pass

            msg_text, kb = build_channel_post(ad)

            if ad.image_url:
                try:
                    await self.bot.send_photo(
                        chat_id=self.channel_username,
                        photo=ad.image_url,
                        caption=msg_text,
                        parse_mode="HTML",
                        reply_markup=kb,
                    )
                    logger.info("Published %s (%s) to channel %s with photo", ad.uid, ad.source, self.channel_username)
                    return
                except Exception as img_err:
                    logger.warning("Failed to post photo for %s to channel: %s, fallback to text", ad.uid, img_err)

            await self.bot.send_message(
                chat_id=self.channel_username,
                text=msg_text,
                parse_mode="HTML",
                reply_markup=kb,
                disable_web_page_preview=False,
            )
            logger.info("Published %s (%s) to channel %s with text", ad.uid, ad.source, self.channel_username)
        except Exception as e:
            logger.error("Failed to post ad %s to channel %s: %s", ad.uid, self.channel_username, e)
