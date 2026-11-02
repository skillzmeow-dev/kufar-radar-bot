import asyncio
import logging
import re
import json
from dataclasses import dataclass
from typing import Optional, List
import aiohttp

logger = logging.getLogger(__name__)

HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

HEADERS_ONLINER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


@dataclass
class RentalListing:
    uid: str                 # kufar_1088056326 / onliner_977979 / realt_4243501
    source: str              # "Kufar", "Onliner", "Realt"
    source_badge: str        # "🟢 Kufar", "🟡 Onliner", "🔵 Realt"
    title: str               # "1-комнатная квартира"
    price_usd_str: str       # "$450 / мес."
    price_byn_str: str       # "1 350 BYN"
    location: str            # "Минск, ул. Ленина, 13"
    rooms_str: str           # "1-комнатная"
    link: str                # https://...
    image_url: Optional[str] = None
    description: Optional[str] = None


def format_rooms(rooms_val: any) -> str:
    if not rooms_val:
        return "Квартира"
    s = str(rooms_val).strip()
    mapping = {
        "1": "1-комнатная",
        "2": "2-комнатная",
        "3": "3-комнатная",
        "4": "4-комнатная",
        "5": "5-комнатная",
        "1_room": "1-комнатная",
        "2_rooms": "2-комнатная",
        "3_rooms": "3-комнатная",
        "4_rooms": "4-комнатная",
        "5_rooms": "5-комнатная",
        "room": "Комната",
    }
    return mapping.get(s, f"{s}-комнатная")


class RentalAggregator:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15, connect=5)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------- KUFAR FETCHER -------------------
    async def fetch_kufar(self, limit: int = 8) -> List[RentalListing]:
        listings = []
        try:
            session = await self.get_session()
            url = (
                f"https://api.kufar.by/search-api/v2/search/rendered-paginated"
                f"?cat=1010&typ=let&rgn=7&cmp=0&size={limit}&sort=lst.d"
            )
            async with session.get(url, headers=HEADERS_BROWSER) as resp:
                if resp.status != 200:
                    logger.warning("Kufar rent fetch failed with status %s", resp.status)
                    return []
                data = await resp.json()

            ads = data.get("ads", [])
            for item in ads:
                ad_id = str(item.get("ad_id", ""))
                if not ad_id:
                    continue

                # Цена
                p_usd_raw = item.get("price_usd", "0")
                p_byn_raw = item.get("price_byn", "0")
                try:
                    p_usd = int(int(p_usd_raw) / 100)
                    p_byn = int(int(p_byn_raw) / 100)
                    if p_usd > 4000:  # Отсекаем ошибочные продажи
                        continue
                    usd_str = f"${p_usd:,} / мес.".replace(",", " ")
                    byn_str = f"{p_byn:,} BYN".replace(",", " ")
                except Exception:
                    usd_str = "Договорная"
                    byn_str = ""

                # Локация
                acc_params = item.get("account_parameters", [])
                address = "Минск"
                for p in acc_params:
                    if p.get("p") == "address":
                        address = p.get("v", address)
                        break

                # Комнаты
                params = item.get("ad_parameters", [])
                rooms_raw = None
                for p in params:
                    if p.get("p") == "rooms":
                        rooms_raw = p.get("v")
                        break

                rooms_str = format_rooms(rooms_raw)
                subject = item.get("subject") or f"{rooms_str} квартира"

                # Фото
                image_url = None
                images = item.get("images", [])
                if images:
                    first_img = images[0]
                    img_id = first_img.get("id")
                    img_path = first_img.get("path")
                    if img_path:
                        image_url = f"https://rms.kufar.by/v1/list_thumbs_2x/{img_path}"
                    elif img_id:
                        image_url = f"https://rms.kufar.by/v1/list_thumbs_2x/{img_id[:2]}/{img_id}.jpg"

                link = item.get("ad_link") or f"https://www.kufar.by/item/{ad_id}"

                listings.append(
                    RentalListing(
                        uid=f"kufar_{ad_id}",
                        source="Kufar",
                        source_badge="🟢 Kufar",
                        title=subject,
                        price_usd_str=usd_str,
                        price_byn_str=byn_str,
                        location=address,
                        rooms_str=rooms_str,
                        link=link,
                        image_url=image_url,
                        description=None,  # Подгружается отдельно при публикации
                    )
                )
        except Exception as e:
            logger.error("Error fetching Kufar rentals: %s", e)
        return listings

    # ------------------- ONLINER FETCHER -------------------
    async def fetch_onliner(self, limit: int = 12) -> List[RentalListing]:
        listings = []
        try:
            session = await self.get_session()
            url = (
                f"https://r.onliner.by/sdapi/ak.api/search/apartments"
                f"?price[min]=100&price[max]=3000&currency=usd&order=created_at:desc"
            )
            async with session.get(url, headers=HEADERS_ONLINER) as resp:
                if resp.status != 200:
                    logger.warning("Onliner rent fetch failed with status %s", resp.status)
                    return []
                data = await resp.json()

            apts = data.get("apartments", [])
            for apt in apts:
                # Фильтр: ТОЛЬКО СОБСТВЕННИКИ
                contact = apt.get("contact", {})
                if contact.get("owner") is not True:
                    continue

                apt_id = str(apt.get("id", ""))
                if not apt_id:
                    continue

                rent_type = apt.get("rent_type")
                rooms_str = format_rooms(rent_type)
                title = f"{rooms_str} квартира" if rent_type != "room" else "Комната в Минске"

                # Цены
                try:
                    usd_amount = int(float(apt.get("price", {}).get("converted", {}).get("USD", {}).get("amount", 0)))
                    byn_amount = int(float(apt.get("price", {}).get("converted", {}).get("BYN", {}).get("amount", 0)))
                    usd_str = f"${usd_amount:,} / мес.".replace(",", " ")
                    byn_str = f"{byn_amount:,} BYN".replace(",", " ")
                except Exception:
                    usd_str = "Договорная"
                    byn_str = ""

                # Локация
                loc = apt.get("location", {})
                user_addr = loc.get("user_address") or loc.get("address") or "Минск"

                link = apt.get("url") or f"https://r.onliner.by/ak/apartments/{apt_id}"
                photo = apt.get("photo")

                listings.append(
                    RentalListing(
                        uid=f"onliner_{apt_id}",
                        source="Onliner",
                        source_badge="🟡 Onliner",
                        title=title,
                        price_usd_str=usd_str,
                        price_byn_str=byn_str,
                        location=user_addr,
                        rooms_str=rooms_str,
                        link=link,
                        image_url=photo,
                        description=None,
                    )
                )
                if len(listings) >= limit:
                    break
        except Exception as e:
            logger.error("Error fetching Onliner rentals: %s", e)
        return listings

    # ------------------- REALT.BY FETCHER -------------------
    async def fetch_realt(self, limit: int = 15) -> List[RentalListing]:
        listings = []
        try:
            session = await self.get_session()
            url = "https://realt.by/rent/flat-for-long/"
            async with session.get(url, headers=HEADERS_BROWSER, timeout=aiohttp.ClientTimeout(total=20, connect=10)) as resp:
                if resp.status != 200:
                    logger.warning("Realt rent fetch failed with status %s", resp.status)
                    return []
                html = await resp.text()

            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
            if not m:
                logger.warning("Realt __NEXT_DATA__ not found in response")
                return []

            next_data = json.loads(m.group(1))
            props = next_data.get("props", {}).get("pageProps", {})
            objects = props.get("objects", [])

            for obj in objects:
                # Фильтр: ТОЛЬКО СОБСТВЕННИКИ (нет имени агентства и нет uuid агентства)
                if obj.get("agencyName") or obj.get("agencyUuid"):
                    continue

                code = str(obj.get("code", ""))
                if not code:
                    continue

                rooms = obj.get("rooms")
                rooms_str = format_rooms(rooms)
                title = f"{rooms_str} квартира"

                rates = obj.get("priceRates", {})
                # ISO: '840' is USD, '933' is BYN
                usd_val = rates.get("840")
                byn_val = rates.get("933")
                usd_str = f"${int(usd_val):,} / мес.".replace(",", " ") if usd_val else "Договорная"
                byn_str = f"{int(byn_val):,} BYN".replace(",", " ") if byn_val else ""

                address = obj.get("address") or "Минск"
                link = f"https://realt.by/rent/flat-for-long/object/{code}/"

                images = obj.get("images", [])
                image_url = images[0] if images else None

                story = obj.get("story")
                desc = None
                if story and isinstance(story, str):
                    desc = story.strip()

                listings.append(
                    RentalListing(
                        uid=f"realt_{code}",
                        source="Realt.by",
                        source_badge="🔵 Realt.by",
                        title=title,
                        price_usd_str=usd_str,
                        price_byn_str=byn_str,
                        location=address,
                        rooms_str=rooms_str,
                        link=link,
                        image_url=image_url,
                        description=desc,
                    )
                )
                if len(listings) >= limit:
                    break
        except Exception as e:
            logger.error("Error fetching Realt rentals: %s", e)
        return listings

    # ------------------- FETCH ALL CONCURRENTLY -------------------
    async def fetch_all_fresh(self) -> List[RentalListing]:
        results = await asyncio.gather(
            self.fetch_kufar(limit=8),
            self.fetch_onliner(limit=10),
            self.fetch_realt(limit=12),
            return_exceptions=True,
        )

        all_listings: List[RentalListing] = []
        for res in results:
            if isinstance(res, list):
                all_listings.extend(res)
            elif isinstance(res, Exception):
                logger.error("Fetcher error in gather: %s", res)

        return all_listings
