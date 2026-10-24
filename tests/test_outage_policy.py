from copy import deepcopy

import pytest

from btc_signal_lab.outage_policy import classify_gap


EVENT = {
    "event_id": "binance-spot-halt-2023-03-24",
    "venue": "Binance",
    "market": "Spot",
    "symbol_scope": "all_spot_symbols",
    "documented_suspension_start_utc": "2023-03-24T11:27:00Z",
    "documented_resume_utc": "2023-03-24T14:00:00Z",
    "sources": [
        {"url": "https://www.binance.com/en/blog/from-our-ceo/6789340645608890113"},
        {"url": "https://www.binance.com/en/support/announcement/detail/813a31506e9f478ea8c1058b425df87a"},
    ],
}


def classify(start, end, *, event=EVENT, market="Spot", symbol="BTCUSDT", mode="strict"):
    return classify_gap(start, end, venue="Binance", market=market, symbol=symbol, events=[event], mode=mode)


def test_strict_mode_rejects_documented_gap():
    result = classify("2023-03-24T12:40:00Z", "2023-03-24T14:00:00Z")
    assert result["eligible"] is False
    assert result["status"] == "rejected_documented_outage_strict_mode"


def test_explicit_outage_aware_mode_excludes_but_never_approves_gap():
    result = classify("2023-03-24T12:40:00Z", "2023-03-24T14:00:00Z", mode="outage_aware")
    assert result["eligible"] is False
    assert result["status"] == "excluded_documented_outage"


@pytest.mark.parametrize(("start", "end"), [
    ("2023-03-24T11:26:00Z", "2023-03-24T11:28:00Z"),
    ("2023-03-24T13:59:00Z", "2023-03-24T14:01:00Z"),
    ("2023-03-24T12:40:00Z", "2023-03-24T14:01:00Z"),
])
def test_gap_not_fully_contained_in_outage_is_rejected(start, end):
    assert classify(start, end, mode="outage_aware")["status"] == "rejected_unexplained_gap"


def test_wrong_venue_market_or_symbol_scope_is_rejected():
    assert classify_gap(
        "2023-03-24T12:40:00Z", "2023-03-24T14:00:00Z",
        venue="KuCoin", market="Spot", symbol="BTCUSDT", events=[EVENT], mode="outage_aware",
    )["status"] == "rejected_unexplained_gap"
    assert classify("2023-03-24T12:40:00Z", "2023-03-24T14:00:00Z", market="Futures", mode="outage_aware")["status"] == "rejected_unexplained_gap"
    event = deepcopy(EVENT)
    event["symbol_scope"] = "ETHUSDT"
    assert classify("2023-03-24T12:40:00Z", "2023-03-24T14:00:00Z", event=event, mode="outage_aware")["status"] == "rejected_unexplained_gap"


@pytest.mark.parametrize("sources", [
    [], [{"url": "http://example.com"}], [{"url": "https://"}], None, [{"url": "not a URL"}],
])
def test_missing_or_invalid_provenance_is_rejected(sources):
    event = deepcopy(EVENT)
    event["sources"] = sources
    assert classify("2023-03-24T12:40:00Z", "2023-03-24T14:00:00Z", event=event, mode="outage_aware")["status"] == "rejected_unexplained_gap"


def test_invalid_event_interval_is_rejected():
    event = deepcopy(EVENT)
    event["documented_resume_utc"] = "2023-03-24T11:27:00Z"
    assert classify("2023-03-24T12:40:00Z", "2023-03-24T14:00:00Z", event=event, mode="outage_aware")["status"] == "rejected_unexplained_gap"


def test_adjacent_or_unrelated_gap_is_not_swallowed():
    result = classify("2023-03-24T14:00:00Z", "2023-03-24T14:01:00Z", mode="outage_aware")
    assert result["status"] == "rejected_unexplained_gap"


@pytest.mark.parametrize(("start", "end"), [
    ("2023-03-24T14:00:00Z", "2023-03-24T12:40:00Z"),
    ("2023-03-24T12:40:00", "2023-03-24T14:00:00Z"),
])
def test_invalid_intervals_fail_closed(start, end):
    with pytest.raises(ValueError):
        classify(start, end, mode="outage_aware")


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        classify("2023-03-24T12:40:00Z", "2023-03-24T14:00:00Z", mode="auto")
