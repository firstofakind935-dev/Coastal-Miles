"""Tunable rules. Edit these to rebalance the economy."""

# Miles are stored as integer "units" (1 mile = 64 units) so fractions like 1/16 are exact.
UNITS_PER_MILE = 64


def to_units(miles: float) -> int:
    return round(miles * UNITS_PER_MILE)


def to_miles(units: int) -> float:
    return units / UNITS_PER_MILE


def fmt_miles(units: int, signed: bool = False) -> str:
    return f"{to_miles(units):{'+' if signed else ''},.2f}"


# --- passive earning (chat) ------------------------------------------
MESSAGE_MILES = 1 / 16       # per message
IMAGE_MILES = 1 / 8          # per image attachment
IMAGES_PER_MESSAGE_CAP = 4   # images counted per message
MESSAGE_COOLDOWN_SECS = 10   # anti-spam: one paying message per user per window
IMAGE_COOLDOWN_SECS = 5      # anti-spam: one paying image post per user per window

# Voice earning is OFF (0). Set e.g. 1/16 to pay that many miles per minute in voice.
VOICE_MILES_PER_MIN = 0
VOICE_MAX_MINS = 180

# --- flights (staff-run /flight command) ------------------------------
FLIGHT_MILES_PER_DISTANCE_MILE = 1.0   # miles awarded per mile flown
FLIGHT_MAX_DISTANCE = 25_000           # sanity cap per flight
FLIGHT_MAX_PLAYERS = 25                # players per /flight

LEADERBOARD_SIZE = 10
PERIODS = {"week": 7 * 86400, "month": 30 * 86400, "all": None}

# (name, miles needed, earning multiplier), lowest first.
# NOTE: miles thresholds are placeholders until you set the real ones.
TIERS: list[tuple[str, int, float]] = [
    ("Basic", 0, 1.0),
    ("Preferred", 500, 1.25),
    ("Premium Preferred", 2_000, 1.5),
    ("Coast to Coast", 7_500, 1.75),
    ("Coastal Reserved", 50_000, 2.0),
]

# Hidden boost: at this many miles, earnings switch to this multiplier.
# It is not a tier: never named, announced or listed anywhere, it just happens.
SECRET_BOOST_MILES = 100_000
SECRET_BOOST_MULT = 10.0


def tier_index(balance: float) -> int:
    """Index of the highest tier reached (balance in miles), or -1 if none."""
    idx = -1
    for i, (_, need, _) in enumerate(TIERS):
        if balance >= need:
            idx = i
    return idx


def multiplier_for(balance: float) -> float:
    """Earning multiplier for a balance in miles."""
    if balance >= SECRET_BOOST_MILES:
        return SECRET_BOOST_MULT
    i = tier_index(balance)
    return TIERS[i][2] if i >= 0 else 1.0
