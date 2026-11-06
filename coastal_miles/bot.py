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

    async def award(self, member: discord.Member, amount: int, reason: str) -> int:
        """Add miles, then grant any milestone roles now reached. Returns new balance."""
        balance = await self.db.add(member.guild.id, member.id, amount, reason)
        if amount > 0:
            await self._apply_milestones(member, balance)
        return balance

    async def _apply_milestones(self, member: discord.Member, balance: int) -> None:
        for miles, role_id in await self.db.milestones(member.guild.id):
            if balance < miles:
                break
            role = member.guild.get_role(role_id)
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason=f"Reached {miles} miles")
                except discord.HTTPException:
                    log.warning("Cannot grant role %s in guild %s", role_id, member.guild.id)


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
            await self.bot.award(message.author, config.MESSAGE_MILES, "message")

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
                await self.bot.award(member, mins * config.VOICE_MILES_PER_MIN, "voice")

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
        balance = await self.bot.award(interaction.user, amount, f"daily (streak {streak})")
        await interaction.response.send_message(
            f"✈️ +**{amount}** miles! Streak: **{streak}** 🔥 — balance: **{balance:,}**")

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
        nxt = next(((m, r) for m, r in await self.bot.db.milestones(gid) if m > balance), None)
        if nxt:
            embed.set_footer(text=f"Next milestone: {nxt[0]:,} miles ({nxt[0] - balance:,} to go)")
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

    @app_commands.command(description="List milestone roles.")
    @app_commands.guild_only()
    async def milestones(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.milestones(interaction.guild_id)
        text = "\n".join(f"**{m:,}** miles → <@&{r}>" for m, r in rows) or "No milestones set."
        await interaction.response.send_message(text, allowed_mentions=discord.AllowedMentions.none())

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
        balance = await self.bot.award(user, amount, f"admin: {reason}")
        await interaction.response.send_message(
            f"{user.mention} {amount:+,} miles → **{balance:,}**", ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())

    @admin.command(name="milestone-set", description="Grant a role when members reach a miles total.")
    async def milestone_set(self, interaction: discord.Interaction,
                            miles: app_commands.Range[int, 1, 10_000_000], role: discord.Role) -> None:
        me = interaction.guild.me
        if role >= me.top_role or role.is_default() or role.managed:
            await interaction.response.send_message(
                "I can't assign that role (it must be below my highest role and not managed).",
                ephemeral=True)
            return
        await self.bot.db.set_milestone(interaction.guild_id, miles, role.id)
        await interaction.response.send_message(
            f"Members reaching **{miles:,}** miles will get {role.mention}.", ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())

    @admin.command(name="milestone-remove", description="Remove a milestone.")
    async def milestone_remove(self, interaction: discord.Interaction, miles: int) -> None:
        ok = await self.bot.db.remove_milestone(interaction.guild_id, miles)
        await interaction.response.send_message("Removed." if ok else "No such milestone.", ephemeral=True)

    @admin.command(description="Export the full ledger as CSV.")
    async def export(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.export(interaction.guild_id)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["user_id", "amount", "reason", "created_at_unix"])
        w.writerows(rows)
        file = discord.File(io.BytesIO(buf.getvalue().encode()), filename="miles_ledger.csv")
        await interaction.response.send_message(file=file, ephemeral=True)
