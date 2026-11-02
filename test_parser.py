import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from kufar_client import KufarClient


async def main():
    print("=" * 60)
    print("🔎 ТЕСТ ПАРСЕРА KUFAR.BY")
    print("=" * 60)

    client = KufarClient()

    # 1. Поиск iPhone до 1000 BYN
    print("\n[1] Поиск: iPhone (до 1000 BYN)...")
    ads = await client.fetch_ads(query="iphone", max_price_byn=1000, size=3)
    if not ads:
        print("❌ Объявления не найдены или ошибка соединения")
    for i, ad in enumerate(ads, 1):
        print(f" {i}. [{ad.time_str}] {ad.title}")
        print(f"    💰 Цена: {ad.price_byn_str} ({ad.price_usd_str})")
        print(f"    📍 Локация: {ad.location}")
        print(f"    🔗 Ссылка: {ad.link}")
        print(f"    🖼 Фото: {ad.image_url or 'Нет'}")

    # 2. Аренда квартир в Минске от собственника
    print("\n[2] Поиск: Аренда квартир в Минске (собственник)...")
    rent_ads = await client.fetch_ads(category_id=1010, region_id=7, only_owner=True, size=2)
    for i, ad in enumerate(rent_ads, 1):
        print(f" {i}. [{ad.time_str}] {ad.title}")
        print(f"    💰 Цена: {ad.price_byn_str} ({ad.price_usd_str})")
        print(f"    📍 Локация: {ad.location}")
        print(f"    🔗 Ссылка: {ad.link}")

    await client.close()
    print("\n✅ Тест успешно завершен!")


if __name__ == "__main__":
    asyncio.run(main())
