import pytest
from coastal_miles import config


def test_no_tiers_by_default():
    assert config.TIERS == []
    assert config.tier_index(1000) == -1


def test_tier_index(monkeypatch):
    monkeypatch.setattr(config, "TIERS", [("A", 0, 1.0), ("B", 250, 1.5)])
    assert config.tier_index(-5) == -1
    assert config.tier_index(0) == 0
    assert config.tier_index(249) == 0
    assert config.tier_index(250) == 1
