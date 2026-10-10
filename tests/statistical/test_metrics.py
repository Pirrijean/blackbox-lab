import pytest

from blackbox_lab.core.metrics import calculate_metrics


def test_empty_sample_is_not_zero():
    with pytest.raises(ValueError):
        calculate_metrics([])


def test_single_sample_has_unknown_uncertainty():
    result = calculate_metrics([8.0])
    assert result.mean == 8.0
    assert result.std_dev is None
    assert result.confidence_interval_95 is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_invalid_measurement_is_rejected(value):
    with pytest.raises(ValueError):
        calculate_metrics([1.0, value])


def test_small_sample_uses_student_interval():
    result = calculate_metrics([1.0, 2.0, 3.0])
    lower, upper = result.confidence_interval_95

    assert result.mean == pytest.approx(2.0)
    assert result.std_dev == pytest.approx(1.0)
    assert lower == pytest.approx(-0.4841377, abs=1e-6)
    assert upper == pytest.approx(4.4841377, abs=1e-6)
