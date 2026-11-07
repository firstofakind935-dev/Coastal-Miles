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
| Tier | Miles needed (placeholder) | Chat/voice multiplier |
|---|---|---|
| Basic | 0 (everyone) | x1.0 |
| Preferred | 500 | x1.25 |
| Premium Preferred | 2,000 | x1.5 |
| Coast to Coast | 7,500 | x1.75 |
| Coastal Reserved | 50,000 | x2.0 |

At 100,000 miles chat/voice earnings silently jump to x10 (`SECRET_BOOST_*` in config). It is not a tier and is never announced or listed. Edit `TIERS` in `coastal_miles/config.py`. Multipliers apply to chat and voice miles only (not `/daily` or admin adjustments); fractional results are rounded fairly at random so x1.25 averages 1.25. `/miles` shows a member's tier, promotions are announced, and `/miles-admin tier-role` links a Discord role to a tier.

## Commands
`/miles [user]` · `/leaderboard [week|month|all]` · `/daily` · `/tiers`
Admin (Manage Server): `/miles-admin adjust` · `tier-role` · `tier-role-clear` · `export`

Data lives in a SQLite ledger (`miles.db`); balances are the sum of ledger entries, so every change is auditable.
