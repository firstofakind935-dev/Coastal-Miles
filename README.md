# Coastal Miles

A Discord bot that tracks community "miles" — earned by chatting, hanging out in voice, and daily check-ins.

## Setup
1. Create a bot at https://discord.com/developers/applications, copy its token.
2. Invite it with scopes `bot applications.commands` and permission **Manage Roles** (for milestone roles).
3. ```bash
   python -m venv .venv && . .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env   # add DISCORD_TOKEN
   python -m coastal_miles
   ```
   Set `DEV_GUILD_IDS` for instant command sync while developing (global sync can take up to an hour).

## Earning (tune in `coastal_miles/config.py`)
- Chat: 1 mile per message, max once per 60s
- Voice: 1 mile per minute (AFK channel excluded, 180 min cap per session), paid when you leave
- `/daily`: 25 miles + 5 per streak day (streak bonus capped at 10 days), resets at 00:00 UTC

## Tiers
Tiers are set up in the code but currently empty. Add `(name, miles needed, multiplier)` entries to `TIERS` in `coastal_miles/config.py`. Once added, `/miles` shows a member's tier, promotions are announced, chat/voice miles get the tier multiplier (`/daily` does not), and `/miles-admin tier-role` links a Discord role to a tier.

## Commands
`/miles [user]` · `/leaderboard [week|month|all]` · `/daily` · `/tiers`
Admin (Manage Server): `/miles-admin adjust` · `tier-role` · `tier-role-clear` · `export`

Data lives in a SQLite ledger (`miles.db`); balances are the sum of ledger entries, so every change is auditable.
