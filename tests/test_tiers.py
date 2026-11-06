import pytest
from coastal_miles import config


def test_default_tiers():
    assert [t[0] for t in config.TIERS] == [
        "Basic", "Preferred", "Premium Preferred", "Coast to Coast", "Coastal Reserved"]
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
