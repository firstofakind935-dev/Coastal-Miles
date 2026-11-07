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

# (name, miles needed, earning multiplier for chat/voice miles), lowest first.
# NOTE: miles thresholds are placeholders until you set the real ones.
TIERS: list[tuple[str, int, float]] = [
    ("Basic", 0, 1.0),
    ("Preferred", 500, 1.25),
    ("Premium Preferred", 2_000, 1.5),
    ("Coast to Coast", 7_500, 1.75),
    ("Coastal Reserved", 50_000, 2.0),
]

# Hidden boost: at this many miles, chat/voice earnings switch to this multiplier.
# It is not a tier: never named, announced or listed anywhere, it just happens.
SECRET_BOOST_MILES = 100_000
SECRET_BOOST_MULT = 10.0


def tier_index(balance: int) -> int:
    """Index of the highest tier reached, or -1 if there are no tiers / none reached."""
    idx = -1
    for i, (_, need, _) in enumerate(TIERS):
        if balance >= need:
            idx = i
    return idx


def multiplier_for(balance: int) -> float:
    """Chat/voice earning multiplier for a given balance."""
    if balance >= SECRET_BOOST_MILES:
        return SECRET_BOOST_MULT
    i = tier_index(balance)
    return TIERS[i][2] if i >= 0 else 1.0
