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
