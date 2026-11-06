import pytest
from coastal_miles.db import Database


@pytest.fixture
async def db():
    d = Database(":memory:")
    await d.connect()
    yield d
    await d.close()


async def test_balance_and_rank(db):
    await db.add(1, 10, 50, "a")
    await db.add(1, 11, 80, "a")
    await db.add(1, 10, -20, "b")
    assert await db.balance(1, 10) == 30
    assert await db.rank(1, 11) == 1
    assert await db.rank(1, 10) == 2
    assert await db.rank(1, 99) is None


async def test_leaderboard_period(db):
    await db.add(1, 10, 100, "old", now=1000)
    await db.add(1, 11, 5, "new", now=5000)
    assert [r[0] for r in await db.leaderboard(1, None, 10)] == [10, 11]
    assert [r[0] for r in await db.leaderboard(1, 2000, 10)] == [11]


async def test_guilds_isolated(db):
    await db.add(1, 10, 5, "x")
    assert await db.balance(2, 10) == 0


async def test_message_cooldown(db):
    assert await db.try_message_award(1, 10, 60, now=1000)
    assert not await db.try_message_award(1, 10, 60, now=1030)
    assert await db.try_message_award(1, 10, 60, now=1061)


async def test_daily_streak(db):
    assert await db.claim_daily(1, 10, 100) == (1, False)
    assert await db.claim_daily(1, 10, 100) == (1, True)
    assert await db.claim_daily(1, 10, 101) == (2, False)
    assert await db.claim_daily(1, 10, 103) == (1, False)  # missed a day


async def test_milestones(db):
    await db.set_milestone(1, 500, 7)
    await db.set_milestone(1, 100, 6)
    assert await db.milestones(1) == [(100, 6), (500, 7)]
    assert await db.remove_milestone(1, 100)
    assert not await db.remove_milestone(1, 100)
