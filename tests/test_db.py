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


async def test_cooldowns_are_per_kind(db):
    assert await db.try_claim(1, 10, "message", 10, now=1000)
    assert not await db.try_claim(1, 10, "message", 10, now=1005)
    assert await db.try_claim(1, 10, "image", 5, now=1005)  # separate cooldown
    assert await db.try_claim(1, 10, "message", 10, now=1011)
    assert await db.try_claim(1, 11, "message", 10, now=1005)  # other user unaffected


async def test_earn_channels(db):
    assert await db.channels(1) == set()
    await db.add_channel(1, 5)
    await db.add_channel(1, 5)
    await db.add_channel(1, 6)
    assert await db.channels(1) == {5, 6}
    assert await db.channels(2) == set()
    assert await db.remove_channel(1, 5)
    assert not await db.remove_channel(1, 5)


async def test_tier_roles(db):
    await db.set_tier_role(1, "Shoreline", 6)
    await db.set_tier_role(1, "Tidecaller", 7)
    await db.set_tier_role(1, "Shoreline", 8)
    assert await db.tier_roles(1) == {"Shoreline": 8, "Tidecaller": 7}
    assert await db.clear_tier_role(1, "Shoreline")
    assert not await db.clear_tier_role(1, "Shoreline")
