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
| Tier | Miles | Chat/voice multiplier |
|---|---|---|
| Dockhand | 0 | x1.0 |
| Shoreline | 250 | x1.1 |
| Tidecaller | 1000 | x1.25 |
| Harbor Master | 2500 | x1.5 |
| Lighthouse | 5000 | x2.0 |

Edit `TIERS` in `config.py` to rename or rebalance. Use `/miles-admin tier-role` to link a Discord role to a tier; members get the role of their current tier (old tier roles are removed). Promotions are announced in chat. `/daily` is not multiplied.

## Commands
`/miles [user]` · `/leaderboard [week|month|all]` · `/daily` · `/tiers`
Admin (Manage Server): `/miles-admin adjust` · `tier-role` · `tier-role-clear` · `export`

Data lives in a SQLite ledger (`miles.db`); balances are the sum of ledger entries, so every change is auditable.
