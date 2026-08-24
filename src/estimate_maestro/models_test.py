import pytest
from pydantic import ValidationError

from estimate_maestro.models import Estimate, MeetingParticipants, Scale


def test_expected_value_follows_the_pert_formula():
    estimate = Estimate(optimistic=8, likely=12, pessimistic=25)

    assert estimate.expected == pytest.approx((8 + 4 * 12 + 25) / 6)


def test_standard_deviation_is_the_range_over_six():
    estimate = Estimate(optimistic=8, likely=12, pessimistic=25)

    assert estimate.standard_deviation == pytest.approx((25 - 8) / 6)


def test_a_point_estimate_degenerates_without_special_casing():
    estimate = Estimate(optimistic=12, likely=12, pessimistic=12)

    assert estimate.expected == pytest.approx(12)
    assert estimate.standard_deviation == pytest.approx(0)


def test_the_scale_defaults_to_points():
    assert Estimate(optimistic=1, likely=1, pessimistic=1).scale is Scale.POINTS


def test_an_out_of_order_triple_is_rejected():
    with pytest.raises(ValidationError):
        Estimate(optimistic=20, likely=12, pessimistic=8)


def test_participants_count_internal_and_external_separately():
    participants = MeetingParticipants(internal=2, external=1, names=["me", "manager", "sales"])

    assert participants.internal == 2
    assert participants.external == 1
