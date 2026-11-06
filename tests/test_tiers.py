import random
from coastal_miles import config
from coastal_miles.bot import apply_multiplier


def test_default_tiers():
    assert [t[0] for t in config.TIERS][:5] == [
        "Basic", "Preferred", "Premium Preferred", "Coast to Coast", "Coastal Reserved"]
    assert [t[2] for t in config.TIERS] == [1.0, 1.25, 1.5, 1.75, 2.0, 10.0]
    assert config.SECRET_TIERS <= {t[0] for t in config.TIERS}
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
