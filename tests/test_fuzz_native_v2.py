from tools.fuzz_native_v2 import campaign


def test_native_v2_corruption_campaign_is_bounded_and_fail_closed():
    result = campaign(500, seed=12345)
    assert result["iterations"] == 500
    assert result["unexpected"] == 0
    assert result["rejected"] > 0
