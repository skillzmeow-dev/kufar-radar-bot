import aiohttp
import logging
import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

API_URL = "https://api.kufar.by/search-api/v2/search/rendered-paginated"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://www.kufar.by",
    "Referer": "https://www.kufar.by/",
}


@dataclass
class KufarAd:
    ad_id: int
    title: str
    body: str
    price_byn_str: str
    price_usd_str: str
    price_byn_num: float
    price_usd_num: float
    link: str
    image_url: Optional[str]
    location: str
    time_str: str
    is_company: bool
    account_id: str
    smart_details: str


def format_price(kopecks_str: Optional[str], currency: str = "BYN") -> str:
    if not kopecks_str:
        return "Договорная"
    try:
        val = int(kopecks_str) / 100.0
        if val <= 0:
            return "Договорная / Бесплатно"
        if val.is_integer():
            return f"{int(val):,} {currency}".replace(",", " ")
        return f"{val:,.2f} {currency}".replace(",", " ")
    except (ValueError, TypeError):
        return "Договорная"


def extract_location(params: List[Dict[str, Any]]) -> str:
    region = ""
    area = ""
    address = ""
    for p in params:
        pu = p.get("pu")
        vl = p.get("vl", "")
        if pu == "rgn":
            region = str(vl)
        elif pu == "ar":
            area = str(vl)
        elif pu == "mto":
            area = f"метро {vl}"
        elif pu == "adrs":
            address = str(vl)

    parts = [p for p in [region, area, address] if p]
    return ", ".join(parts) if parts else "Беларусь"


def extract_image(images: List[Dict[str, Any]]) -> Optional[str]:
    if not images:
        return None
    first = images[0]
    path = first.get("path")
    if not path:
        return None
    storage = first.get("media_storage", "rms")
    if storage == "rms":
        return f"https://rms.kufar.by/v1/gallery/{path}"
    elif first.get("yams_storage"):
        return f"https://yams.kufar.by/api/v1/kufar-ads/images/{path[:2]}/{path}.jpg"
    return f"https://rms.kufar.by/v1/gallery/{path}"


def extract_smart_details(subject: str, body: str, params: List[Dict[str, Any]], category_id: int) -> str:
    """Извлекает ключевые маркеры (АКБ, нюансы, комплект, этаж, метро) для перекупов и арендаторов."""
    text = f"{subject} {body}".lower()
    details = []

    # 1. Поиск АКБ (Battery Health) для техники
    battery_match = re.search(
        r"(?:акб|батаре[яеи]|емкост[ьи]|аккумулятор|battery|health)\D{0,10}?(\d{2,3})\s*%?",
        text,
    )
    if battery_match:
        pct = int(battery_match.group(1))
        if 40 <= pct <= 100:
            emoji = "🔋" if pct >= 80 else "🪫"
            details.append(f"{emoji} <b>АКБ:</b> {pct}%")

    # 2. Нюансы и ремонт
    if re.search(r"\b(трещин\w*|разбит\w*|скол\w*|дефект\w*|полос\w*)\b", text):
        details.append("⚠️ <b>Есть дефекты/сколы</b>")
    elif re.search(r"\b(в\s*идеале|идеальн\w*|нов[ыо][ей]|отличн\w*)\b", text):
        details.append("✨ <b>Состояние:</b> Идеал/Отличное")

    if re.search(r"\b(заменен\w* (?:дисплей|экран|акб|батаре)|менял\w*)\b", text):
        details.append("🔧 <b>Был ремонт/замена</b>")

    # 3. Комплект
    set_items = []
    if "коробк" in text:
        set_items.append("коробка")
    if "чек" in text:
        set_items.append("чек")
    if "гаранти" in text:
        set_items.append("гарантия")
    if set_items:
        details.append(f"📦 <b>Комплект:</b> {', '.join(set_items)}")

    # 4. Недвижимость
    if category_id == 1010 or "квартир" in text:
        floor_match = re.search(r"(\d+)\s*/\s*(\d+)\s*(?:эт|этаж)", text)
        if floor_match:
            details.append(f"🏢 <b>Этаж:</b> {floor_match.group(1)}/{floor_match.group(2)}")

        if re.search(r"(?:можно|разрешено)\s*(?:с\s*)?(?:животн|собак|кош)", text):
            details.append("🐾 <b>Можно с животными</b>")
        elif re.search(r"(?:без|нельзя|запрещено)\s*(?:с\s*)?(?:животн|собак|кош)", text):
            details.append("🚫 <b>Без животных</b>")

        if re.search(r"без\s*залога", text):
            details.append("🟢 <b>Без залога</b>")
        elif "залог" in text:
            details.append("⚠️ <b>Есть залог</b>")

    if not details:
        return ""

    return "🔍 <b>Детали лота:</b> " + " | ".join(details)


class KufarClient:
    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._own_session = False

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=DEFAULT_HEADERS)
            self._own_session = True
        return self._session

    async def close(self):
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    async def fetch_ad_body(self, ad_link: str) -> str:
        """Подгружает реальное описание товара со страницы объявления."""
        session = await self._get_session()
        try:
            async with session.get(ad_link, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    m = re.search(r'itemProp="description"[^>]*>(.*?)</div>', text, re.DOTALL)
                    if m:
                        clean = re.sub(r"<br\s*/?>", "\n", m.group(1))
                        clean = re.sub(r"<[^>]+>", "", clean).strip()
                        return clean
        except Exception as e:
            logger.debug("Failed to fetch full ad body: %s", e)
        return ""

    async def fetch_ads(
        self,
        query: Optional[str] = None,
        category_id: Optional[int] = None,
        region_id: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        currency: str = "BYN",
        rooms: Optional[str] = None,
        seller_id: Optional[str] = None,
        only_owner: bool = False,
        size: int = 15,
    ) -> List[KufarAd]:
        session = await self._get_session()
        params: Dict[str, Any] = {
            "sort": "lst.d",
            "size": str(size),
        }

        # Отслеживание конкретного продавца
        if seller_id and seller_id.strip():
            clean_seller = seller_id.strip().split("/")[-1].split("?")[0]
            params["atid"] = clean_seller

        if query and query.strip():
            params["query"] = query.strip()

        if category_id and category_id > 0:
            params["cat"] = str(category_id)
            if category_id == 1010:  # Аренда квартир
                params["typ"] = "let"

        if region_id and region_id > 0:
            params["rgn"] = str(region_id)

        # Комнаты (например: rms=v.or:1,2)
        if rooms and rooms.strip():
            clean_rms = rooms.replace(" ", "")
            params["rms"] = f"v.or:{clean_rms}"

        if only_owner:
            params["cmp"] = "0"

        # Фильтр по цене (в копейках)
        # Если валюта USD — Куфар фильтрует через prc для BYN, поэтому конвертируем по курсу ~3.3 BYN/USD
        rate = 3.3 if currency.upper() == "USD" else 1.0

        if min_price is not None or max_price is not None:
            min_kop = int((min_price or 0) * rate) * 100
            max_kop = int(max_price * rate) * 100 if max_price else 999999999
            params["prc"] = f"r:{min_kop},{max_kop}"

        try:
            async with session.get(API_URL, params=params, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status != 200:
                    logger.warning("Kufar API error: status %s for params %s", resp.status, params)
                    return []
                data = await resp.json()

            raw_ads = data.get("ads", [])
            results: List[KufarAd] = []

            for item in raw_ads:
                ad_id = int(item.get("ad_id", 0))
                if not ad_id:
                    continue

                price_byn_k = item.get("price_byn", "0")
                price_usd_k = item.get("price_usd", "0")

                byn_str = format_price(price_byn_k, "BYN")
                usd_str = format_price(price_usd_k, "$")

                try:
                    num_byn = int(price_byn_k) / 100.0
                except (ValueError, TypeError):
                    num_byn = 0.0

                try:
                    num_usd = int(price_usd_k) / 100.0
                except (ValueError, TypeError):
                    num_usd = 0.0

                time_raw = item.get("list_time", "")
                try:
                    dt = datetime.fromisoformat(time_raw.replace("Z", "+00:00"))
                    time_str = dt.strftime("%H:%M")
                except Exception:
                    time_str = "сегодня"

                ad_params = item.get("ad_parameters", [])
                subject = item.get("subject", "Без названия")
                body = item.get("body_short") or item.get("body") or ""

                smart = extract_smart_details(
                    subject=subject,
                    body=body,
                    params=ad_params,
                    category_id=category_id or int(item.get("category", 0)),
                )

                ad = KufarAd(
                    ad_id=ad_id,
                    title=subject,
                    body=body,
                    price_byn_str=byn_str,
                    price_usd_str=usd_str,
                    price_byn_num=num_byn,
                    price_usd_num=num_usd,
                    link=item.get("ad_link", f"https://www.kufar.by/item/{ad_id}"),
                    image_url=extract_image(item.get("images", [])),
                    location=extract_location(ad_params),
                    time_str=time_str,
                    is_company=bool(item.get("company_ad", False)),
                    account_id=str(item.get("account_id", "")),
                    smart_details=smart,
                )
                results.append(ad)

            return results
        except Exception as e:
            logger.error("Error fetching Kufar ads: %s", e)
            return []
