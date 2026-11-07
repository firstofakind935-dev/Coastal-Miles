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
CREATE TABLE IF NOT EXISTS cooldowns (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    last_at INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, kind)
);
CREATE TABLE IF NOT EXISTS flight_roles (
    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, role_id)
);
CREATE TABLE IF NOT EXISTS earn_channels (
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, channel_id)
);
CREATE TABLE IF NOT EXISTS tier_roles (
    guild_id INTEGER NOT NULL,
    tier_name TEXT NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, tier_name)
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
        """Record a ledger entry (amount in units) and return the new balance in units."""
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

    # --- anti-spam cooldowns -----------------------------------------
    async def try_claim(self, guild_id: int, user_id: int, kind: str, cooldown: int,
                        now: int | None = None) -> bool:
        """Atomically claim a cooldown slot. True if the user may earn for `kind` now."""
        now = int(now if now is not None else time.time())
        await self.conn.execute(
            "INSERT OR IGNORE INTO cooldowns (guild_id, user_id, kind) VALUES (?,?,?)",
            (guild_id, user_id, kind))
        cur = await self.conn.execute(
            "UPDATE cooldowns SET last_at=? WHERE guild_id=? AND user_id=? AND kind=? "
            "AND last_at<=?", (now, guild_id, user_id, kind, now - cooldown))
        await self.conn.commit()
        return cur.rowcount == 1

    # --- earning channels --------------------------------------------
    async def add_channel(self, guild_id: int, channel_id: int) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO earn_channels (guild_id, channel_id) VALUES (?,?)",
            (guild_id, channel_id))
        await self.conn.commit()

    async def remove_channel(self, guild_id: int, channel_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM earn_channels WHERE guild_id=? AND channel_id=?", (guild_id, channel_id))
        await self.conn.commit()
        return cur.rowcount > 0

    async def channels(self, guild_id: int) -> set[int]:
        cur = await self.conn.execute(
            "SELECT channel_id FROM earn_channels WHERE guild_id=?", (guild_id,))
        return {r[0] for r in await cur.fetchall()}

    # --- roles allowed to run /flight --------------------------------
    async def add_flight_role(self, guild_id: int, role_id: int) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO flight_roles (guild_id, role_id) VALUES (?,?)", (guild_id, role_id))
        await self.conn.commit()

    async def remove_flight_role(self, guild_id: int, role_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM flight_roles WHERE guild_id=? AND role_id=?", (guild_id, role_id))
        await self.conn.commit()
        return cur.rowcount > 0

    async def flight_roles(self, guild_id: int) -> set[int]:
        cur = await self.conn.execute("SELECT role_id FROM flight_roles WHERE guild_id=?", (guild_id,))
        return {r[0] for r in await cur.fetchall()}

    # --- tier roles ---------------------------------------------------
    async def set_tier_role(self, guild_id: int, tier_name: str, role_id: int) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO tier_roles (guild_id, tier_name, role_id) VALUES (?,?,?)",
            (guild_id, tier_name, role_id))
        await self.conn.commit()

    async def clear_tier_role(self, guild_id: int, tier_name: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM tier_roles WHERE guild_id=? AND tier_name=?", (guild_id, tier_name))
        await self.conn.commit()
        return cur.rowcount > 0

    async def tier_roles(self, guild_id: int) -> dict[str, int]:
        cur = await self.conn.execute(
            "SELECT tier_name, role_id FROM tier_roles WHERE guild_id=?", (guild_id,))
        return dict(await cur.fetchall())
