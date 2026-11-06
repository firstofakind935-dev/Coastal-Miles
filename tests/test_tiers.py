from coastal_miles import config


def test_tier_index():
    assert config.tier_index(0) == 0
    assert config.tier_index(-50) == 0
    assert config.tier_index(249) == 0
    assert config.tier_index(250) == 1
    assert config.tier_index(10**6) == len(config.TIERS) - 1
