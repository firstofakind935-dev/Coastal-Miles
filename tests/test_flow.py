from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from coastal_miles import config
from coastal_miles.bot import Miles, MilesBot
from coastal_miles.db import Database


@pytest.fixture
async def cog():
    bot = MilesBot(Database(":memory:"), [])
    await bot.db.connect()
    yield Miles(bot)
    await bot.db.close()


def message(channel_id=100, images=0, user_id=7, parent_id=None):
    member = MagicMock(spec=discord.Member)
    member.bot, member.id, member.roles = False, user_id, []
    member.guild = NS(id=1, get_role=lambda _: None)
    channel = NS(id=channel_id, parent_id=parent_id, send=AsyncMock())
    atts = [NS(content_type="image/png", filename=f"{i}.png") for i in range(images)]
    return NS(author=member, guild=member.guild, channel=channel, attachments=atts)


async def test_text_message_pays_one_sixteenth(cog):
    await cog.on_message(message())
    assert await cog.bot.db.balance(1, 7) == 4  # 4/64 = 1/16 mile


async def test_image_pays_extra_eighth_per_image(cog):
    await cog.on_message(message(images=2))
    assert await cog.bot.db.balance(1, 7) == 4 + 2 * 8  # message + 2 images


async def test_cooldown_blocks_spam(cog):
    await cog.on_message(message())
    await cog.on_message(message())
    assert await cog.bot.db.balance(1, 7) == 4


async def test_channel_filter_and_threads(cog):
    await cog.bot.db.add_channel(1, 100)
    await cog.on_message(message(channel_id=999, user_id=1))             # not allowed
    await cog.on_message(message(channel_id=555, parent_id=100, user_id=2))  # thread of allowed
    await cog.on_message(message(channel_id=100, user_id=3))            # allowed
    assert await cog.bot.db.balance(1, 1) == 0
    assert await cog.bot.db.balance(1, 2) == 4
    assert await cog.bot.db.balance(1, 3) == 4


async def test_tier_multiplier_applies(cog):
    await cog.bot.db.add(1, 7, config.to_units(500), "seed")  # Preferred, x1.25
    await cog.on_message(message())  # 4 units * 1.25 = 5 exactly
    assert await cog.bot.db.balance(1, 7) == config.to_units(500) + 5


async def test_secret_boost_and_promotion(cog):
    await cog.bot.db.add(1, 7, config.to_units(config.SECRET_BOOST_MILES), "seed")
    await cog.on_message(message())
    assert await cog.bot.db.balance(1, 7) == config.to_units(config.SECRET_BOOST_MILES) + 40


async def test_promotion_announced(cog):
    m = message()
    await cog.bot.db.add(1, 7, config.to_units(500) - 2, "seed")  # just under Preferred
    await cog.on_message(m)
    m.channel.send.assert_awaited_once()
    assert "Preferred" in m.channel.send.await_args.args[0]


# --- /flight ---------------------------------------------------------
from coastal_miles.bot import parse_mention_ids


def test_parse_mentions():
    assert parse_mention_ids("<@111111111111111111> <@!222222222222222222> <@111111111111111111>") == [
        111111111111111111, 222222222222222222]
    assert parse_mention_ids("no one here") == []


def flight_interaction(cog, *, manage=False, role_ids=(), member_ids=()):
    members = {}
    for i in member_ids:
        m = MagicMock(spec=discord.Member)
        m.bot, m.id, m.roles, m.mention = False, i, [], f"<@{i}>"
        m.guild = NS(id=1, get_role=lambda _: None)
        members[i] = m
    user = NS(guild_permissions=NS(manage_guild=manage), roles=[NS(id=r) for r in role_ids])
    return NS(user=user, guild_id=1, guild=NS(get_member=members.get),
              response=NS(send_message=AsyncMock())), members


A, B = 111111111111111111, 222222222222222222


async def test_flight_denied_without_permission(cog):
    it, _ = flight_interaction(cog, member_ids=[A])
    await Miles.flight.callback(cog, it, f"<@{A}>", 500.0)
    assert "Only flight staff" in it.response.send_message.await_args.args[0]
    assert await cog.bot.db.balance(1, A) == 0


async def test_flight_awards_by_distance_to_all_players(cog):
    it, _ = flight_interaction(cog, manage=True, member_ids=[A, B])
    await Miles.flight.callback(cog, it, f"<@{A}> <@{B}>", 250.5, "LAX-JFK")
    assert await cog.bot.db.balance(1, A) == config.to_units(250.5)
    assert await cog.bot.db.balance(1, B) == config.to_units(250.5)
    assert "LAX-JFK" in it.response.send_message.await_args.args[0]


async def test_flight_role_can_award_and_tier_boost_applies(cog):
    await cog.bot.db.add_flight_role(1, 77)
    await cog.bot.db.add(1, A, config.to_units(500), "seed")  # Preferred x1.25
    it, _ = flight_interaction(cog, role_ids=[77], member_ids=[A])
    await Miles.flight.callback(cog, it, f"<@{A}>", 400.0)
    assert await cog.bot.db.balance(1, A) == config.to_units(500) + config.to_units(400) * 5 // 4


async def test_flight_unknown_players(cog):
    it, _ = flight_interaction(cog, manage=True)
    await Miles.flight.callback(cog, it, "<@999999999999999999>", 100.0)
    assert "couldn't find" in it.response.send_message.await_args.args[0]
