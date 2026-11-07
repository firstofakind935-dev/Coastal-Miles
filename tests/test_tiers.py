import random
from coastal_miles import config
from coastal_miles.bot import apply_multiplier


def test_default_tiers():
    assert [t[0] for t in config.TIERS]== [
        "Basic", "Preferred", "Premium Preferred", "Coast to Coast", "Coastal Reserved"]
    assert [t[2] for t in config.TIERS] == [1.0, 1.25, 1.5, 1.75, 2.0]
    assert config.TIERS[0][1] == 0  # everyone starts in Basic
    assert [t[1] for t in config.TIERS] == sorted(t[1] for t in config.TIERS)
    assert config.tier_index(0) == 0


def test_no_tiers(monkeypatch):
    monkeypatch.setattr(config, "TIERS", [])
    assert config.tier_index(1000) == -1


def test_tier_index(monkeypatch):
    monkeypatch.setattr(config, "TIERS", [("A", 0, 1.0), ("B", 250, 1.5)])
    assert config.tier_index(-5) == -1
    assert config.tier_index(0) == 0
    assert config.tier_index(249) == 0
    assert config.tier_index(250) == 1


def test_multiplier_whole_and_fraction():
    assert apply_multiplier(1, 2.0) == 2
    assert apply_multiplier(5, 10.0) == 50
    assert apply_multiplier(1, 1.25, rand=lambda: 0.1) == 2
    assert apply_multiplier(1, 1.25, rand=lambda: 0.9) == 1


def test_multiplier_average():
    rng = random.Random(1)
    total = sum(apply_multiplier(1, 1.25, rng.random) for _ in range(20000))
    assert abs(total / 20000 - 1.25) < 0.02


def test_multiplier_for():
    assert config.multiplier_for(0) == 1.0
    assert config.multiplier_for(500) == 1.25
    assert config.multiplier_for(50_000) == 2.0
    assert config.multiplier_for(config.SECRET_BOOST_MILES - 1) == 2.0
    assert config.multiplier_for(config.SECRET_BOOST_MILES) == 10.0


def test_secret_boost_is_not_a_tier():
    assert all(config.SECRET_BOOST_MULT != t[2] for t in config.TIERS)
    assert all(t[1] < config.SECRET_BOOST_MILES for t in config.TIERS)


def test_fractional_units_are_exact():
    assert config.to_units(1 / 16) == 4
    assert config.to_units(1 / 8) == 8
    # tier multipliers are exact on these amounts (no randomness needed)
    for mult in (1.0, 1.25, 1.5, 1.75, 2.0, 10.0):
        for miles in (1 / 16, 1 / 8):
            assert (config.to_units(miles) * mult) % 1 == 0


def test_format():
    assert config.fmt_miles(4) == "0.06"
    assert config.fmt_miles(64 * 1234 + 8, signed=True) == "+1,234.12"
    assert config.fmt_miles(-8, signed=True) == "-0.12"
