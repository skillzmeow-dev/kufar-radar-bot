import aiosqlite
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    show_photo INTEGER DEFAULT 1,
                    show_desc INTEGER DEFAULT 1,
                    show_smart INTEGER DEFAULT 1,
                    currency TEXT DEFAULT 'BOTH',
                    sound INTEGER DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    query TEXT,
                    category_id INTEGER DEFAULT 0,
                    region_id INTEGER DEFAULT 0,
                    min_price INTEGER DEFAULT 0,
                    max_price INTEGER DEFAULT 0,
                    currency TEXT DEFAULT 'BYN',
                    rooms TEXT,
                    seller_id TEXT,
                    only_owner INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_ads (
                    ad_id INTEGER PRIMARY KEY,
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS blocked_sellers (
                    user_id INTEGER NOT NULL,
                    seller_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, seller_id)
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS channel_seen_ads (
                    ad_uid TEXT PRIMARY KEY,
                    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_active ON tasks (is_active);"
            )
            # Автоматическая миграция недостающих колонок
            cursor = await db.execute("PRAGMA table_info(tasks);")
            existing_cols = {row[1] for row in await cursor.fetchall()}
            for col_name, col_def in [
                ("currency", "TEXT DEFAULT 'BYN'"),
                ("rooms", "TEXT"),
                ("seller_id", "TEXT"),
            ]:
                if col_name not in existing_cols:
                    await db.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_def};")

            await db.commit()
            logger.info("Database initialized successfully at %s", self.db_path)

    async def add_user(self, user_id: int, username: Optional[str], full_name: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO users (user_id, username, full_name)
                VALUES (?, ?, ?);
                """,
                (user_id, username, full_name),
            )
            await db.execute(
                """
                INSERT OR IGNORE INTO user_settings (user_id)
                VALUES (?);
                """,
                (user_id,),
            )
            await db.commit()

    async def get_user_settings(self, user_id: int) -> Dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM user_settings WHERE user_id = ?;",
                (user_id,),
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            # Если нет — создаем дефолтные
            await db.execute(
                "INSERT OR IGNORE INTO user_settings (user_id) VALUES (?);",
                (user_id,),
            )
            await db.commit()
            return {
                "user_id": user_id,
                "show_photo": 1,
                "show_desc": 1,
                "show_smart": 1,
                "currency": "BOTH",
                "sound": 1,
            }

    async def toggle_setting(self, user_id: int, setting_name: str) -> Any:
        settings = await self.get_user_settings(user_id)
        current = settings.get(setting_name, 1)

        async with aiosqlite.connect(self.db_path) as db:
            if setting_name == "currency":
                # Переключение BOTH -> BYN -> USD -> BOTH
                cycle = {"BOTH": "BYN", "BYN": "USD", "USD": "BOTH"}
                new_val = cycle.get(str(current), "BOTH")
            else:
                new_val = 0 if current == 1 else 1

            await db.execute(
                f"UPDATE user_settings SET {setting_name} = ? WHERE user_id = ?;",
                (new_val, user_id),
            )
            await db.commit()
            return new_val

    async def add_task(
        self,
        user_id: int,
        title: str,
        query: Optional[str] = "",
        category_id: int = 0,
        region_id: int = 0,
        min_price: int = 0,
        max_price: int = 0,
        currency: str = "BYN",
        rooms: Optional[str] = None,
        seller_id: Optional[str] = None,
        only_owner: bool = False,
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO tasks (
                    user_id, title, query, category_id, region_id,
                    min_price, max_price, currency, rooms, seller_id,
                    only_owner, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
                """,
                (
                    user_id,
                    title,
                    query or "",
                    category_id,
                    region_id,
                    min_price,
                    max_price,
                    currency,
                    rooms,
                    seller_id,
                    1 if only_owner else 0,
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_user_tasks(self, user_id: int) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM tasks WHERE user_id = ? ORDER BY id DESC;
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_task_by_id(self, task_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE id = ? AND user_id = ?;",
                (task_id, user_id),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def delete_task(self, task_id: int, user_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM tasks WHERE id = ? AND user_id = ?;",
                (task_id, user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def toggle_task(self, task_id: int, user_id: int) -> Optional[bool]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT is_active FROM tasks WHERE id = ? AND user_id = ?;",
                (task_id, user_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            new_status = 0 if row[0] == 1 else 1
            await db.execute(
                "UPDATE tasks SET is_active = ? WHERE id = ? AND user_id = ?;",
                (new_status, task_id, user_id),
            )
            await db.commit()
            return bool(new_status)

    async def toggle_all_tasks(self, user_id: int, activate: bool) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            val = 1 if activate else 0
            cursor = await db.execute(
                "UPDATE tasks SET is_active = ? WHERE user_id = ?;",
                (val, user_id),
            )
            await db.commit()
            return cursor.rowcount

    async def get_all_active_tasks(self) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE is_active = 1;"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def block_seller(self, user_id: int, seller_id: str) -> bool:
        if not seller_id:
            return False
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO blocked_sellers (user_id, seller_id) VALUES (?, ?);",
                (user_id, seller_id),
            )
            await db.commit()
            return True

    async def is_seller_blocked(self, user_id: int, seller_id: str) -> bool:
        if not seller_id:
            return False
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM blocked_sellers WHERE user_id = ? AND seller_id = ?;",
                (user_id, seller_id),
            )
            return await cursor.fetchone() is not None

    async def get_blocked_sellers_count(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM blocked_sellers WHERE user_id = ?;",
                (user_id,),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def clear_blocked_sellers(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM blocked_sellers WHERE user_id = ?;",
                (user_id,),
            )
            await db.commit()
            return cursor.rowcount

    async def filter_unseen_ads(self, ad_ids: List[int]) -> List[int]:
        if not ad_ids:
            return []
        async with aiosqlite.connect(self.db_path) as db:
            placeholders = ",".join(["?"] * len(ad_ids))
            cursor = await db.execute(
                f"SELECT ad_id FROM seen_ads WHERE ad_id IN ({placeholders});",
                ad_ids,
            )
            seen = {row[0] for row in await cursor.fetchall()}
            return [aid for aid in ad_ids if aid not in seen]

    async def mark_ads_seen(self, ad_ids: List[int]):
        if not ad_ids:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                "INSERT OR IGNORE INTO seen_ads (ad_id) VALUES (?);",
                [(aid,) for aid in ad_ids],
            )
            await db.commit()

    async def filter_unseen_channel_ads(self, ad_uids: List[str]) -> List[str]:
        if not ad_uids:
            return []
        async with aiosqlite.connect(self.db_path) as db:
            placeholders = ",".join(["?"] * len(ad_uids))
            cursor = await db.execute(
                f"SELECT ad_uid FROM channel_seen_ads WHERE ad_uid IN ({placeholders});",
                ad_uids,
            )
            seen = {row[0] for row in await cursor.fetchall()}
            return [uid for uid in ad_uids if uid not in seen]

    async def mark_channel_ads_seen(self, ad_uids: List[str]):
        if not ad_uids:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                "INSERT OR IGNORE INTO channel_seen_ads (ad_uid) VALUES (?);",
                [(uid,) for uid in ad_uids],
            )
            await db.commit()

    # ------------------- МЕТОДЫ АДМИН-ПАНЕЛИ -------------------
    async def get_admin_stats(self) -> Dict[str, Any]:
        import os
        db_size_kb = 0
        if os.path.exists(self.db_path):
            db_size_kb = round(os.path.getsize(self.db_path) / 1024, 1)

        async with aiosqlite.connect(self.db_path) as db:
            # Всего пользователей
            c = await db.execute("SELECT COUNT(*) FROM users;")
            total_users = (await c.fetchone())[0]

            # Новых за 24 часа
            c = await db.execute(
                "SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', '-1 day');"
            )
            users_24h = (await c.fetchone())[0]

            # Всего задач и активных задач
            c = await db.execute("SELECT COUNT(*), SUM(is_active) FROM tasks;")
            row = await c.fetchone()
            total_tasks = row[0] or 0
            active_tasks = row[1] or 0

            # Всего просмотренных объявлений
            c = await db.execute("SELECT COUNT(*) FROM seen_ads;")
            total_seen = (await c.fetchone())[0]

            # Заблокированных продавцов всего
            c = await db.execute("SELECT COUNT(*) FROM blocked_sellers;")
            total_blocked = (await c.fetchone())[0]

            return {
                "total_users": total_users,
                "users_24h": users_24h,
                "total_tasks": total_tasks,
                "active_tasks": active_tasks,
                "total_seen": total_seen,
                "total_blocked": total_blocked,
                "db_size_kb": db_size_kb,
            }

    async def get_recent_users(self, limit: int = 8) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT u.user_id, u.username, u.full_name, u.created_at,
                       COUNT(t.id) as task_count
                FROM users u
                LEFT JOIN tasks t ON u.user_id = t.user_id
                GROUP BY u.user_id
                ORDER BY u.created_at DESC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_top_queries(self, limit: int = 6) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT title, COUNT(*) as cnt
                FROM tasks
                GROUP BY title
                ORDER BY cnt DESC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_all_user_ids(self) -> List[int]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT user_id FROM users;")
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
