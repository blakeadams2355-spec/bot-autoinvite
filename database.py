import aiosqlite
import json
from datetime import datetime
from typing import Optional, List, Dict
from collections import Counter
from config import config


class Database:
    def __init__(self, db_path: str = config.DATABASE_PATH):
        self.db_path = db_path

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id INTEGER PRIMARY KEY,
                    title TEXT,
                    auto_accept BOOLEAN DEFAULT 1,
                    accepted_count INTEGER DEFAULT 0,
                    welcome_message TEXT,
                    schedule TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    full_name TEXT,
                    channel_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    processed_by INTEGER,
                    processed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER,
                    date DATE,
                    accepted INTEGER DEFAULT 0,
                    UNIQUE(channel_id, date)
                )
            ''')

            await db.commit()
            await self._migrate(db)

    async def _migrate(self, db):
        async with db.execute("PRAGMA table_info(channels)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]

        if 'schedule' not in columns:
            await db.execute('ALTER TABLE channels ADD COLUMN schedule TEXT')
            await db.commit()

    # === Каналы ===

    async def add_channel(self, channel_id: int, title: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO channels (channel_id, title, is_active)
                VALUES (?, ?, 1)
                ON CONFLICT(channel_id) DO UPDATE SET title = ?, is_active = 1
            ''', (channel_id, title, title))
            await db.commit()
            return True

    async def save_discovered_channel(self, channel_id: int, title: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO channels (channel_id, title, is_active)
                VALUES (?, ?, 0)
                ON CONFLICT(channel_id) DO UPDATE SET title = ?
            ''', (channel_id, title, title))
            await db.commit()

    async def mark_channel_removed(self, channel_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('UPDATE channels SET is_active = 0 WHERE channel_id = ?', (channel_id,))
            await db.commit()

    async def get_channel(self, channel_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM channels WHERE channel_id = ?', (channel_id,)) as c:
                row = await c.fetchone()
                if row:
                    d = dict(row)
                    if d.get('schedule'):
                        try:
                            d['schedule'] = json.loads(d['schedule'])
                        except:
                            d['schedule'] = None
                    return d
                return None

    async def get_all_channels(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM channels WHERE is_active = 1 ORDER BY title') as c:
                rows = await c.fetchall()
                result = []
                for row in rows:
                    d = dict(row)
                    if d.get('schedule'):
                        try:
                            d['schedule'] = json.loads(d['schedule'])
                        except:
                            d['schedule'] = None
                    result.append(d)
                return result

    async def get_discovered_channels(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM channels ORDER BY title') as c:
                return [dict(row) for row in await c.fetchall()]

    async def get_channels_with_schedule(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                    "SELECT * FROM channels WHERE is_active = 1 AND schedule IS NOT NULL AND schedule != ''"
            ) as c:
                rows = await c.fetchall()
                result = []
                for row in rows:
                    d = dict(row)
                    if d.get('schedule'):
                        try:
                            d['schedule'] = json.loads(d['schedule'])
                            if d['schedule'].get('enabled'):
                                result.append(d)
                        except:
                            pass
                return result

    async def update_channel(self, channel_id: int, **kwargs) -> bool:
        if not kwargs:
            return False

        if 'schedule' in kwargs:
            if kwargs['schedule'] is not None:
                kwargs['schedule'] = json.dumps(kwargs['schedule'], ensure_ascii=False)
            else:
                kwargs['schedule'] = None

        set_clause = ', '.join(f'{k} = ?' for k in kwargs.keys())
        values = list(kwargs.values()) + [channel_id]

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f'UPDATE channels SET {set_clause} WHERE channel_id = ?', values)
            await db.commit()
            return True

    async def increment_accepted(self, channel_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('UPDATE channels SET accepted_count = accepted_count + 1 WHERE channel_id = ?',
                             (channel_id,))
            await db.commit()
            async with db.execute('SELECT accepted_count FROM channels WHERE channel_id = ?', (channel_id,)) as c:
                row = await c.fetchone()
                return row[0] if row else 0

    # === Заявки ===

    async def has_pending_request(self, user_id: int, channel_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                    "SELECT 1 FROM requests WHERE user_id = ? AND channel_id = ? AND status = 'pending' LIMIT 1",
                    (user_id, channel_id)
            ) as c:
                return await c.fetchone() is not None

    async def add_request(self, user_id: int, username: str, full_name: str, channel_id: int) -> Optional[int]:
        if await self.has_pending_request(user_id, channel_id):
            return None

        async with aiosqlite.connect(self.db_path) as db:
            c = await db.execute(
                'INSERT INTO requests (user_id, username, full_name, channel_id) VALUES (?, ?, ?, ?)',
                (user_id, username, full_name, channel_id)
            )
            await db.commit()
            return c.lastrowid

    async def update_request(self, request_id: int, status: str, processed_by: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'UPDATE requests SET status = ?, processed_by = ?, processed_at = ? WHERE id = ?',
                (status, processed_by, datetime.now(), request_id)
            )
            await db.commit()
            return True

    async def get_pending_requests(self, channel_id: int) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                    "SELECT * FROM requests WHERE channel_id = ? AND status = 'pending' ORDER BY created_at",
                    (channel_id,)
            ) as c:
                return [dict(row) for row in await c.fetchall()]

    async def get_pending_count(self, channel_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                    "SELECT COUNT(*) FROM requests WHERE channel_id = ? AND status = 'pending'",
                    (channel_id,)
            ) as c:
                row = await c.fetchone()
                return row[0] if row else 0

    # === Статистика по часам ===

    async def get_hourly_stats(self) -> Dict[int, int]:
        """Возвращает статистику заявок по часам {час: количество}"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT strftime('%H', created_at) as hour, COUNT(*) as count
                FROM requests
                WHERE created_at IS NOT NULL
                GROUP BY hour
                ORDER BY hour
            ''') as c:
                rows = await c.fetchall()
                return {int(row[0]): row[1] for row in rows if row[0]}

    # === Статистика ===

    async def update_stats(self, channel_id: int, accepted: int = 0):
        today = datetime.now().date()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO stats (channel_id, date, accepted) VALUES (?, ?, ?)
                ON CONFLICT(channel_id, date) DO UPDATE SET accepted = accepted + ?
            ''', (channel_id, today, accepted, accepted))
            await db.commit()

    async def get_total_stats(self, channel_id: int) -> Dict:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                    'SELECT COALESCE(SUM(accepted), 0) FROM stats WHERE channel_id = ?',
                    (channel_id,)
            ) as c:
                row = await c.fetchone()
                return {'total_accepted': row[0]}

    async def get_hourly_stats(self, channel_id: int = None) -> Dict[int, int]:
        """Статистика заявок по часам для конкретного канала или всех"""
        async with aiosqlite.connect(self.db_path) as db:
            if channel_id:
                query = '''
                    SELECT strftime('%H', created_at) as hour, COUNT(*) as count
                    FROM requests
                    WHERE channel_id = ? AND created_at IS NOT NULL
                    GROUP BY hour
                    ORDER BY hour
                '''
                params = (channel_id,)
            else:
                query = '''
                    SELECT strftime('%H', created_at) as hour, COUNT(*) as count
                    FROM requests
                    WHERE created_at IS NOT NULL
                    GROUP BY hour
                    ORDER BY hour
                '''
                params = ()

            async with db.execute(query, params) as c:
                rows = await c.fetchall()
                return {int(row[0]): row[1] for row in rows if row[0]}

    async def get_all_requests(self, channel_id: int) -> List[Dict]:
        """Получить все заявки канала (для экспорта)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                    "SELECT * FROM requests WHERE channel_id = ? ORDER BY created_at DESC",
                    (channel_id,)
            ) as c:
                return [dict(row) for row in await c.fetchall()]

    async def is_blacklisted(self, user_id: int, channel_id: int) -> bool:
        return False

    async def is_whitelisted(self, user_id: int, channel_id: int) -> bool:
        return False


db = Database()