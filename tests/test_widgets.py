import pytest

from cubo.voice.timing import Timing
from cubo.web.widgets import average_timing, format_seconds


@pytest.mark.parametrize(
    "value, expected",
    [(None, "—"), (0, "0,0 s"), (1.84, "1,8 s"), (12.06, "12,1 s")],
)
def test_format_seconds(value, expected):
    assert format_seconds(value) == expected


def test_average_of_each_stage():
    average = average_timing([Timing(0.5, 1.0, 2.0, 1.5, 3.0), Timing(1.5, 3.0, 4.0, 2.5, 5.0)])

    assert average == Timing(1.0, 2.0, 3.0, 2.0, 4.0)


def test_average_ignores_the_requests_where_a_stage_did_not_happen():
    average = average_timing([Timing(0.5, None, 2.0, 1.5, 3.0), Timing(0.5, 3.0, 2.0, None, 3.0)])

    assert average.first_text == 3.0
    assert average.first_sound == 1.5


def test_average_of_nothing_is_nothing():
    assert average_timing([]) is None


def test_a_stage_that_never_happened_stays_absent_in_the_average():
    average = average_timing([Timing(0.5, None, 2.0, None, 3.0)])

    assert (average.first_text, average.first_sound) == (None, None)
