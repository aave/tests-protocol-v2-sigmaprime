from brownie import (
    accounts, reverts, MathUtilsTest, chain, web3, WadRayMath
)

from Crypto.Hash import keccak
from helpers import (RAY, ray_mul, calculate_compound_interest, SECONDS_PER_YEAR)
import pytest


# Test `calculateLinearInterest()` for a simple test case
def test_linear_interest():
    # Deploy `MathUtilsTest`
    accounts[0].deploy(WadRayMath)
    math_utils = accounts[0].deploy(MathUtilsTest)

    # Setup parameters
    rate = RAY // 100 # 1.00%
    time_difference = 100 # seconds
    lastUpdateTimestamp = chain[web3.eth.blockNumber]['timestamp'] - time_difference
    result = (rate * time_difference // SECONDS_PER_YEAR) + RAY

    # `calculateLinearInterest()`
    assert result == math_utils.calculateLinearInterest(rate, lastUpdateTimestamp)


# Test `calculateLinearInterest()` for exactly one year
def test_linear_interest_one_year():
    # Deploy `MathUtilsTest`
    accounts[0].deploy(WadRayMath)
    math_utils = accounts[0].deploy(MathUtilsTest)

    # Time difference of 1 year => rate + RAY
    lastUpdateTimestamp = chain[web3.eth.blockNumber]['timestamp'] - SECONDS_PER_YEAR
    max_rate_for_1_year = ((1 << 256) - 1) // SECONDS_PER_YEAR
    for rate in [1, 3, 5, RAY // 100, RAY, max_rate_for_1_year]:
        assert math_utils.calculateLinearInterest(rate, lastUpdateTimestamp) == rate + RAY


# Test `calculateLinearInterest()` for a maximal rate values based on timestamps
def test_linear_interest_max_values():
    # Deploy `MathUtilsTest`
    accounts[0].deploy(WadRayMath)
    math_utils = accounts[0].deploy(MathUtilsTest)

    # Check multiplication overflows (note impossible for addition to overflow)
    for time_difference in [2, 15, 60, 3600, 3600*24, SECONDS_PER_YEAR, SECONDS_PER_YEAR * 10]:
        max_rate = (1 << 256) - 1
        if not time_difference == 0:
             max_rate = max_rate // time_difference
        lastUpdateTimestamp = chain[web3.eth.blockNumber]['timestamp'] - time_difference

        result = (max_rate * time_difference // SECONDS_PER_YEAR) + RAY
        assert result == math_utils.calculateLinearInterest(max_rate, lastUpdateTimestamp) # ensure does not revert

        with reverts('SafeMath: multiplication overflow'):
            math_utils.calculateLinearInterest(max_rate + 1, lastUpdateTimestamp)


# Test `calculateLinearInterest()` for zero rate or time difference
def test_linear_interest_zero():
    # Deploy `MathUtilsTest`
    accounts[0].deploy(WadRayMath)
    math_utils = accounts[0].deploy(MathUtilsTest)

    # rate = 0
    lastUpdateTimestamp = chain[web3.eth.blockNumber]['timestamp'] - 100
    assert RAY == math_utils.calculateLinearInterest(0, lastUpdateTimestamp)

    # time difference = 0
    lastUpdateTimestamp = chain[web3.eth.blockNumber]['timestamp']
    assert RAY == math_utils.calculateLinearInterest(10 * RAY, lastUpdateTimestamp)


# Test `calculateCompoundedInterest()`
def test_compound_interest():
    # Deploy `MathUtilsTest`
    accounts[0].deploy(WadRayMath)
    math_utils = accounts[0].deploy(MathUtilsTest)

    # Selection of values vs Python implementation
    for (rate , time_difference) in [(1, 1), (RAY, 1), (RAY, 2), (RAY, 15), (99 * RAY, 100), (2 * RAY, SECONDS_PER_YEAR), (5 * RAY, 10 * SECONDS_PER_YEAR)]:
        lastUpdateTimestamp = chain[web3.eth.blockNumber]['timestamp'] - time_difference
        result = calculate_compound_interest(rate, time_difference)

        assert result == math_utils.calculateCompoundedInterest(rate, lastUpdateTimestamp)

    # Pre-calculated
    assert RAY + 1 == math_utils.calculateCompoundedInterest(SECONDS_PER_YEAR, 0, 1)


# Test `calculateCompoundedInterest()` overflows
def test_compound_interest_overflows():
    # Deploy `MathUtilsTest`
    accounts[0].deploy(WadRayMath)
    math_utils = accounts[0].deploy(MathUtilsTest)

    with reverts('48'):
        math_utils.calculateCompoundedInterest((1 << 256) - 1, 0, 1)
    with reverts('SafeMath: multiplication overflow'):
        math_utils.calculateCompoundedInterest(1, 0, (1 << 256) - 1)


# Test `calculateCompoundedInterest()` for zero rate or time difference
def test_compound_interest_zero():
    # Deploy `MathUtilsTest`
    accounts[0].deploy(WadRayMath)
    math_utils = accounts[0].deploy(MathUtilsTest)

    # rate = 0
    lastUpdateTimestamp = chain[web3.eth.blockNumber]['timestamp'] - 100
    assert RAY == math_utils.calculateCompoundedInterest(0, lastUpdateTimestamp)

    # time difference = 0
    lastUpdateTimestamp = chain[web3.eth.blockNumber]['timestamp']
    assert RAY == math_utils.calculateCompoundedInterest(10 * RAY, lastUpdateTimestamp)
