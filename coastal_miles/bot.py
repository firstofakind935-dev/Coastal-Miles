from __future__ import annotations

import csv
import io
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from . import config
from .db import Database

log = logging.getLogger("coastal_miles")


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

    async def award(self, member: discord.Member, amount: int, reason: str,
                    boost: bool = False) -> tuple[int, int, str | None]:
        """Add miles (tier-boosted if `boost`), sync tier roles.

        Returns (miles_added, new_balance, promoted_tier_name_or_None).
        """
        gid = member.guild.id
        before = await self.db.balance(gid, member.id)
        if boost and amount > 0:
            ti = config.tier_index(before)
            if ti >= 0:
                amount = max(1, round(amount * config.TIERS[ti][2]))
        after = await self.db.add(gid, member.id, amount, reason)
        old_i, new_i = config.tier_index(before), config.tier_index(after)
        await self._sync_roles(member, new_i)
        promoted = config.TIERS[new_i][0] if new_i > old_i and new_i >= 0 else None
        return amount, after, promoted

    async def _sync_roles(self, member: discord.Member, tier_i: int) -> None:
        """Give the role for the current tier, remove roles of the other tiers."""
        mapping = await self.db.tier_roles(member.guild.id)
        if not mapping:
            return
        keep = mapping.get(config.TIERS[tier_i][0]) if tier_i >= 0 else None
        try:
            for name, role_id in mapping.items():
                role = member.guild.get_role(role_id)
                if not role:
                    continue
                if role_id == keep and role not in member.roles:
                    await member.add_roles(role, reason="Miles tier")
                elif role_id != keep and role in member.roles:
                    await member.remove_roles(role, reason="Miles tier changed")
        except discord.HTTPException:
            log.warning("Cannot update tier roles in guild %s", member.guild.id)


def _ts(ts: int) -> str:
    return f"<t:{ts}:R>"


class Miles(commands.Cog):
    def __init__(self, bot: MilesBot):
        self.bot = bot

    # --- earning ------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
            return
        if await self.bot.db.try_message_award(
                message.guild.id, message.author.id, config.MESSAGE_COOLDOWN_SECS):
            _, _, promoted = await self.bot.award(
                message.author, config.MESSAGE_MILES, "message", boost=True)
            if promoted:
                await message.channel.send(
                    f"🎉 {message.author.mention} reached **{promoted}**!",
                    allowed_mentions=discord.AllowedMentions(users=[message.author]))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState) -> None:
        if member.bot:
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
                await self.bot.award(member, mins * config.VOICE_MILES_PER_MIN, "voice", boost=True)

    @app_commands.command(description="Claim your daily miles. Consecutive days build a streak bonus.")
    @app_commands.guild_only()
    async def daily(self, interaction: discord.Interaction) -> None:
        today = int(time.time() // 86400)  # UTC day
        streak, already = await self.bot.db.claim_daily(interaction.guild_id, interaction.user.id, today)
        if already:
            await interaction.response.send_message(
                f"You already claimed today. Streak: **{streak}** 🔥 — come back after 00:00 UTC.",
                ephemeral=True)
            return
        amount = config.DAILY_BASE + config.DAILY_STREAK_BONUS * (min(streak, config.DAILY_STREAK_CAP) - 1)
        _, balance, promoted = await self.bot.award(
            interaction.user, amount, f"daily (streak {streak})")
        msg = f"✈️ +**{amount}** miles! Streak: **{streak}** 🔥 — balance: **{balance:,}**"
        if promoted:
            msg += f"\n🎉 You reached **{promoted}**!"
        await interaction.response.send_message(msg)

    # --- viewing ------------------------------------------------------
    @app_commands.command(description="Show a miles balance and recent activity.")
    @app_commands.guild_only()
    async def miles(self, interaction: discord.Interaction, user: discord.Member | None = None) -> None:
        user = user or interaction.user
        gid = interaction.guild_id
        balance = await self.bot.db.balance(gid, user.id)
        rank = await self.bot.db.rank(gid, user.id)
        hist = await self.bot.db.history(gid, user.id, 5)
        embed = discord.Embed(title=f"{user.display_name}'s miles", color=discord.Color.teal())
        embed.add_field(name="Balance", value=f"{balance:,}")
        embed.add_field(name="Rank", value=f"#{rank}" if rank else "—")
        embed.add_field(name="Recent", inline=False, value="\n".join(
            f"{a:+,} · {r} · {_ts(t)}" for a, r, t in hist) or "Nothing yet")
        if config.TIERS:
            i = config.tier_index(balance)
            if i >= 0:
                name, _, mult = config.TIERS[i]
                embed.insert_field_at(0, name="Tier", value=f"{name} (x{mult:g})")
            if i + 1 < len(config.TIERS):
                n_name, need, _ = config.TIERS[i + 1]
                embed.set_footer(text=f"Next tier: {n_name} at {need:,} miles ({need - balance:,} to go)")
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
        lines = [f"{medals.get(i, f'`{i}.`')} <@{uid}> — **{total:,}**" for i, (uid, total) in enumerate(rows, 1)]
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
            lines.append(f"**{name}** — {need:,}+ miles · x{mult:g} chat/voice earnings{role}")
        await interaction.response.send_message(
            "\n".join(lines), allowed_mentions=discord.AllowedMentions.none())

    # --- admin --------------------------------------------------------
    admin = app_commands.Group(name="miles-admin", description="Manage miles",
                               default_permissions=discord.Permissions(manage_guild=True),
                               guild_only=True)

    @admin.command(description="Give (or with a negative number, take) miles.")
    async def adjust(self, interaction: discord.Interaction, user: discord.Member,
                     amount: app_commands.Range[int, -1_000_000, 1_000_000], reason: str = "admin") -> None:
        if user.bot:
            await interaction.response.send_message("Bots can't hold miles.", ephemeral=True)
            return
        _, balance, _ = await self.bot.award(user, amount, f"admin: {reason}")
        await interaction.response.send_message(
            f"{user.mention} {amount:+,} miles → **{balance:,}**", ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())

    @admin.command(name="tier-role", description="Assign a Discord role to a tier.")
    async def tier_role(self, interaction: discord.Interaction,
                        tier: str, role: discord.Role) -> None:
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
    async def tier_role_clear(self, interaction: discord.Interaction,
                              tier: str) -> None:
        ok = await self.bot.db.clear_tier_role(interaction.guild_id, tier)
        await interaction.response.send_message("Cleared." if ok else "No role set.", ephemeral=True)

    @admin.command(description="Export the full ledger as CSV.")
    async def export(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.export(interaction.guild_id)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["user_id", "amount", "reason", "created_at_unix"])
        w.writerows(rows)
        file = discord.File(io.BytesIO(buf.getvalue().encode()), filename="miles_ledger.csv")
        await interaction.response.send_message(file=file, ephemeral=True)
