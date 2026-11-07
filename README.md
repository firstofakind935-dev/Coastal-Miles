# Coastal Miles

A Discord bot that tracks community "miles", earned passively by chatting and posting images.

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

## Earning (passive, no commands needed)
Members just chat; the bot does the rest. Tune everything in `coastal_miles/config.py`.
- Each message: **1/16 mile** (one paying message per user every 10s)
- Each image attachment: **1/8 mile** (up to 4 per message, one paying post every 5s)
- Voice earning exists but is **off** by default (`VOICE_MILES_PER_MIN = 0`)

Earning is limited to the channels you choose with `/miles-admin earn-channel-add` (threads inside them count). If none are set, every channel earns. Miles are stored in 1/64ths so fractions stay exact.

## Flights
Flight staff run `/flight players:@a @b distance:850 route:LAX-JFK` to award each mentioned player miles equal to the distance flown (`FLIGHT_MILES_PER_DISTANCE_MILE` in config; up to 25 players per flight). Tier multipliers apply, like passive earning. Who can run it: anyone with Manage Server, plus any role added with `/miles-admin flight-role-add`.

## Tiers
| Tier | Miles needed (placeholder) | Multiplier |
|---|---|---|
| Basic | 0 (everyone) | x1.0 |
| Preferred | 500 | x1.25 |
| Premium Preferred | 2,000 | x1.5 |
| Coast to Coast | 7,500 | x1.75 |
| Coastal Reserved | 50,000 | x2.0 |

At 100,000 miles earnings silently jump to x10 (`SECRET_BOOST_*` in config). It is not a tier and is never announced or listed. Edit `TIERS` in `coastal_miles/config.py`. Multipliers apply to earned miles only (not admin adjustments). `/miles` shows a member's tier, promotions are announced, and `/miles-admin tier-role` links a Discord role to a tier.

## Commands
Viewing: `/miles [user]` · `/leaderboard [week|month|all]` · `/tiers`
Flight staff: `/flight`
Admin (Manage Server): `/miles-admin earn-channel-add|earn-channel-remove|earn-channels` · `adjust` · `tier-role` · `tier-role-clear` · `export`

Data lives in a SQLite ledger (`miles.db`); balances are the sum of ledger entries, so every change is auditable.
