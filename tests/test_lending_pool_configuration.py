import brownie
from brownie import (
    accounts, AToken,  AToken2, AaveOracle, Contract, DelegationAwareAToken,
    DefaultReserveInterestRateStrategy, GenericLogic,
    LendingPool, LendingPoolAddressesProvider, LendingPoolConfigurator,
    LendingPoolAddressesProviderRegistry, LendingPoolCollateralManager,
    ReserveLogic, reverts, StableDebtToken, StableDebtToken2, ValidationLogic, VariableDebtToken,
    VariableDebtToken2, WETH9, ZERO_ADDRESS,
)

from Crypto.Hash import keccak
from helpers import (
    BORROWING_ENABLED_START_BIT_POSITION, LIQUIDATION_THRESHOLD_START_BIT_POSITION,
    IS_FROZEN_START_BIT_POSITION, IS_ACTIVE_START_BIT_POSITION, RESERVE_DECIMALS_START_BIT_POSITION, setup_and_deploy,
    setup_and_deploy_configuration, STABLE_BORROWING_ENABLED_START_BIT_POSITION, RAY, RESERVE_FACTOR_START_BIT_POSITION,
    LIQUIDATION_BONUS_START_BIT_POSITION,
)
import pytest


# Test `initReserve()`
def test_init_reserve():
    # Deploy and initialize contracts
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle) = setup_and_deploy()

    # Deploy contracts required for a Reserve
    incentivesController = ZERO_ADDRESS
    reserveTreasuryAddress = ZERO_ADDRESS
    weth = accounts[0].deploy(WETH9)
    atoken = accounts[0].deploy(
        AToken,
        lending_pool.address,
        weth,
        reserveTreasuryAddress,
        'Aave interest bearing WETH',
        'aWETH',
        incentivesController
    )
    stable_debt = accounts[0].deploy(
        StableDebtToken,
        lending_pool.address,
        weth.address,
        "Aave stable debt bearing WETH",
        "stableDebWETHt",
        incentivesController,
    )
    variable_debt = accounts[0].deploy(
        VariableDebtToken,
        lending_pool.address,
        weth.address,
        "Aave variable debt bearing WETH",
        "variableDebt",
        incentivesController,
    )

    optimalUtilizationRate = 20_000
    baseVariableBorrowRate = 2
    variableRateSlope1 = 3
    variableRateSlope2 = 4
    stableRateSlope1 = 5
    stableRateSlope2 = 6
    strategy = accounts[0].deploy(
        DefaultReserveInterestRateStrategy,
        addresses_provider.address,
        optimalUtilizationRate,
        baseVariableBorrowRate,
        variableRateSlope1,
        variableRateSlope2,
        stableRateSlope1,
        stableRateSlope2,
    )

    # initReserve()
    tx = configurator.initReserve(
        atoken.address,
        stable_debt.address,
        variable_debt.address,
        weth.decimals(),
        strategy.address,
        {'from': pool_admin},
    )

    # Verify logs
    init_event = tx.events['ReserveInitialized']
    assert init_event['asset'] == weth.address
    assert init_event['interestRateStrategyAddress'] == strategy.address
    assert init_event['aToken'] != ZERO_ADDRESS
    assert init_event['stableDebtToken'] != ZERO_ADDRESS
    assert init_event['variableDebtToken'] != ZERO_ADDRESS

    # Check configurations have been updated in `LendingPool`
    assert lending_pool.getReservesList() == [weth.address]
    assert lending_pool.paused() == False
    reserve_config = ((1 << IS_ACTIVE_START_BIT_POSITION) | (18 << RESERVE_DECIMALS_START_BIT_POSITION),)
    assert lending_pool.getConfiguration(weth.address) == reserve_config
    # Note we must use the proxy addresses for AToken, StableDebt, VariableDebt
    reserve_data = (reserve_config, RAY,  RAY, 0, 0, 0, 0, init_event['aToken'], init_event['stableDebtToken'], init_event['variableDebtToken'], strategy.address, 0)
    assert lending_pool.getReserveData(weth.address) == reserve_data


# Test `initReserve()` being called twice
def test_init_reserve_twice():
    # Deploy and initialize contracts
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle) = setup_and_deploy()

    # Deploy contracts required for a Reserve
    incentivesController = ZERO_ADDRESS
    reserveTreasuryAddress = ZERO_ADDRESS
    weth = accounts[0].deploy(WETH9)
    atoken = accounts[0].deploy(
        AToken,
        lending_pool.address,
        weth,
        reserveTreasuryAddress,
        'Aave interest bearing WETH',
        'aWETH',
        incentivesController
    )
    stable_debt = accounts[0].deploy(
        StableDebtToken,
        lending_pool.address,
        weth.address,
        "Aave stable debt bearing WETH",
        "stableDebWETHt",
        incentivesController,
    )
    variable_debt = accounts[0].deploy(
        VariableDebtToken,
        lending_pool.address,
        weth.address,
        "Aave variable debt bearing WETH",
        "variableDebt",
        incentivesController,
    )

    optimalUtilizationRate = 10_000
    baseVariableBorrowRate = 200
    variableRateSlope1 = 300
    variableRateSlope2 = 400
    stableRateSlope1 = 100
    stableRateSlope2 = 200
    strategy = accounts[0].deploy(
        DefaultReserveInterestRateStrategy,
        addresses_provider.address,
        optimalUtilizationRate,
        baseVariableBorrowRate,
        variableRateSlope1,
        variableRateSlope2,
        stableRateSlope1,
        stableRateSlope2,
    )

    # initReserve()
    tx = configurator.initReserve(
        atoken.address,
        stable_debt.address,
        variable_debt.address,
        weth.decimals(),
        strategy.address,
        {'from': pool_admin},
    )

    # initReserve() again
    with reverts('32'):
        tx = configurator.initReserve(
            atoken.address,
            stable_debt.address,
            variable_debt.address,
            1,
            strategy.address,
            {'from': pool_admin},
        )


# Test `onlyPoolAdmin` modifier
def test_only_pool_admin():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration()

    # initReserve() not from pool admin
    with reverts('33'):
        configurator.initReserve(
            atoken.address,
            stable_debt.address,
            variable_debt.address,
            weth.decimals(),
            strategy.address,
            {'from': emergency_admin},
        )

    # initReserve() from pool admin does not revert
    configurator.initReserve(
        atoken.address,
        stable_debt.address,
        variable_debt.address,
        weth.decimals(),
        strategy.address,
        {'from': pool_admin},
    )


# Test `setPause()`
def test_set_pool_pause():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration()

    # Pre-checks
    isPaused = False
    assert lending_pool.paused() == isPaused

    # setPoolPaused()
    isPaused = True
    tx = configurator.setPoolPause(isPaused, {'from': emergency_admin})

    # Check values and logs
    assert lending_pool.paused() == isPaused
    assert 'Paused' in tx.events

    # setPoolPaused() again
    isPaused = False
    tx = configurator.setPoolPause(isPaused, {'from': emergency_admin})

    # Check values and logs
    assert lending_pool.paused() == isPaused
    assert 'Unpaused' in tx.events

    # setPoolPaused() again (while paused)
    isPaused = False
    tx = configurator.setPoolPause(isPaused, {'from': emergency_admin})

    # Check values and logs
    assert lending_pool.paused() == isPaused
    assert 'Unpaused' in tx.events


# Test `onlyEmergencyAdmin()`
def test_only_emergency_admin():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration()

    # setPoolPaused() not from emergency admin
    with reverts():
        configurator.setPoolPause(True, {'from': pool_admin})

    # setPoolPaused from emergency admin does not revert
    configurator.setPoolPause(False, {'from': emergency_admin})


# Test `updateStableDebtToken()`
def test_update_stable_debt_token():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration()

    # initReserve()
    tx = configurator.initReserve(
        atoken.address,
        stable_debt.address,
        variable_debt.address,
        weth.decimals(),
        strategy.address,
        {'from': pool_admin},
    )

    reserve_data = lending_pool.getReserveData(weth.address)

    (_, _, _, _, _, _, _, _, stable_debt_proxy_address, _, _, _) = reserve_data
    stable_debt_proxy = Contract.from_abi(StableDebtToken, stable_debt_proxy_address, stable_debt.abi)

    # Deploy a second StableDebtToken
    stable_debt2 = accounts[0].deploy(
        StableDebtToken2,
        lending_pool.address,
        weth.address,
        "Aave stable debt bearing WETH",
        "stableDebtWETH",
        ZERO_ADDRESS,
    )

    # updateStableDebtToken()
    tx = configurator.updateStableDebtToken(weth.address, stable_debt2.address, {'from': pool_admin})

    # Verify update
    assert reserve_data == lending_pool.getReserveData(weth.address), "reserve data should not have changed"
    stable_debt_proxy.DEBT_TOKEN_REVISION() == 2, "Updated to revision two"

    assert tx.events['StableDebtTokenUpgraded']['asset'] == weth.address
    assert tx.events['StableDebtTokenUpgraded']['proxy'] == stable_debt_proxy_address
    assert tx.events['StableDebtTokenUpgraded']['implementation'] == stable_debt2.address


# Test `updateVariableDebtToken()`
def test_update_variable_debt_token():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration()

    # initReserve()
    tx = configurator.initReserve(
        atoken.address,
        stable_debt.address,
        variable_debt.address,
        weth.decimals(),
        strategy.address,
        {'from': pool_admin},
    )

    reserve_data = lending_pool.getReserveData(weth.address)

    (_, _, _, _, _, _, _, _, _, variable_debt_proxy_address, _, _) = reserve_data
    variable_debt_proxy = Contract.from_abi(VariableDebtToken, variable_debt_proxy_address, variable_debt.abi)

    # Deploy a second VariableDebtToken
    variable_debt2 = accounts[0].deploy(
        VariableDebtToken2,
        lending_pool.address,
        weth.address,
        "Aave stable debt bearing WETH",
        "stableDebtWETH",
        ZERO_ADDRESS,
    )

    # updateVariableDebtToken()
    tx = configurator.updateVariableDebtToken(weth.address, variable_debt2.address, {'from': pool_admin})

    # Verify update
    assert reserve_data == lending_pool.getReserveData(weth.address), "reserve data should not have changed"
    variable_debt_proxy.DEBT_TOKEN_REVISION() == 2, "Updated to revision two"

    assert tx.events['VariableDebtTokenUpgraded']['asset'] == weth.address
    assert tx.events['VariableDebtTokenUpgraded']['proxy'] == variable_debt_proxy_address
    assert tx.events['VariableDebtTokenUpgraded']['implementation'] == variable_debt2.address


# Test `updateAToken()`
def test_update_atoken():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration()

    # initReserve()
    tx = configurator.initReserve(
        atoken.address,
        stable_debt.address,
        variable_debt.address,
        weth.decimals(),
        strategy.address,
        {'from': pool_admin},
    )

    reserve_data = lending_pool.getReserveData(weth.address)

    (_, _, _, _, _, _, _, atoken_proxy_address, _, _, _, _) = reserve_data
    atoken_proxy = Contract.from_abi(AToken, atoken_proxy_address, atoken.abi)

    # Deploy a second VariableDebtToken
    atoken2 = accounts[0].deploy(
        AToken2,
        lending_pool.address,
        weth.address,
        ZERO_ADDRESS,
        "Aave stable debt bearing WETH",
        "stableDebtWETH",
        ZERO_ADDRESS,
    )

    # updateAToken()
    tx = configurator.updateAToken(weth.address, atoken2.address, {'from': pool_admin})

    # Verify update
    assert reserve_data == lending_pool.getReserveData(weth.address), "reserve data should not have changed"
    atoken_proxy.ATOKEN_REVISION() == 2, "Updated to revision two"

    assert tx.events['ATokenUpgraded']['asset'] == weth.address
    assert tx.events['ATokenUpgraded']['proxy'] == atoken_proxy_address
    assert tx.events['ATokenUpgraded']['implementation'] == atoken2.address


# Test `freezeReserve()` and `unfreezeReserve()`
def test_reserve_freezing():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration()

    # initReserve()
    tx = configurator.initReserve(
        atoken.address,
        stable_debt.address,
        variable_debt.address,
        weth.decimals(),
        strategy.address,
        {'from': pool_admin},
    )

    # Pre-checks
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << IS_FROZEN_START_BIT_POSITION) == 0

    # freezeReserve
    tx = configurator.freezeReserve(weth.address, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << IS_FROZEN_START_BIT_POSITION) != 0
    assert tx.events['ReserveFrozen']['asset'] == weth.address

    # freezeReserve (even though it's already frozen)
    tx = configurator.freezeReserve(weth.address, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << IS_FROZEN_START_BIT_POSITION) != 0
    assert tx.events['ReserveFrozen']['asset'] == weth.address

    # unfreezeReserve
    tx = configurator.unfreezeReserve(weth.address, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << IS_FROZEN_START_BIT_POSITION) == 0
    assert tx.events['ReserveUnfrozen']['asset'] == weth.address

    # unfreezeReserve (even though it's already unfrozen)
    tx = configurator.unfreezeReserve(weth.address, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << IS_FROZEN_START_BIT_POSITION) == 0
    assert tx.events['ReserveUnfrozen']['asset'] == weth.address


# Test `activateReserve()` and `deactivateReserve()`
def test_reserve_activating():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration()

    # initReserve()
    tx = configurator.initReserve(
        atoken.address,
        stable_debt.address,
        variable_debt.address,
        weth.decimals(),
        strategy.address,
        {'from': pool_admin},
    )

    # Pre-checks
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << IS_ACTIVE_START_BIT_POSITION) != 0

    # deactivateReserve
    tx = configurator.deactivateReserve(weth.address, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << IS_ACTIVE_START_BIT_POSITION) == 0
    assert tx.events['ReserveDeactivated']['asset'] == weth.address

    # deactivateReserve (even though it's already deactivated)
    tx = configurator.deactivateReserve(weth.address, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << IS_ACTIVE_START_BIT_POSITION) == 0
    assert tx.events['ReserveDeactivated']['asset'] == weth.address

    # activateReserve
    tx = configurator.activateReserve(weth.address, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << IS_ACTIVE_START_BIT_POSITION) != 0
    assert tx.events['ReserveActivated']['asset'] == weth.address

    # activateReserve (even though it's already active)
    tx = configurator.activateReserve(weth.address, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << IS_ACTIVE_START_BIT_POSITION) != 0
    assert tx.events['ReserveActivated']['asset'] == weth.address

    # Deposit so there is liquidity
    depositer = accounts[4]
    amount = 1
    weth.deposit({'from': depositer, 'value': amount})
    weth.approve(lending_pool.address, amount, {'from': depositer})
    lending_pool.deposit(weth.address, amount, depositer, 0, {'from': depositer})

    # Deactivate reserve with balance
    with reverts('34'):
        configurator.deactivateReserve(weth.address, {'from': pool_admin})

    # TODO: Deactivate reserve when entire liquidity is borrowed

# Test `enableReserveStableRate()` and `disableReserveStableRate()`
def test_reserve_stable_rate_enabling():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration()

    # initReserve()
    tx = configurator.initReserve(
        atoken.address,
        stable_debt.address,
        variable_debt.address,
        weth.decimals(),
        strategy.address,
        {'from': pool_admin},
    )

    # Pre-checks
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << STABLE_BORROWING_ENABLED_START_BIT_POSITION) == 0

    # enableReserveStableRate
    tx = configurator.enableReserveStableRate(weth.address, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << STABLE_BORROWING_ENABLED_START_BIT_POSITION) != 0
    assert tx.events['StableRateEnabledOnReserve']['asset'] == weth.address

    # enableReserveStableRate again
    tx = configurator.enableReserveStableRate(weth.address, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << STABLE_BORROWING_ENABLED_START_BIT_POSITION) != 0
    assert tx.events['StableRateEnabledOnReserve']['asset'] == weth.address

    # disableReserveStableRate
    tx = configurator.disableReserveStableRate(weth.address, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << STABLE_BORROWING_ENABLED_START_BIT_POSITION) == 0
    assert tx.events['StableRateDisabledOnReserve']['asset'] == weth.address

    # disableReserveStableRate again
    tx = configurator.disableReserveStableRate(weth.address, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << STABLE_BORROWING_ENABLED_START_BIT_POSITION) == 0
    assert tx.events['StableRateDisabledOnReserve']['asset'] == weth.address


# Test `enableBorrowingOnReserve()` and `disableBorrowingOnReserve()`
def test_reserve_borrowing_enabling():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration()

    # initReserve()
    tx = configurator.initReserve(
        atoken.address,
        stable_debt.address,
        variable_debt.address,
        weth.decimals(),
        strategy.address,
        {'from': pool_admin},
    )

    # Pre-checks
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << STABLE_BORROWING_ENABLED_START_BIT_POSITION) == 0

    # enableBorrowingOnReserve
    tx = configurator.enableBorrowingOnReserve(weth.address, False, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << BORROWING_ENABLED_START_BIT_POSITION) != 0
    assert reserve_config & (1 << STABLE_BORROWING_ENABLED_START_BIT_POSITION) == 0
    assert tx.events['BorrowingEnabledOnReserve']['asset'] == weth.address
    assert tx.events['BorrowingEnabledOnReserve']['stableRateEnabled'] == False

    # enableBorrowingOnReserve again
    tx = configurator.enableBorrowingOnReserve(weth.address, True, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << BORROWING_ENABLED_START_BIT_POSITION) != 0
    assert reserve_config & (1 << STABLE_BORROWING_ENABLED_START_BIT_POSITION) != 0
    assert tx.events['BorrowingEnabledOnReserve']['asset'] == weth.address
    assert tx.events['BorrowingEnabledOnReserve']['stableRateEnabled'] == True

    # disableBorrowingOnReserve
    tx = configurator.disableBorrowingOnReserve(weth.address, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << BORROWING_ENABLED_START_BIT_POSITION) == 0
    assert reserve_config & (1 << STABLE_BORROWING_ENABLED_START_BIT_POSITION) != 0
    assert tx.events['BorrowingDisabledOnReserve']['asset'] == weth.address

    # disableBorrowingOnReserve again
    tx = configurator.disableBorrowingOnReserve(weth.address, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << BORROWING_ENABLED_START_BIT_POSITION) == 0
    assert reserve_config & (1 << STABLE_BORROWING_ENABLED_START_BIT_POSITION) != 0
    assert tx.events['BorrowingDisabledOnReserve']['asset'] == weth.address


# Test `setReserveFactor()`
def test_set_reserve_factor():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration()

    # initReserve()
    tx = configurator.initReserve(
        atoken.address,
        stable_debt.address,
        variable_debt.address,
        weth.decimals(),
        strategy.address,
        {'from': pool_admin},
    )

    # Pre-checks
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (1 << STABLE_BORROWING_ENABLED_START_BIT_POSITION) == 0

    # setReserveFactor
    reserve_factor = 33_333
    tx = configurator.setReserveFactor(weth.address, reserve_factor, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & ((2**16 - 1) << RESERVE_FACTOR_START_BIT_POSITION) == reserve_factor << RESERVE_FACTOR_START_BIT_POSITION
    assert tx.events['ReserveFactorChanged']['asset'] == weth.address
    assert tx.events['ReserveFactorChanged']['factor'] == reserve_factor

    # setReserveFactor again
    reserve_factor = 0
    tx = configurator.setReserveFactor(weth.address, reserve_factor, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & ((2**16 - 1) << RESERVE_FACTOR_START_BIT_POSITION) == reserve_factor << RESERVE_FACTOR_START_BIT_POSITION
    assert tx.events['ReserveFactorChanged']['asset'] == weth.address
    assert tx.events['ReserveFactorChanged']['factor'] == reserve_factor

    # setReserveFactor too high
    with reverts('71'):
        reserve_factor = 1 << 16
        configurator.setReserveFactor(weth.address, reserve_factor, {'from': pool_admin})


# Test `setReserveInterestRateStrategyAddress()`
def test_set_reserve_interest_rate_strategy_address():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration()

    # initReserve()
    tx = configurator.initReserve(
        atoken.address,
        stable_debt.address,
        variable_debt.address,
        weth.decimals(),
        strategy.address,
        {'from': pool_admin},
    )

    # Deploy another `DefaultReserveInterestRateStrategy`
    random_rate = 7
    strategy2 = accounts[0].deploy(
        DefaultReserveInterestRateStrategy,
        addresses_provider.address,
        random_rate,
        random_rate,
        random_rate,
        random_rate,
        random_rate,
        random_rate,
    )

    # Pre-checks
    (_, _, _, _, _, _, _, _, _, _, strategy_address, _) = lending_pool.getReserveData(weth.address)
    assert strategy_address == strategy.address

    # setReserveInterestRateStrategyAddress
    tx = configurator.setReserveInterestRateStrategyAddress(weth.address, strategy2.address, {'from': pool_admin})

    # Check logs and values
    (_, _, _, _, _, _, _, _, _, _, strategy_address, _) = lending_pool.getReserveData(weth.address)
    assert strategy_address == strategy2.address
    assert tx.events['ReserveInterestRateStrategyChanged']['asset'] == weth.address
    assert tx.events['ReserveInterestRateStrategyChanged']['strategy'] == strategy2.address

    # setReserveInterestRateStrategyAddress again
    tx = configurator.setReserveInterestRateStrategyAddress(weth.address, strategy2.address, {'from': pool_admin})

    # Check logs and values
    (_, _, _, _, _, _, _, _, _, _, strategy_address, _) = lending_pool.getReserveData(weth.address)
    assert strategy_address == strategy2.address
    assert tx.events['ReserveInterestRateStrategyChanged']['asset'] == weth.address
    assert tx.events['ReserveInterestRateStrategyChanged']['strategy'] == strategy2.address


# Test `configureReserveAsCollateral()`
def test_configure_reserve_as_collateral():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration()

    # initReserve()
    tx = configurator.initReserve(
        atoken.address,
        stable_debt.address,
        variable_debt.address,
        weth.decimals(),
        strategy.address,
        {'from': pool_admin},
    )

    # Pre-checks
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (2**16 - 1) == 0
    assert reserve_config & ((2**16 - 1) << LIQUIDATION_THRESHOLD_START_BIT_POSITION) == 0
    assert reserve_config & ((2**16 - 1) << LIQUIDATION_BONUS_START_BIT_POSITION) == 0

    # configureReserveAsCollateral
    ltv = 3_000 # 30%
    threshold = 5_000 # 50%
    bonus = 10_100 # 101%
    tx = configurator.configureReserveAsCollateral(weth.address, ltv, threshold, bonus, {'from': pool_admin})

    # Check logs and values
    (reserve_config,) = lending_pool.getConfiguration(weth.address)
    assert reserve_config & (2**16 - 1) == ltv
    assert reserve_config & ((2**16 - 1) << LIQUIDATION_THRESHOLD_START_BIT_POSITION) == threshold << LIQUIDATION_THRESHOLD_START_BIT_POSITION
    assert reserve_config & ((2**16 - 1) << LIQUIDATION_BONUS_START_BIT_POSITION) == bonus << LIQUIDATION_BONUS_START_BIT_POSITION
    assert tx.events['CollateralConfigurationChanged']['asset'] == weth.address
    assert tx.events['CollateralConfigurationChanged']['ltv'] == ltv
    assert tx.events['CollateralConfigurationChanged']['liquidationThreshold'] == threshold
    assert tx.events['CollateralConfigurationChanged']['liquidationBonus'] == bonus

    ### Check invalid configs

    # LTV > threshold
    with reverts('75'):
        ltv = 4_100 # 51%
        threshold = 4_000 # 50%
        bonus = 10_100 # 101%
        configurator.configureReserveAsCollateral(weth.address, ltv, threshold, bonus, {'from': pool_admin})

    # bonus = 100%
    with reverts('75'):
        ltv = 3_000 # 30%
        threshold = 5_000 # 50%
        bonus = 10_000 # 100%
        configurator.configureReserveAsCollateral(weth.address, ltv, threshold, bonus, {'from': pool_admin})

    # bonus < 100%
    with reverts('75'):
        ltv = 3_000 # 30%
        threshold = 5_000 # 50%
        bonus = 9_900 # 99%
        configurator.configureReserveAsCollateral(weth.address, ltv, threshold, bonus, {'from': pool_admin})

    # threshold + absolute bonus > 100%
    with reverts('75'):
        ltv = 3_000 # 30%
        threshold = 5_000 # 50%
        bonus = 15_100 # 151%
        configurator.configureReserveAsCollateral(weth.address, ltv, threshold, bonus, {'from': pool_admin})

    # threshold = 0; bonus != 0
    with reverts('75'):
        ltv = 0 # 0%
        threshold = 0 # 0%
        bonus = 1 # 1%
        configurator.configureReserveAsCollateral(weth.address, ltv, threshold, bonus, {'from': pool_admin})
