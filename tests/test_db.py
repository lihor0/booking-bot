from datetime import date, datetime

import pytest

from bot.db import SlotTaken


def at(h: int, m: int = 0) -> datetime:
    return datetime(2030, 3, 4, h, m)


async def book(db, start, end, user_id=1):
    return await db.create_booking(user_id, "Иван", "+79001234567", "haircut", start, end)


async def test_create_and_overlap(db):
    await book(db, at(12), at(13))
    with pytest.raises(SlotTaken):
        await book(db, at(12, 30), at(13, 30), user_id=2)
    # Встык — можно
    await book(db, at(13), at(14), user_id=2)
    assert await db.busy_intervals(date(2030, 3, 4)) == [(at(12), at(13)), (at(13), at(14))]


async def test_cancel_frees_slot(db):
    b = await book(db, at(12), at(13))
    assert (await db.cancel_booking(b.id)).id == b.id
    assert await db.cancel_booking(b.id) is None  # повторная отмена
    await book(db, at(12), at(13), user_id=2)


async def test_upcoming_for_user(db):
    await book(db, at(10), at(11), user_id=1)
    await book(db, at(15), at(16), user_id=2)
    await book(db, at(17), at(18), user_id=1)
    mine = await db.upcoming(at(12), user_id=1)
    assert [b.start for b in mine] == [at(17)]


async def test_reminders(db):
    soon = await book(db, at(14), at(15))
    await book(db, at(18), at(19))
    due = await db.due_reminders(at(12, 30), at(14, 30))
    assert [b.id for b in due] == [soon.id]
    await db.mark_reminded(soon.id)
    assert await db.due_reminders(at(12, 30), at(14, 30)) == []


async def test_last_contact(db):
    assert await db.last_contact(1) is None
    await book(db, at(10), at(11))
    assert await db.last_contact(1) == ("Иван", "+79001234567")


async def test_blocked_days(db):
    d = date(2030, 3, 4)
    await db.block_day(d)
    await db.block_day(d)  # идемпотентно
    assert await db.blocked_days() == {d}
    await db.unblock_day(d)
    assert await db.blocked_days() == set()
