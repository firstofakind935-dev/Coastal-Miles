from __future__ import annotations

import csv
import io
import logging
import random
import re
import time

import discord
from discord import app_commands
from discord.ext import commands

from . import config
from .config import fmt_miles
from .db import Database

log = logging.getLogger("coastal_miles")

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic", ".avif")


def apply_multiplier(amount: int, mult: float, rand=random.random) -> int:
    """Scale an integer amount. Any fraction is rounded up with matching probability,
    so the long-run average is exact."""
    scaled = amount * mult
    whole = int(scaled)
    if rand() < scaled - whole:
        whole += 1
    return whole


def count_images(message: discord.Message) -> int:
    n = 0
    for a in message.attachments:
        ctype = (a.content_type or "").lower()
        if ctype.startswith("image/") or a.filename.lower().endswith(IMAGE_EXTS):
            n += 1
    return min(n, config.IMAGES_PER_MESSAGE_CAP)


def parse_mention_ids(text: str) -> list[int]:
    """User IDs from <@id> / <@!id> mentions (or bare IDs), in order, de-duplicated."""
    seen: dict[int, None] = {}
    for m in re.finditer(r"<@!?(\d{15,25})>|\b(\d{15,25})\b", text):
        seen.setdefault(int(m.group(1) or m.group(2)))
    return list(seen)


def _ts(ts: int) -> str:
    return f"<t:{ts}:R>"


class MilesBot(commands.Bot):
    def __init__(self, db: Database, dev_guild_ids: list[int]):
        intents = discord.Intents.default()  # no privileged intents needed
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.db = db
        self.dev_guild_ids = dev_guild_ids
        self.voice_joined: dict[tuple[int, int], float] = {}

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.add_cog(Miles(self))
        for gid in self.dev_guild_ids:
            guild = discord.Object(gid)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        if not self.dev_guild_ids:
            await self.tree.sync()

    async def close(self) -> None:
        await self.db.close()
        await super().close()

    async def award(self, member: discord.Member, units: int, reason: str,
                    boost: bool = False) -> tuple[int, int, str | None]:
        """Add miles (in units, multiplied if `boost`) and sync tier roles.

        Returns (units_added, new_balance_units, promoted_tier_name_or_None).
        """
        gid = member.guild.id
        before = await self.db.balance(gid, member.id)
        if boost and units > 0:
            units = apply_multiplier(units, config.multiplier_for(config.to_miles(before)))
        if units == 0:
            return 0, before, None
        after = await self.db.add(gid, member.id, units, reason)
        old_i = config.tier_index(config.to_miles(before))
        new_i = config.tier_index(config.to_miles(after))
        await self._sync_roles(member, new_i)
        promoted = config.TIERS[new_i][0] if new_i > old_i and new_i >= 0 else None
        return units, after, promoted

    async def _sync_roles(self, member: discord.Member, tier_i: int) -> None:
        """Give the role for the current tier, remove roles of the other tiers."""
        mapping = await self.db.tier_roles(member.guild.id)
        if not mapping:
            return
        keep = mapping.get(config.TIERS[tier_i][0]) if tier_i >= 0 else None
        try:
            for role_id in mapping.values():
                role = member.guild.get_role(role_id)
                if not role:
                    continue
                if role_id == keep and role not in member.roles:
                    await member.add_roles(role, reason="Miles tier")
                elif role_id != keep and role in member.roles:
                    await member.remove_roles(role, reason="Miles tier changed")
        except discord.HTTPException:
            log.warning("Cannot update tier roles in guild %s", member.guild.id)


class Miles(commands.Cog):
    def __init__(self, bot: MilesBot):
        self.bot = bot

    # --- passive earning ---------------------------------------------
    async def _earns_here(self, message: discord.Message) -> bool:
        """Earning is limited to the configured channels (or everywhere if none set).
        Threads count via their parent channel."""
        allowed = await self.bot.db.channels(message.guild.id)
        if not allowed:
            return True
        parent = getattr(message.channel, "parent_id", None)
        return message.channel.id in allowed or parent in allowed

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
            return
        if not await self._earns_here(message):
            return
        db, gid, uid = self.bot.db, message.guild.id, message.author.id
        units, parts = 0, []
        if await db.try_claim(gid, uid, "message", config.MESSAGE_COOLDOWN_SECS):
            units += config.to_units(config.MESSAGE_MILES)
            parts.append("message")
        images = count_images(message)
        if images and await db.try_claim(gid, uid, "image", config.IMAGE_COOLDOWN_SECS):
            units += images * config.to_units(config.IMAGE_MILES)
            parts.append(f"image x{images}")
        if not units:
            return
        _, _, promoted = await self.bot.award(message.author, units, " + ".join(parts), boost=True)
        if promoted:
            await message.channel.send(
                f"🎉 {message.author.mention} reached **{promoted}**!",
                allowed_mentions=discord.AllowedMentions(users=[message.author]))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState) -> None:
        if member.bot or config.VOICE_MILES_PER_MIN <= 0:
            return
        key = (member.guild.id, member.id)
        afk = member.guild.afk_channel

        def counts(state: discord.VoiceState) -> bool:
            return state.channel is not None and state.channel != afk and not state.afk

        if counts(after) and key not in self.bot.voice_joined:
            self.bot.voice_joined[key] = time.time()
        elif not counts(after) and key in self.bot.voice_joined:
            started = self.bot.voice_joined.pop(key)
            mins = min(int((time.time() - started) // 60), config.VOICE_MAX_MINS)
            if mins > 0:
                units = mins * config.to_units(config.VOICE_MILES_PER_MIN)
                await self.bot.award(member, units, "voice", boost=True)

    # --- viewing ------------------------------------------------------
    @app_commands.command(description="Show a miles balance and recent activity.")
    @app_commands.guild_only()
    async def miles(self, interaction: discord.Interaction, user: discord.Member | None = None) -> None:
        user = user or interaction.user
        gid = interaction.guild_id
        units = await self.bot.db.balance(gid, user.id)
        balance = config.to_miles(units)
        rank = await self.bot.db.rank(gid, user.id)
        hist = await self.bot.db.history(gid, user.id, 5)
        embed = discord.Embed(title=f"{user.display_name}'s miles", color=discord.Color.teal())
        embed.add_field(name="Balance", value=fmt_miles(units))
        embed.add_field(name="Rank", value=f"#{rank}" if rank else "—")
        embed.add_field(name="Recent", inline=False, value="\n".join(
            f"{fmt_miles(a, True)} · {r} · {_ts(t)}" for a, r, t in hist) or "Nothing yet")
        if config.TIERS:
            i = config.tier_index(balance)
            if i >= 0:
                name, _, mult = config.TIERS[i]
                embed.insert_field_at(0, name="Tier", value=f"{name} (x{mult:g})")
            if i + 1 < len(config.TIERS):
                n_name, need, _ = config.TIERS[i + 1]
                embed.set_footer(text=f"Next tier: {n_name} at {need:,} miles ({need - balance:,.2f} to go)")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(description="Top members by miles.")
    @app_commands.guild_only()
    @app_commands.choices(period=[app_commands.Choice(name=n, value=n) for n in config.PERIODS])
    async def leaderboard(self, interaction: discord.Interaction,
                          period: app_commands.Choice[str] | None = None) -> None:
        name = period.value if period else "all"
        secs = config.PERIODS[name]
        since = int(time.time()) - secs if secs else None
        rows = await self.bot.db.leaderboard(interaction.guild_id, since, config.LEADERBOARD_SIZE)
        if not rows:
            await interaction.response.send_message("No miles earned in that period yet.")
            return
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = [f"{medals.get(i, f'`{i}.`')} <@{uid}> — **{fmt_miles(total)}**"
                 for i, (uid, total) in enumerate(rows, 1)]
        embed = discord.Embed(title=f"Leaderboard ({name})", description="\n".join(lines),
                              color=discord.Color.gold())
        await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(description="Show all tiers and their perks.")
    @app_commands.guild_only()
    async def tiers(self, interaction: discord.Interaction) -> None:
        if not config.TIERS:
            await interaction.response.send_message("No tiers have been set up yet.")
            return
        roles = await self.bot.db.tier_roles(interaction.guild_id)
        lines = []
        for name, need, mult in config.TIERS:
            role = f" → <@&{roles[name]}>" if name in roles else ""
            lines.append(f"**{name}** — {need:,}+ miles · x{mult:g} earnings{role}")
        await interaction.response.send_message(
            "\n".join(lines), allowed_mentions=discord.AllowedMentions.none())

    # --- flights ------------------------------------------------------
    async def _can_award_flights(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.manage_guild:
            return True
        allowed = await self.bot.db.flight_roles(interaction.guild_id)
        return any(r.id in allowed for r in interaction.user.roles)

    @app_commands.command(description="Award miles for a flight, based on its distance (flight staff only).")
    @app_commands.describe(players="Mention the players who flew, e.g. @a @b",
                           distance="Distance flown in miles",
                           route="Optional note, e.g. LAX-JFK")
    @app_commands.guild_only()
    async def flight(self, interaction: discord.Interaction, players: str,
                     distance: app_commands.Range[float, 1, config.FLIGHT_MAX_DISTANCE],
                     route: app_commands.Range[str, 0, 60] = "") -> None:
        if not await self._can_award_flights(interaction):
            await interaction.response.send_message(
                "Only flight staff can award flight miles.", ephemeral=True)
            return
        ids = parse_mention_ids(players)[:config.FLIGHT_MAX_PLAYERS]
        members = [m for m in (interaction.guild.get_member(i) for i in ids) if m and not m.bot]
        if not members:
            await interaction.response.send_message(
                "I couldn't find any players. Mention them, e.g. `@player1 @player2`.", ephemeral=True)
            return
        units = config.to_units(distance * config.FLIGHT_MILES_PER_DISTANCE_MILE)
        reason = f"flight {route}".strip() + f" ({distance:g} mi)"
        lines = []
        for m in members:
            added, balance, promoted = await self.bot.award(m, units, reason, boost=True)
            line = f"{m.mention} +{fmt_miles(added)} → {fmt_miles(balance)}"
            lines.append(line + (f" 🎉 **{promoted}**" if promoted else ""))
        title = f"✈️ Flight{' ' + route if route else ''}: {distance:g} mi"
        await interaction.response.send_message(
            title + "\n" + "\n".join(lines), allowed_mentions=discord.AllowedMentions.none())

    # --- admin --------------------------------------------------------
    admin = app_commands.Group(name="miles-admin", description="Manage miles",
                               default_permissions=discord.Permissions(manage_guild=True),
                               guild_only=True)

    @admin.command(description="Give (or with a negative number, take) miles.")
    async def adjust(self, interaction: discord.Interaction, user: discord.Member,
                     miles: app_commands.Range[float, -1_000_000, 1_000_000],
                     reason: str = "admin") -> None:
        if user.bot:
            await interaction.response.send_message("Bots can't hold miles.", ephemeral=True)
            return
        units, balance, _ = await self.bot.award(user, config.to_units(miles), f"admin: {reason}")
        await interaction.response.send_message(
            f"{user.mention} {fmt_miles(units, True)} miles → **{fmt_miles(balance)}**", ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())

    @admin.command(name="earn-channel-add", description="Let chat in this channel earn miles.")
    async def earn_channel_add(self, interaction: discord.Interaction,
                               channel: discord.TextChannel) -> None:
        await self.bot.db.add_channel(interaction.guild_id, channel.id)
        await interaction.response.send_message(
            f"Chatting in {channel.mention} (and its threads) now earns miles.", ephemeral=True)

    @admin.command(name="earn-channel-remove", description="Stop earning miles in a channel.")
    async def earn_channel_remove(self, interaction: discord.Interaction,
                                  channel: discord.TextChannel) -> None:
        ok = await self.bot.db.remove_channel(interaction.guild_id, channel.id)
        await interaction.response.send_message("Removed." if ok else "That channel wasn't set.", ephemeral=True)

    @admin.command(name="earn-channels", description="List channels where miles are earned.")
    async def earn_channels(self, interaction: discord.Interaction) -> None:
        ids = await self.bot.db.channels(interaction.guild_id)
        text = ("Miles are earned in: " + ", ".join(f"<#{i}>" for i in sorted(ids))) if ids else \
            "No channels set, so miles are earned in **every** channel. Use `earn-channel-add` to limit it."
        await interaction.response.send_message(text, ephemeral=True)

    @admin.command(name="flight-role-add", description="Let a role run /flight.")
    async def flight_role_add(self, interaction: discord.Interaction, role: discord.Role) -> None:
        await self.bot.db.add_flight_role(interaction.guild_id, role.id)
        await interaction.response.send_message(
            f"{role.mention} can now run `/flight`.", ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())

    @admin.command(name="flight-role-remove", description="Stop a role from running /flight.")
    async def flight_role_remove(self, interaction: discord.Interaction, role: discord.Role) -> None:
        ok = await self.bot.db.remove_flight_role(interaction.guild_id, role.id)
        await interaction.response.send_message("Removed." if ok else "That role wasn't set.", ephemeral=True)

    @admin.command(name="tier-role", description="Assign a Discord role to a tier.")
    async def tier_role(self, interaction: discord.Interaction, tier: str, role: discord.Role) -> None:
        if tier not in {t[0] for t in config.TIERS}:
            await interaction.response.send_message(
                "Unknown tier. Available: " + (", ".join(t[0] for t in config.TIERS) or "none set up yet"),
                ephemeral=True)
            return
        if role >= interaction.guild.me.top_role or role.is_default() or role.managed:
            await interaction.response.send_message(
                "I can't assign that role (it must be below my highest role and not managed).",
                ephemeral=True)
            return
        await self.bot.db.set_tier_role(interaction.guild_id, tier, role.id)
        await interaction.response.send_message(
            f"**{tier}** members will get {role.mention}.", ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())

    @admin.command(name="tier-role-clear", description="Stop using a role for a tier.")
    async def tier_role_clear(self, interaction: discord.Interaction, tier: str) -> None:
        ok = await self.bot.db.clear_tier_role(interaction.guild_id, tier)
        await interaction.response.send_message("Cleared." if ok else "No role set.", ephemeral=True)

    @admin.command(description="Export the full ledger as CSV.")
    async def export(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.export(interaction.guild_id)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["user_id", "miles", "reason", "created_at_unix"])
        w.writerows((u, config.to_miles(a), r, t) for u, a, r, t in rows)
        file = discord.File(io.BytesIO(buf.getvalue().encode()), filename="miles_ledger.csv")
        await interaction.response.send_message(file=file, ephemeral=True)
