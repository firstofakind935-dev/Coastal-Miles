"""Tunable earning rules. Edit these to rebalance the economy."""

MESSAGE_MILES = 1            # miles per qualifying message
MESSAGE_COOLDOWN_SECS = 60   # one qualifying message per user per this window
VOICE_MILES_PER_MIN = 1      # miles per full minute in a voice channel
VOICE_MAX_MINS = 180         # cap per voice session so idle users can't farm
DAILY_BASE = 25
DAILY_STREAK_BONUS = 5       # extra per consecutive day...
DAILY_STREAK_CAP = 10        # ...up to this many days
LEADERBOARD_SIZE = 10

PERIODS = {"week": 7 * 86400, "month": 30 * 86400, "all": None}

# (name, miles needed, earning multiplier for chat/voice miles)
TIERS = [
    ("Dockhand", 0, 1.0),
    ("Shoreline", 250, 1.1),
    ("Tidecaller", 1000, 1.25),
    ("Harbor Master", 2500, 1.5),
    ("Lighthouse", 5000, 2.0),
]


def tier_index(balance: int) -> int:
    idx = 0
    for i, (_, need, _) in enumerate(TIERS):
        if balance >= need:
            idx = i
    return idx
