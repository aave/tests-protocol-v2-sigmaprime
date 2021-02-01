from brownie import (
    accounts, reverts, PercentageMathTest,
)

from Crypto.Hash import keccak
from helpers import (PERCENTAGE_FACTOR, HALF_PERCENT)
import pytest



# Tests `percentMul()`
def test_percent_mul():
    # Deploy `PercentageMathTest`
    percent_math = accounts[0].deploy(PercentageMathTest)

    max_value_for_100_percent = ((1 << 256) - 1 - HALF_PERCENT) // PERCENTAGE_FACTOR

    # a * 100% = a
    for a in [1, 3, 10_000, max_value_for_100_percent]:
        assert percent_math.percentMul(a, PERCENTAGE_FACTOR) == a

    # a * b% = (a * b + 5_000) // 10_000
    for (a, b) in [(1, 1), (3, 1), (10_000, 1), (1234, 5432), ((1 << 100) - 1, (1 << 13) - 1)]:
        assert percent_math.percentMul(a, b) == (a * b + HALF_PERCENT) // PERCENTAGE_FACTOR

    # pre-calculated: a * b% = c
    for (a, b, c) in [(2, 5_000, 1), (99, 3_333, 33), (100, 3_333, 33), (101, 3_333, 34), (10_000, 1, 1)]:
        assert percent_math.percentMul(a, b) == c


# Tests `percentMul()` when either parameters is zero
def test_percent_mul_zero():
    # Deploy `PercentageMathTest`
    percent_math = accounts[0].deploy(PercentageMathTest)

    assert percent_math.percentMul(10_000, 0) == 0
    assert percent_math.percentMul(0, 10_000) == 0
    assert percent_math.percentMul(0, 0) == 0


# Tests `percentMul()` overflow
def test_percent_mul_overflow():
    # Deploy `PercentageMathTest`
    percent_math = accounts[0].deploy(PercentageMathTest)

    for i in [1, 10_000, (1 << 256) - 1]:
        percent = i
        max_value = ((1 << 256) - 1 - HALF_PERCENT) // percent
        assert percent_math.percentMul(max_value, percent) == (max_value * percent + HALF_PERCENT) // PERCENTAGE_FACTOR
        with reverts('48'):
            percent_math.percentMul(max_value + 1, percent)


# Tests `percentDiv()`
def test_percent_div():
    # Deploy `PercentageMathTest`
    percent_math = accounts[0].deploy(PercentageMathTest)

    max_value_for_100_percent = ((1 << 256) - 1 - HALF_PERCENT) // PERCENTAGE_FACTOR

    # a / 100% = a
    for a in [1, 3, 10_000, max_value_for_100_percent]:
        assert percent_math.percentDiv(a, PERCENTAGE_FACTOR) == a

    # a / b% = (a * 10_000 + b // 2) // b
    for (a, b) in [(1, 1), (3, 1), (10_000, 1), (1234, 5432), ((1 << 100) - 1, (1 << 13) - 1)]:
        assert percent_math.percentDiv(a, b) == (a * PERCENTAGE_FACTOR + b // 2) // b

    # pre-calculated: a / b% = c
    for (a, b, c) in [(2, 20_000, 1), (100, 5_000, 200), (3, 3_333, 9), (5, 2_000, 25)]:
        assert percent_math.percentDiv(a, b) == c


# Tests `percentDiv()` by 0%
def test_percent_div_zero():
    # Deploy `PercentageMathTest`
    percent_math = accounts[0].deploy(PercentageMathTest)

    with reverts('50'):
        percent_math.percentDiv(1, 0)

    with reverts('50'):
        percent_math.percentDiv(0, 0)


# Tests `percentDiv()` overflow
def test_percent_div_overflow():
    # Deploy `PercentageMathTest`
    percent_math = accounts[0].deploy(PercentageMathTest)

    for i in [1, 10_000, (1 << 256) - 1]:
        percent = i
        max_value = ((1 << 256) - 1 - percent // 2) // PERCENTAGE_FACTOR
        assert percent_math.percentDiv(max_value, percent) == (max_value * PERCENTAGE_FACTOR + percent // 2) // percent
        with reverts('48'):
            percent_math.percentDiv(max_value + 1, percent)
