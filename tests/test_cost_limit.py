import pytest
from career_pipeline.cost_limit import CostTracker, CostLimitExceeded


def test_cost_tracker_starts_at_zero():
    tracker = CostTracker(budget=10)
    assert tracker.calls == 0
    assert tracker.remaining == 10


def test_cost_tracker_records_call():
    tracker = CostTracker(budget=10)
    tracker.record_call('patina')
    assert tracker.calls == 1
    assert tracker.remaining == 9


def test_cost_tracker_enforces_budget():
    tracker = CostTracker(budget=2)
    tracker.record_call('patina')
    tracker.record_call('copyeditor')
    with pytest.raises(CostLimitExceeded):
        tracker.record_call('patina')


def test_cost_tracker_summary():
    tracker = CostTracker(budget=10)
    tracker.record_call('patina')
    tracker.record_call('patina')
    tracker.record_call('copyeditor')
    summary = tracker.summary()
    assert summary == {'patina': 2, 'copyeditor': 1, 'total': 3, 'budget': 10}


def test_cost_tracker_to_dict():
    tracker = CostTracker(budget=5)
    tracker.record_call('patina')
    d = tracker.to_dict()
    assert d['budget'] == 5
    assert d['calls']['patina'] == 1
    assert d['remaining'] == 4
