import asyncio
import logging
import os

from dotenv import load_dotenv

from .bot import MilesBot
from .db import Database


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Set DISCORD_TOKEN (see .env.example)")
    dev = [int(x) for x in os.environ.get("DEV_GUILD_IDS", "").split(",") if x.strip()]
    bot = MilesBot(Database(os.environ.get("DB_PATH", "miles.db")), dev)
    bot.run(token)


if __name__ == "__main__":
    main()
