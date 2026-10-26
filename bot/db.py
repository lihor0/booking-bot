import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import aiosqlite

FMT = "%Y-%m-%d %H:%M"

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    client_name TEXT    NOT NULL,
    phone       TEXT    NOT NULL,
    service_id  TEXT    NOT NULL,
    start_ts    TEXT    NOT NULL,
    end_ts      TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'active',
    reminded    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bookings_start ON bookings(start_ts);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id);

CREATE TABLE IF NOT EXISTS blocked_days (
    day TEXT PRIMARY KEY
);
"""


class SlotTaken(Exception):
    """Время уже занято другой записью."""


@dataclass(frozen=True)
class Booking:
    id: int
    user_id: int
    client_name: str
    phone: str
    service_id: str
    start: datetime
    end: datetime
    status: str


def _to_booking(row: aiosqlite.Row) -> Booking:
    return Booking(
        id=row["id"],
        user_id=row["user_id"],
        client_name=row["client_name"],
        phone=row["phone"],
        service_id=row["service_id"],
        start=datetime.strptime(row["start_ts"], FMT),
        end=datetime.strptime(row["end_ts"], FMT),
        status=row["status"],
    )


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        # Сериализует проверку пересечения и вставку, чтобы два клиента не заняли один слот
        self._write_lock = asyncio.Lock()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() не вызван")
        return self._conn

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _fetch(self, sql: str, params: tuple = ()) -> list[Booking]:
        async with self.conn.execute(sql, params) as cur:
            return [_to_booking(row) for row in await cur.fetchall()]

    # --- записи ---

    async def create_booking(
        self,
        user_id: int,
        client_name: str,
        phone: str,
        service_id: str,
        start: datetime,
        end: datetime,
        reminded: bool = False,
    ) -> Booking:
        async with self._write_lock:
            async with self.conn.execute(
                "SELECT 1 FROM bookings WHERE status = 'active' AND start_ts < ? AND end_ts > ? LIMIT 1",
                (end.strftime(FMT), start.strftime(FMT)),
            ) as cur:
                if await cur.fetchone():
                    raise SlotTaken
            cur = await self.conn.execute(
                "INSERT INTO bookings (user_id, client_name, phone, service_id, start_ts, end_ts, reminded)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, client_name, phone, service_id, start.strftime(FMT), end.strftime(FMT), int(reminded)),
            )
            await self.conn.commit()
            return Booking(cur.lastrowid, user_id, client_name, phone, service_id, start, end, "active")

    async def get_booking(self, booking_id: int) -> Booking | None:
        rows = await self._fetch("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        return rows[0] if rows else None

    async def cancel_booking(self, booking_id: int) -> Booking | None:
        """Отменяет активную запись. Возвращает её или None, если отменять нечего."""
        booking = await self.get_booking(booking_id)
        if booking is None or booking.status != "active":
            return None
        await self.conn.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
        await self.conn.commit()
        return booking

    async def busy_intervals(self, day: date) -> list[tuple[datetime, datetime]]:
        return [(b.start, b.end) for b in await self.bookings_for_day(day)]

    async def bookings_for_day(self, day: date) -> list[Booking]:
        next_day = day + timedelta(days=1)
        return await self._fetch(
            "SELECT * FROM bookings WHERE status = 'active' AND start_ts >= ? AND start_ts < ? ORDER BY start_ts",
            (f"{day:%Y-%m-%d} 00:00", f"{next_day:%Y-%m-%d} 00:00"),
        )

    async def upcoming(self, now: datetime, user_id: int | None = None, limit: int = 50) -> list[Booking]:
        sql = "SELECT * FROM bookings WHERE status = 'active' AND start_ts >= ?"
        params: tuple = (now.strftime(FMT),)
        if user_id is not None:
            sql += " AND user_id = ?"
            params += (user_id,)
        sql += " ORDER BY start_ts LIMIT ?"
        return await self._fetch(sql, params + (limit,))

    async def last_contact(self, user_id: int) -> tuple[str, str] | None:
        """Имя и телефон из последней записи клиента — чтобы не спрашивать повторно."""
        async with self.conn.execute(
            "SELECT client_name, phone FROM bookings WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return (row["client_name"], row["phone"]) if row else None

    # --- напоминания ---

    async def due_reminders(self, now: datetime, until: datetime) -> list[Booking]:
        return await self._fetch(
            "SELECT * FROM bookings WHERE status = 'active' AND reminded = 0 AND start_ts > ? AND start_ts <= ?",
            (now.strftime(FMT), until.strftime(FMT)),
        )

    async def mark_reminded(self, booking_id: int) -> None:
        await self.conn.execute("UPDATE bookings SET reminded = 1 WHERE id = ?", (booking_id,))
        await self.conn.commit()

    # --- закрытые дни ---

    async def block_day(self, day: date) -> None:
        await self.conn.execute("INSERT OR IGNORE INTO blocked_days (day) VALUES (?)", (day.isoformat(),))
        await self.conn.commit()

    async def unblock_day(self, day: date) -> None:
        await self.conn.execute("DELETE FROM blocked_days WHERE day = ?", (day.isoformat(),))
        await self.conn.commit()

    async def blocked_days(self) -> set[date]:
        async with self.conn.execute("SELECT day FROM blocked_days") as cur:
            return {date.fromisoformat(row["day"]) for row in await cur.fetchall()}
