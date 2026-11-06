from __future__ import annotations

import time
import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_user ON ledger (guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_ledger_time ON ledger (guild_id, created_at);
CREATE TABLE IF NOT EXISTS user_state (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    last_message_at INTEGER NOT NULL DEFAULT 0,
    last_daily_day INTEGER NOT NULL DEFAULT 0,
    daily_streak INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS milestones (
    guild_id INTEGER NOT NULL,
    miles INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, miles)
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.path)
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    # --- ledger -------------------------------------------------------
    async def add(self, guild_id: int, user_id: int, amount: int, reason: str,
                  now: int | None = None) -> int:
        """Record a ledger entry and return the user's new balance."""
        now = int(now if now is not None else time.time())
        await self.conn.execute(
            "INSERT INTO ledger (guild_id, user_id, amount, reason, created_at) VALUES (?,?,?,?,?)",
            (guild_id, user_id, amount, reason, now))
        await self.conn.commit()
        return await self.balance(guild_id, user_id)

    async def balance(self, guild_id: int, user_id: int) -> int:
        cur = await self.conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM ledger WHERE guild_id=? AND user_id=?",
            (guild_id, user_id))
        return (await cur.fetchone())[0]

    async def leaderboard(self, guild_id: int, since: int | None, limit: int):
        q = "SELECT user_id, SUM(amount) AS total FROM ledger WHERE guild_id=?"
        args: list = [guild_id]
        if since is not None:
            q += " AND created_at>=?"
            args.append(since)
        q += " GROUP BY user_id HAVING total>0 ORDER BY total DESC, user_id LIMIT ?"
        args.append(limit)
        cur = await self.conn.execute(q, args)
        return await cur.fetchall()

    async def rank(self, guild_id: int, user_id: int) -> int | None:
        bal = await self.balance(guild_id, user_id)
        if bal <= 0:
            return None
        cur = await self.conn.execute(
            "SELECT COUNT(*) FROM (SELECT SUM(amount) t FROM ledger WHERE guild_id=? "
            "GROUP BY user_id HAVING t>?)", (guild_id, bal))
        return (await cur.fetchone())[0] + 1

    async def history(self, guild_id: int, user_id: int, limit: int = 10):
        cur = await self.conn.execute(
            "SELECT amount, reason, created_at FROM ledger WHERE guild_id=? AND user_id=? "
            "ORDER BY id DESC LIMIT ?", (guild_id, user_id, limit))
        return await cur.fetchall()

    async def export(self, guild_id: int):
        cur = await self.conn.execute(
            "SELECT user_id, amount, reason, created_at FROM ledger WHERE guild_id=? ORDER BY id",
            (guild_id,))
        return await cur.fetchall()

    # --- activity state ----------------------------------------------
    async def try_message_award(self, guild_id: int, user_id: int, cooldown: int,
                                now: int | None = None) -> bool:
        """Atomically claim the message cooldown. True if the user may earn now."""
        now = int(now if now is not None else time.time())
        await self.conn.execute(
            "INSERT OR IGNORE INTO user_state (guild_id, user_id) VALUES (?,?)",
            (guild_id, user_id))
        cur = await self.conn.execute(
            "UPDATE user_state SET last_message_at=? WHERE guild_id=? AND user_id=? "
            "AND last_message_at<=?", (now, guild_id, user_id, now - cooldown))
        await self.conn.commit()
        return cur.rowcount == 1

    async def claim_daily(self, guild_id: int, user_id: int, today: int):
        """Return (new_streak, already_claimed). `today` is days since epoch."""
        await self.conn.execute(
            "INSERT OR IGNORE INTO user_state (guild_id, user_id) VALUES (?,?)",
            (guild_id, user_id))
        cur = await self.conn.execute(
            "SELECT last_daily_day, daily_streak FROM user_state WHERE guild_id=? AND user_id=?",
            (guild_id, user_id))
        last, streak = await cur.fetchone()
        if last == today:
            return streak, True
        streak = streak + 1 if last == today - 1 else 1
        await self.conn.execute(
            "UPDATE user_state SET last_daily_day=?, daily_streak=? WHERE guild_id=? AND user_id=?",
            (today, streak, guild_id, user_id))
        await self.conn.commit()
        return streak, False

    # --- milestones ---------------------------------------------------
    async def set_milestone(self, guild_id: int, miles: int, role_id: int) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO milestones (guild_id, miles, role_id) VALUES (?,?,?)",
            (guild_id, miles, role_id))
        await self.conn.commit()

    async def remove_milestone(self, guild_id: int, miles: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM milestones WHERE guild_id=? AND miles=?", (guild_id, miles))
        await self.conn.commit()
        return cur.rowcount > 0

    async def milestones(self, guild_id: int):
        cur = await self.conn.execute(
            "SELECT miles, role_id FROM milestones WHERE guild_id=? ORDER BY miles", (guild_id,))
        return await cur.fetchall()
