import pytest

from solution import solve


@pytest.mark.parametrize(
    "nums,expected",
    [
        ([], 0),
    ],
)
def test_solve(nums, expected):
    assert solve(nums) == expected
