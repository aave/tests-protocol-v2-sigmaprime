from brownie import (
    accounts, AToken, AaveOracle, DelegationAwareAToken,
    DefaultReserveInterestRateStrategy, GenericLogic,
    LendingPool, LendingPoolAddressesProvider, LendingPoolConfigurator,
    LendingPoolAddressesProviderRegistry, LendingPoolCollateralManager, MintableDelegationERC20,
    reverts, ReserveLogic, StableDebtToken, ValidationLogic, VariableDebtToken,
    WETH9, ZERO_ADDRESS, web3, FlashLoanTests
)

from helpers import (
    wad_to_ray, ray_div, ray_mul, wad_div, RAY, WAD, setup_and_deploy_configuration_with_reserve,
    allow_reserve_collateral_and_borrowing, MARKET_BORROW_RATE, setup_and_deploy, deploy_default_strategy,
    setup_new_reserve, WEI, INTEREST_RATE_MODE_STABLE, INTEREST_RATE_MODE_NONE, INTEREST_RATE_MODE_VARIABLE,
    calculate_stable_borrow_rate, calculate_variable_borrow_rate,
    calculate_compound_interest, RAY_DIV_WAD, calculate_linear_interest, calculate_overall_borrow_rate,
    calculate_overall_stable_rate, percent_mul, setup_borrow, percent_div,
)

import pytest
import time


################
# initReserve()
################


# Check the initial state after `initReserve()` note full functionality tested in `test_lending_pool_configuration.py`
def test_initial_reserve_state():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Check `LendingPool` state without any deposits or configurations
    assert (0,) == lending_pool.getUserConfiguration(accounts[0])
    (total_collateral, total_debt, available_borrow, current_threshold, current_ltv, health_factor) = lending_pool.getUserAccountData(accounts[0])
    assert total_debt == 0
    assert current_ltv == 0
    assert total_collateral == 0
    assert available_borrow == 0
    assert health_factor == (1 << 256) - 1 # uint256(-1)

    # Configure reserve collateral and borrowing
    (ltv, threhold, bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Check `LendingPool` state with borrowing and collateral but without any deposits
    assert (0,) == lending_pool.getUserConfiguration(accounts[0])
    (total_collateral, total_debt, available_borrow, current_threshold, current_ltv, health_factor) = lending_pool.getUserAccountData(accounts[0])
    assert total_debt == 0
    assert current_ltv == 0
    assert total_collateral == 0
    assert available_borrow == 0
    assert health_factor == (1 << 256) - 1 # uint256(-1)


############
# deposit()
############


# Test `deposit()` with collateral and borrowing on but no outstanding borrowings
def test_deposits_no_collateral_and_borrowings():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    depositor_b = accounts[5]
    deposit_amount = 10_000_000_000
    deposit_amount_b = 22_000_000_000_000_000_000
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositor})
    weth.deposit({'from': depositor_b, 'value': deposit_amount_b})
    weth.approve(lending_pool, deposit_amount_b, {'from': depositor_b})

    # Turn on collateral and borrowing
    (ltv, threhold, bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # deposit()
    referral_code = 0
    tx = lending_pool.deposit(weth, deposit_amount, depositor, referral_code, {'from': depositor})

    # Check logs `LendingPool`
    assert tx.events['Deposit']['reserve'] == weth
    assert tx.events['Deposit']['user'] == depositor
    assert tx.events['Deposit']['onBehalfOf'] == depositor
    assert tx.events['Deposit']['amount'] == deposit_amount
    assert tx.events['Deposit']['referral'] == referral_code
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == 0
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == 0
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY
    assert tx.events['ReserveUsedAsCollateralEnabled']['reserve'] == weth
    assert tx.events['ReserveUsedAsCollateralEnabled']['user'] == depositor

    # Check logs `AToken`
    assert tx.events['Mint']['from'] == depositor
    assert tx.events['Mint']['value'] == deposit_amount
    assert tx.events['Mint']['index'] == RAY
    assert tx.events['Transfer'][0]['from'] == ZERO_ADDRESS
    assert tx.events['Transfer'][0]['value'] == deposit_amount
    assert tx.events['Transfer'][0]['to'] == depositor

    # Check logs `WETH`
    assert tx.events['Transfer'][1]['src'] == depositor
    assert tx.events['Transfer'][1]['dst'] == atoken
    assert tx.events['Transfer'][1]['wad'] == deposit_amount

    # Check `AToken` state
    assert atoken.balanceOf(depositor) == deposit_amount
    assert atoken.scaledBalanceOf(depositor) == deposit_amount
    assert atoken.totalSupply() == deposit_amount

    # Check `LendingPool` state
    (userConfig,) = lending_pool.getUserConfiguration(depositor)
    assert userConfig == 2**(0 * 2 + 1) # Collateral for reserve index 0
    (total_collateral, total_debt, available_borrow, current_threshold, current_ltv, health_factor) = lending_pool.getUserAccountData(depositor)
    assert total_debt == 0
    assert current_ltv == ltv
    assert total_collateral == deposit_amount
    assert available_borrow == deposit_amount * ltv // 10_000
    assert health_factor == (1 << 256) - 1 # uint256(-1)

    # `deposit()` a second time
    tx = lending_pool.deposit(weth, deposit_amount_b, depositor_b, referral_code, {'from': depositor_b})

    # Check logs `LendingPool`
    assert tx.events['Deposit']['reserve'] == weth
    assert tx.events['Deposit']['user'] == depositor_b
    assert tx.events['Deposit']['onBehalfOf'] == depositor_b
    assert tx.events['Deposit']['amount'] == deposit_amount_b
    assert tx.events['Deposit']['referral'] == referral_code
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == 0
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == 0
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY
    assert tx.events['ReserveUsedAsCollateralEnabled']['reserve'] == weth
    assert tx.events['ReserveUsedAsCollateralEnabled']['user'] == depositor_b

    # Check logs `AToken`
    assert tx.events['Mint']['from'] == depositor_b
    assert tx.events['Mint']['value'] == deposit_amount_b
    assert tx.events['Mint']['index'] == RAY
    assert tx.events['Transfer'][0]['from'] == ZERO_ADDRESS
    assert tx.events['Transfer'][0]['value'] == deposit_amount_b
    assert tx.events['Transfer'][0]['to'] == depositor_b

    # Check logs `WETH`
    assert tx.events['Transfer'][1]['src'] == depositor_b
    assert tx.events['Transfer'][1]['dst'] == atoken
    assert tx.events['Transfer'][1]['wad'] == deposit_amount_b

    # Check `AToken` state
    assert atoken.balanceOf(depositor_b) == deposit_amount_b
    assert atoken.scaledBalanceOf(depositor_b) == deposit_amount_b
    assert atoken.totalSupply() == deposit_amount + deposit_amount_b

    # Check `LendingPool` state
    (userConfig,) = lending_pool.getUserConfiguration(depositor_b)
    assert userConfig == 2**(0 * 2 + 1) # Collateral for reserve index 0
    (total_collateral, total_debt, available_borrow, current_threshold, current_ltv, health_factor) = lending_pool.getUserAccountData(depositor_b)
    assert total_debt == 0
    assert current_ltv == ltv
    assert total_collateral == deposit_amount_b
    assert available_borrow == deposit_amount_b * ltv // 10_000
    assert health_factor == (1 << 256) - 1 # uint256(-1)


# Tests the `onBehalfOf` parameter in `deposit()`
def test_simple_deposit_on_behalf_of():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    on_bahalf_of = accounts[5]
    deposit_amount = 1
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositor})

    # deposit()
    referral_code = 0
    tx = lending_pool.deposit(weth, deposit_amount, on_bahalf_of, referral_code, {'from': depositor})

    # Check logs `LendingPool`
    assert tx.events['Deposit']['reserve'] == weth
    assert tx.events['Deposit']['user'] == depositor
    assert tx.events['Deposit']['onBehalfOf'] == on_bahalf_of
    assert tx.events['Deposit']['amount'] == deposit_amount
    assert tx.events['Deposit']['referral'] == referral_code
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == 0
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == 0
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY
    assert tx.events['ReserveUsedAsCollateralEnabled']['reserve'] == weth
    assert tx.events['ReserveUsedAsCollateralEnabled']['user'] == on_bahalf_of

    # Check logs `AToken`
    assert tx.events['Mint']['from'] == on_bahalf_of
    assert tx.events['Mint']['value'] == deposit_amount
    assert tx.events['Mint']['index'] == RAY
    assert tx.events['Transfer'][0]['from'] == ZERO_ADDRESS
    assert tx.events['Transfer'][0]['value'] == deposit_amount
    assert tx.events['Transfer'][0]['to'] == on_bahalf_of

    # Check logs `WETH`
    assert tx.events['Transfer'][1]['src'] == depositor
    assert tx.events['Transfer'][1]['dst'] == atoken
    assert tx.events['Transfer'][1]['wad'] == deposit_amount

    # Check `AToken`
    assert atoken.balanceOf(on_bahalf_of) == deposit_amount
    assert atoken.scaledBalanceOf(on_bahalf_of) == deposit_amount
    assert atoken.totalSupply() == deposit_amount


# Test `deposit()` with collateral and borrowing off
def test_deposits_collateral_and_borrowings_off():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor_a = accounts[4]
    depositor_b = accounts[5]
    deposit_amount = 13
    deposit_amount_2 = 99_999
    deposit_amount_3 = 1_000_000_000_000_000_000
    weth.deposit({'from': depositor_a, 'value': deposit_amount + deposit_amount_2})
    weth.approve(lending_pool, deposit_amount + deposit_amount_2, {'from': depositor_a})
    weth.deposit({'from': depositor_b, 'value': deposit_amount_3})
    weth.approve(lending_pool, deposit_amount_3, {'from': depositor_b})

    # deposit()
    referral_code = 0
    tx = lending_pool.deposit(weth, deposit_amount, depositor_a, referral_code, {'from': depositor_a})

    # Check logs `LendingPool`
    assert tx.events['Deposit']['reserve'] == weth
    assert tx.events['Deposit']['user'] == depositor_a
    assert tx.events['Deposit']['onBehalfOf'] == depositor_a
    assert tx.events['Deposit']['amount'] == deposit_amount
    assert tx.events['Deposit']['referral'] == referral_code
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == 0
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == 0
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY
    assert tx.events['ReserveUsedAsCollateralEnabled']['reserve'] == weth
    assert tx.events['ReserveUsedAsCollateralEnabled']['user'] == depositor_a

    # Check logs `AToken`
    assert tx.events['Mint']['from'] == depositor_a
    assert tx.events['Mint']['value'] == deposit_amount
    assert tx.events['Mint']['index'] == RAY
    assert tx.events['Transfer'][0]['from'] == ZERO_ADDRESS
    assert tx.events['Transfer'][0]['value'] == deposit_amount
    assert tx.events['Transfer'][0]['to'] == depositor_a

    # Check logs `WETH`
    assert tx.events['Transfer'][1]['src'] == depositor_a
    assert tx.events['Transfer'][1]['dst'] == atoken
    assert tx.events['Transfer'][1]['wad'] == deposit_amount

    # Check AToken
    assert atoken.balanceOf(depositor_a) == deposit_amount
    assert atoken.scaledBalanceOf(depositor_a) == deposit_amount
    assert atoken.totalSupply() == deposit_amount

    # deposit() a second time
    tx = lending_pool.deposit(weth, deposit_amount_2, depositor_a, referral_code, {'from': depositor_a})

    # Check logs `LendingPool`
    assert tx.events['Deposit']['reserve'] == weth
    assert tx.events['Deposit']['user'] == depositor_a
    assert tx.events['Deposit']['onBehalfOf'] == depositor_a
    assert tx.events['Deposit']['amount'] == deposit_amount_2
    assert tx.events['Deposit']['referral'] == referral_code
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == 0
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == 0
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY
    assert not 'ReserveUsedAsCollateralEnabled' in tx.events

    # Check logs `AToken`
    assert tx.events['Mint']['from'] == depositor_a
    assert tx.events['Mint']['value'] == deposit_amount_2
    assert tx.events['Mint']['index'] == RAY
    assert tx.events['Transfer'][0]['from'] == ZERO_ADDRESS
    assert tx.events['Transfer'][0]['value'] == deposit_amount_2
    assert tx.events['Transfer'][0]['to'] == depositor_a

    # Check logs `WETH`
    assert tx.events['Transfer'][1]['src'] == depositor_a
    assert tx.events['Transfer'][1]['dst'] == atoken
    assert tx.events['Transfer'][1]['wad'] == deposit_amount_2

    # Check AToken
    assert atoken.balanceOf(depositor_a) == deposit_amount_2 + deposit_amount
    assert atoken.scaledBalanceOf(depositor_a) == deposit_amount_2 + deposit_amount
    assert atoken.totalSupply() == deposit_amount_2 + deposit_amount

    # deposit() a third time
    tx = lending_pool.deposit(weth, deposit_amount_3, depositor_b, referral_code, {'from': depositor_b})

    # Check logs `LendingPool`
    assert tx.events['Deposit']['reserve'] == weth
    assert tx.events['Deposit']['user'] == depositor_b
    assert tx.events['Deposit']['onBehalfOf'] == depositor_b
    assert tx.events['Deposit']['amount'] == deposit_amount_3
    assert tx.events['Deposit']['referral'] == referral_code
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == 0
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == 0
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY
    assert tx.events['ReserveUsedAsCollateralEnabled']['reserve'] == weth
    assert tx.events['ReserveUsedAsCollateralEnabled']['user'] == depositor_b

    # Check logs `AToken`
    assert tx.events['Mint']['from'] == depositor_b
    assert tx.events['Mint']['value'] == deposit_amount_3
    assert tx.events['Mint']['index'] == RAY
    assert tx.events['Transfer'][0]['from'] == ZERO_ADDRESS
    assert tx.events['Transfer'][0]['value'] == deposit_amount_3
    assert tx.events['Transfer'][0]['to'] == depositor_b

    # Check logs `WETH`
    assert tx.events['Transfer'][1]['src'] == depositor_b
    assert tx.events['Transfer'][1]['dst'] == atoken
    assert tx.events['Transfer'][1]['wad'] == deposit_amount_3

    # Check AToken
    assert atoken.balanceOf(depositor_b) == deposit_amount_3
    assert atoken.scaledBalanceOf(depositor_b) == deposit_amount_3
    assert atoken.totalSupply() == deposit_amount_2 + deposit_amount + deposit_amount_3


# Test `deposit()` with existing collateral and debt
def test_deposit_with_debt():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositor, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, ltv, threshold, bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()` variable debt
    variable_borrow_amount = terc20_deposit_amount * price // WEI // 10 # 10% of collateral in ETH
    tx = lending_pool.borrow(
        weth,
        variable_borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # `borrow()` stable debt
    web3.manager.request_blocking("evm_increaseTime", 4) # ensure some interest is accrued
    stable_borrow_amount = terc20_deposit_amount * price // WEI // 20 # 5% of collateral in ETH
    tx_b = lending_pool.borrow(
        weth,
        stable_borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Store previous state
    liquidity_index = tx_b.events['ReserveDataUpdated']['liquidityIndex']
    liquidity_rate = tx_b.events['ReserveDataUpdated']['liquidityRate']
    variable_borrow_index = tx_b.events['ReserveDataUpdated']['variableBorrowIndex']
    variable_rate = tx_b.events['ReserveDataUpdated']['variableBorrowRate']
    stable_rate = tx_b.events['ReserveDataUpdated']['stableBorrowRate']
    overall_stable_rate = tx_b.events['Mint']['avgStableRate']

    # Mint more tokens for deposit
    second_deposit = 99_000_000_000
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, second_deposit, {'from': depositor})

    # `deposit()` more collateral
    web3.manager.request_blocking("evm_increaseTime", 4) # ensure some interest is accrued
    tx_c = lending_pool.deposit(
        weth,
        second_deposit,
        depositor,
        0,
        {'from': depositor},
    )

    ### Python Calculations
    time_diff = tx_c.timestamp - tx_b.timestamp
    prev_stable_rate = stable_rate # SRt-1
    prev_overall_stable_rate = overall_stable_rate # ^SRt-1
    prev_total_stable_debt_with_interest = ray_mul(stable_borrow_amount, calculate_compound_interest(prev_overall_stable_rate, time_diff))

    # `updateState()`
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt

    # `updateInterestRates()`
    total_stable_debt = prev_total_stable_debt_with_interest # SDt
    total_variable_debt = ray_mul(variable_borrow_amount, variable_borrow_index) # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - stable_borrow_amount - variable_borrow_amount + second_deposit
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = prev_overall_stable_rate
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` logs
    assert tx_c.events['ReserveDataUpdated']['reserve'] == weth
    assert tx_c.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx_c.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx_c.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx_c.events['ReserveDataUpdated']['variableBorrowIndex'] == variable_borrow_index
    assert tx_c.events['ReserveDataUpdated']['liquidityIndex'] == liquidity_index
    assert tx_c.events['Deposit']['reserve'] == weth
    assert tx_c.events['Deposit']['user'] == depositor
    assert tx_c.events['Deposit']['onBehalfOf'] == depositor
    assert tx_c.events['Deposit']['amount'] == second_deposit
    assert tx_c.events['Deposit']['referral'] == 0

    # Check logs `AToken`
    assert tx_c.events['Mint']['from'] == depositor
    assert tx_c.events['Mint']['value'] == second_deposit
    assert tx_c.events['Mint']['index'] == liquidity_index
    assert tx_c.events['Transfer'][0]['from'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][0]['to'] == depositor
    assert tx_c.events['Transfer'][0]['value'] == second_deposit

    # Check `WETH` logs
    assert tx_c.events['Transfer'][1]['dst'] == weth_atoken
    assert tx_c.events['Transfer'][1]['src'] == depositor
    assert tx_c.events['Transfer'][1]['wad'] == second_deposit


############
# withdraw()
############


# Test `withdraw()` with borrowings and collateral off
def test_withdraw_borrowings_and_collateral_off():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor_a = accounts[4]
    amount = 13_000_000
    amount_2 = 99_999_000_000
    weth.deposit({'from': depositor_a, 'value': amount + amount_2})
    weth.approve(lending_pool, amount + amount_2, {'from': depositor_a})

    # `deposit()`
    referral_code = 0
    lending_pool.deposit(weth, amount, depositor_a, referral_code, {'from': depositor_a})

    # Check `AToken`
    assert atoken.balanceOf(depositor_a) == amount
    assert atoken.scaledBalanceOf(depositor_a) == amount
    assert atoken.totalSupply() == amount

    # `withdraw()` all to self
    tx = lending_pool.withdraw(weth, amount, depositor_a, {'from': depositor_a})

    # Check logs `LendingPool`
    assert tx.events['Withdraw']['reserve'] == weth
    assert tx.events['Withdraw']['user'] == depositor_a
    assert tx.events['Withdraw']['to'] == depositor_a
    assert tx.events['Withdraw']['amount'] == amount
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == 0
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == 0
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY
    assert tx.events['ReserveUsedAsCollateralDisabled']['reserve'] == weth
    assert tx.events['ReserveUsedAsCollateralDisabled']['user'] == depositor_a

    # Check logs `AToken`
    assert tx.events['Burn']['from'] == depositor_a
    assert tx.events['Burn']['target'] == depositor_a
    assert tx.events['Burn']['value'] == amount
    assert tx.events['Burn']['index'] == RAY
    assert tx.events['Transfer'][1]['to'] == ZERO_ADDRESS
    assert tx.events['Transfer'][1]['value'] == amount
    assert tx.events['Transfer'][1]['from'] == depositor_a

    # Check logs `WETH`
    assert tx.events['Transfer'][0]['dst'] == depositor_a
    assert tx.events['Transfer'][0]['src'] == atoken
    assert tx.events['Transfer'][0]['wad'] == amount

    # Check `AToken`
    assert atoken.balanceOf(depositor_a) == 0
    assert atoken.scaledBalanceOf(depositor_a) == 0
    assert atoken.totalSupply() == 0

    # `deposit()` a second time
    lending_pool.deposit(weth, amount_2, depositor_a, referral_code, {'from': depositor_a})

    # `withdraw()` half balance
    tx = lending_pool.withdraw(weth, amount_2 // 2, depositor_a, {'from': depositor_a})

    # Check logs `LendingPool`
    assert tx.events['Withdraw']['reserve'] == weth
    assert tx.events['Withdraw']['user'] == depositor_a
    assert tx.events['Withdraw']['to'] == depositor_a
    assert tx.events['Withdraw']['amount'] == amount_2 // 2
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == 0
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == 0
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY
    assert not 'ReserveUsedAsCollateralDisabled' in tx.events

    # Check logs `AToken`
    assert tx.events['Burn']['from'] == depositor_a
    assert tx.events['Burn']['target'] == depositor_a
    assert tx.events['Burn']['value'] == amount_2 // 2
    assert tx.events['Burn']['index'] == RAY
    assert tx.events['Transfer'][1]['to'] == ZERO_ADDRESS
    assert tx.events['Transfer'][1]['value'] == amount_2 // 2
    assert tx.events['Transfer'][1]['from'] == depositor_a

    # Check logs `WETH`
    assert tx.events['Transfer'][0]['dst'] == depositor_a
    assert tx.events['Transfer'][0]['src'] == atoken
    assert tx.events['Transfer'][0]['wad'] == amount_2 // 2

    # Check `AToken`
    remaining_balance = amount_2 - amount_2 // 2
    assert atoken.balanceOf(depositor_a) == remaining_balance
    assert atoken.scaledBalanceOf(depositor_a) == remaining_balance
    assert atoken.totalSupply() == remaining_balance

    # `withdraw()` max(uint256), withdraws all user balance
    tx = lending_pool.withdraw(weth, (1 << 256) - 1, depositor_a, {'from': depositor_a})

    # Check logs `LendingPool`
    assert tx.events['Withdraw']['reserve'] == weth
    assert tx.events['Withdraw']['user'] == depositor_a
    assert tx.events['Withdraw']['to'] == depositor_a
    assert tx.events['Withdraw']['amount'] == remaining_balance
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == 0
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == 0
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY
    assert tx.events['ReserveUsedAsCollateralDisabled']['reserve'] == weth
    assert tx.events['ReserveUsedAsCollateralDisabled']['user'] == depositor_a

    # Check logs `AToken`
    assert tx.events['Burn']['from'] == depositor_a
    assert tx.events['Burn']['target'] == depositor_a
    assert tx.events['Burn']['value'] == remaining_balance
    assert tx.events['Burn']['index'] == RAY
    assert tx.events['Transfer'][1]['to'] == ZERO_ADDRESS
    assert tx.events['Transfer'][1]['value'] == remaining_balance
    assert tx.events['Transfer'][1]['from'] == depositor_a

    # Check logs `WETH`
    assert tx.events['Transfer'][0]['dst'] == depositor_a
    assert tx.events['Transfer'][0]['src'] == atoken
    assert tx.events['Transfer'][0]['wad'] == remaining_balance

    # Check AToken
    assert atoken.balanceOf(depositor_a) == 0
    assert atoken.scaledBalanceOf(depositor_a) == 0
    assert atoken.totalSupply() == 0


# Test `withdraw()`, `to` parameter
def test_withdraw_to():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor_a = accounts[4]
    withdraw_to = accounts[5]
    amount = 13_000_000
    weth.deposit({'from': depositor_a, 'value': amount})
    weth.approve(lending_pool, amount, {'from': depositor_a})

    # `deposit()`
    referral_code = 0
    lending_pool.deposit(weth, amount, depositor_a, referral_code, {'from': depositor_a})

    # Check `AToken`
    assert atoken.balanceOf(depositor_a) == amount
    assert atoken.scaledBalanceOf(depositor_a) == amount
    assert atoken.totalSupply() == amount

    # `withdraw()` part to other user
    withdraw_amount = amount // 3
    tx = lending_pool.withdraw(weth, withdraw_amount, withdraw_to, {'from': depositor_a})

    # Check logs `LendingPool`
    assert tx.events['Withdraw']['reserve'] == weth
    assert tx.events['Withdraw']['user'] == depositor_a
    assert tx.events['Withdraw']['to'] == withdraw_to
    assert tx.events['Withdraw']['amount'] == withdraw_amount
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == 0
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == 0
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY

    # Check logs `AToken`
    assert tx.events['Burn']['from'] == depositor_a
    assert tx.events['Burn']['target'] == withdraw_to
    assert tx.events['Burn']['value'] == withdraw_amount
    assert tx.events['Burn']['index'] == RAY
    assert tx.events['Transfer'][1]['to'] == ZERO_ADDRESS
    assert tx.events['Transfer'][1]['value'] == withdraw_amount
    assert tx.events['Transfer'][1]['from'] == depositor_a

    # Check logs `WETH`
    assert tx.events['Transfer'][0]['dst'] == withdraw_to
    assert tx.events['Transfer'][0]['src'] == atoken
    assert tx.events['Transfer'][0]['wad'] == withdraw_amount

    # Check `AToken`
    assert atoken.balanceOf(depositor_a) == amount - withdraw_amount
    assert atoken.scaledBalanceOf(depositor_a) == amount - withdraw_amount
    assert atoken.totalSupply() == amount - withdraw_amount


# Test `withdraw()` with borrowings and collateral on but no borrowings
def test_withdraw_no_borrowings_and_collateral():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor_a = accounts[4]
    amount = 1
    amount_2 = 99_999_000_000
    weth.deposit({'from': depositor_a, 'value': amount + amount_2})
    weth.approve(lending_pool, amount + amount_2, {'from': depositor_a})

    # Turn on collateral and borrowing
    (ltv, threhold, bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # `deposit()`
    referral_code = 0
    lending_pool.deposit(weth, amount, depositor_a, referral_code, {'from': depositor_a})

    # Check `AToken`
    assert atoken.balanceOf(depositor_a) == amount
    assert atoken.scaledBalanceOf(depositor_a) == amount
    assert atoken.totalSupply() == amount

    # `withdraw()` all to self
    tx = lending_pool.withdraw(weth, amount, depositor_a, {'from': depositor_a})

    # Check logs `LendingPool`
    assert tx.events['Withdraw']['reserve'] == weth
    assert tx.events['Withdraw']['user'] == depositor_a
    assert tx.events['Withdraw']['to'] == depositor_a
    assert tx.events['Withdraw']['amount'] == amount
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == 0
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == 0
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY
    assert tx.events['ReserveUsedAsCollateralDisabled']['reserve'] == weth
    assert tx.events['ReserveUsedAsCollateralDisabled']['user'] == depositor_a

    # Check logs `AToken`
    assert tx.events['Burn']['from'] == depositor_a
    assert tx.events['Burn']['target'] == depositor_a
    assert tx.events['Burn']['value'] == amount
    assert tx.events['Burn']['index'] == RAY
    assert tx.events['Transfer'][1]['to'] == ZERO_ADDRESS
    assert tx.events['Transfer'][1]['value'] == amount
    assert tx.events['Transfer'][1]['from'] == depositor_a

    # Check logs `WETH`
    assert tx.events['Transfer'][0]['dst'] == depositor_a
    assert tx.events['Transfer'][0]['src'] == atoken
    assert tx.events['Transfer'][0]['wad'] == amount

    # Check `AToken` state
    assert atoken.balanceOf(depositor_a) == 0
    assert atoken.scaledBalanceOf(depositor_a) == 0
    assert atoken.totalSupply() == 0

    # Check `LendingPool` state
    (userConfig,) = lending_pool.getUserConfiguration(depositor_a)
    assert userConfig == 0 # Collateral for reserve index 0 disabled
    (total_collateral, total_debt, available_borrow, current_threshold, current_ltv, health_factor) = lending_pool.getUserAccountData(depositor_a)
    assert total_debt == 0
    assert current_ltv == 0
    assert total_collateral == 0
    assert available_borrow == 0
    assert health_factor == (1 << 256) - 1 # uint256(-1)

    # `deposit()` a second time
    lending_pool.deposit(weth, amount_2, depositor_a, referral_code, {'from': depositor_a})

    # `withdraw()` half balance
    tx = lending_pool.withdraw(weth, amount_2 // 2, depositor_a, {'from': depositor_a})

    # Check logs `LendingPool`
    assert tx.events['Withdraw']['reserve'] == weth
    assert tx.events['Withdraw']['user'] == depositor_a
    assert tx.events['Withdraw']['to'] == depositor_a
    assert tx.events['Withdraw']['amount'] == amount_2 // 2
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == 0
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == 0
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY
    assert not 'ReserveUsedAsCollateralDisabled' in tx.events

    # Check logs `AToken`
    assert tx.events['Burn']['from'] == depositor_a
    assert tx.events['Burn']['target'] == depositor_a
    assert tx.events['Burn']['value'] == amount_2 // 2
    assert tx.events['Burn']['index'] == RAY
    assert tx.events['Transfer'][1]['to'] == ZERO_ADDRESS
    assert tx.events['Transfer'][1]['value'] == amount_2 // 2
    assert tx.events['Transfer'][1]['from'] == depositor_a

    # Check logs `WETH`
    assert tx.events['Transfer'][0]['dst'] == depositor_a
    assert tx.events['Transfer'][0]['src'] == atoken
    assert tx.events['Transfer'][0]['wad'] == amount_2 // 2

    # Check `AToken`
    remaining_balance = amount_2 - amount_2 // 2
    assert atoken.balanceOf(depositor_a) == remaining_balance
    assert atoken.scaledBalanceOf(depositor_a) == remaining_balance
    assert atoken.totalSupply() == remaining_balance

    # Check `LendingPool` state
    (userConfig,) = lending_pool.getUserConfiguration(depositor_a)
    assert userConfig == 2**(0 * 2 + 1) # Collateral for reserve index 0
    (total_collateral, total_debt, available_borrow, current_threshold, current_ltv, health_factor) = lending_pool.getUserAccountData(depositor_a)
    assert total_debt == 0
    assert current_ltv == ltv
    assert total_collateral == remaining_balance
    assert available_borrow == remaining_balance * ltv // 10_000
    assert health_factor == (1 << 256) - 1 # uint256(-1)

    # `withdraw()` max(uint256), withdraws all user balance
    tx = lending_pool.withdraw(weth, (1 << 256) - 1, depositor_a, {'from': depositor_a})

    # Check logs `LendingPool`
    assert tx.events['Withdraw']['reserve'] == weth
    assert tx.events['Withdraw']['user'] == depositor_a
    assert tx.events['Withdraw']['to'] == depositor_a
    assert tx.events['Withdraw']['amount'] == remaining_balance
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == 0
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == 0
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY
    assert tx.events['ReserveUsedAsCollateralDisabled']['reserve'] == weth
    assert tx.events['ReserveUsedAsCollateralDisabled']['user'] == depositor_a

    # Check logs `AToken`
    assert tx.events['Burn']['from'] == depositor_a
    assert tx.events['Burn']['target'] == depositor_a
    assert tx.events['Burn']['value'] == remaining_balance
    assert tx.events['Burn']['index'] == RAY
    assert tx.events['Transfer'][1]['to'] == ZERO_ADDRESS
    assert tx.events['Transfer'][1]['value'] == remaining_balance
    assert tx.events['Transfer'][1]['from'] == depositor_a

    # Check logs `WETH`
    assert tx.events['Transfer'][0]['dst'] == depositor_a
    assert tx.events['Transfer'][0]['src'] == atoken
    assert tx.events['Transfer'][0]['wad'] == remaining_balance

    # Check AToken
    assert atoken.balanceOf(depositor_a) == 0
    assert atoken.scaledBalanceOf(depositor_a) == 0
    assert atoken.totalSupply() == 0

    # Check `LendingPool` state
    (userConfig,) = lending_pool.getUserConfiguration(depositor_a)
    assert userConfig == 0 # Collateral for reserve index 0 disabled
    (total_collateral, total_debt, available_borrow, current_threshold, current_ltv, health_factor) = lending_pool.getUserAccountData(depositor_a)
    assert total_debt == 0
    assert current_ltv == 0
    assert total_collateral == 0
    assert available_borrow == 0
    assert health_factor == (1 << 256) - 1 # uint256(-1)




# Test `withdraw()` with existing collateral and debt
def test_withdraw_with_debt():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, weth_depositor, deposit_amount, terc20_depositor,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, ltv, threshold, bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()` variable debt
    variable_borrow_amount = terc20_deposit_amount * price // WEI // 10 # 10% of collateral in ETH
    tx = lending_pool.borrow(
        terc20,
        variable_borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        terc20_depositor,
        {'from': terc20_depositor},
    )

    # `borrow()` stable debt
    web3.manager.request_blocking("evm_increaseTime", 4) # ensure some interest is accrued
    stable_borrow_amount = terc20_deposit_amount // 20 # 5% of total liquidity
    tx_b = lending_pool.borrow(
        terc20,
        stable_borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        weth_depositor,
        {'from': weth_depositor},
    )

    # Store previous state
    liquidity_index = tx_b.events['ReserveDataUpdated']['liquidityIndex']
    liquidity_rate = tx_b.events['ReserveDataUpdated']['liquidityRate']
    variable_borrow_index = tx_b.events['ReserveDataUpdated']['variableBorrowIndex']
    variable_rate = tx_b.events['ReserveDataUpdated']['variableBorrowRate']
    stable_rate = tx_b.events['ReserveDataUpdated']['stableBorrowRate']
    overall_stable_rate = tx_b.events['Mint']['avgStableRate']

    # `deposit()` more collateral
    web3.manager.request_blocking("evm_increaseTime", 4) # ensure some interest is accrued
    withdraw_amount = 9_000_000
    tx_c = lending_pool.withdraw(
        terc20,
        withdraw_amount,
        terc20_depositor,
        {'from': terc20_depositor},
    )

    ### Python Calculations
    time_diff = tx_c.timestamp - tx_b.timestamp
    prev_stable_rate = stable_rate # SRt-1
    prev_overall_stable_rate = overall_stable_rate # ^SRt-1
    prev_total_stable_debt_with_interest = ray_mul(stable_borrow_amount, calculate_compound_interest(prev_overall_stable_rate, time_diff))

    # `updateState()`
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt

    # `updateInterestRates()`
    total_stable_debt = prev_total_stable_debt_with_interest # SDt
    total_variable_debt = ray_mul(variable_borrow_amount, variable_borrow_index) # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = terc20_deposit_amount - stable_borrow_amount - variable_borrow_amount - withdraw_amount
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(terc20), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(prev_overall_stable_rate, prev_total_stable_debt_with_interest, 0, 0, False)
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` logs
    assert tx_c.events['ReserveDataUpdated']['reserve'] == terc20
    assert tx_c.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx_c.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx_c.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx_c.events['ReserveDataUpdated']['liquidityIndex'] == liquidity_index
    assert tx_c.events['ReserveDataUpdated']['variableBorrowIndex'] == variable_borrow_index
    assert tx_c.events['Withdraw']['reserve'] == terc20
    assert tx_c.events['Withdraw']['user'] == terc20_depositor
    assert tx_c.events['Withdraw']['to'] == terc20_depositor
    assert tx_c.events['Withdraw']['amount'] == withdraw_amount

    # Check `AToken` logs
    assert tx_c.events['Burn']['from'] == terc20_depositor
    assert tx_c.events['Burn']['target'] == terc20_depositor
    assert tx_c.events['Burn']['value'] == withdraw_amount
    assert tx_c.events['Burn']['index'] == liquidity_index
    assert tx_c.events['Transfer'][1]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][1]['value'] == withdraw_amount
    assert tx_c.events['Transfer'][1]['from'] == terc20_depositor

    # Check `WETH` logs
    assert tx_c.events['Transfer'][0]['to'] == terc20_depositor
    assert tx_c.events['Transfer'][0]['from'] == terc20_atoken
    assert tx_c.events['Transfer'][0]['value'] == withdraw_amount


###########
# borrow()
###########


# Test `borrow()` with a stable rate
# `depositor` deposits WETH
# `borrower` deposits tERC20 and borrows WETH
# `borrower_b` deposits tERC20 and borrows WETH
def test_stable_borrow():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    deposit_amount = 10_000_000_000_000_000_000
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositor})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Set market lending rate
    lending_rate_oracle.setMarketBorrowRate(weth, MARKET_BORROW_RATE)

    # `deposit()` weth
    lending_pool.deposit(weth, deposit_amount, depositor, 0, {'from': depositor})

    # Add additional reserve
    terc20 = accounts[0].deploy(
        MintableDelegationERC20,
        "Test ERC20",
        "tERC20",
        18,
    )

    # Initialise reserve tERC20
    (terc20_atoken, terc20_stable_debt, terc20_variable_debt) = setup_new_reserve(configurator, terc20, lending_pool, pool_admin)

    # Turn on collateral and borrowing
    (tecr20_ltv, tecr20_threshold, tecr20_bonus) = allow_reserve_collateral_and_borrowing(configurator, terc20, pool_admin)

    # Setup price for tERC20
    price = WEI // 10 # 1 tERC20 : 0.1 ETH
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    ### First Borrower ###

    # Create tERC20 tokens for `borrower` and deposit them into `LendingPool`
    borrower = accounts[5]
    terc20_deposit_amount = deposit_amount // 10
    terc20.mint(terc20_deposit_amount, {'from': borrower})
    terc20.approve(lending_pool, terc20_deposit_amount, {'from': borrower})
    lending_pool.deposit(terc20, terc20_deposit_amount, borrower, 0, {'from': borrower})

    # `borrow()`
    borrow_amount = terc20_deposit_amount // 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Calculate values
    prev_stable_rate = lending_rate_oracle.getMarketBorrowRate(weth) # SRt-1

    total_stable_debt = borrow_amount # SDt
    total_variable_debt = 0 # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(RAY, 0, prev_stable_rate, borrow_amount, True) # ^SRt
    overall_borrow_rate = ray_div(ray_mul(0, variable_rate) + ray_mul(borrow_amount, overall_stable_rate), 0 + borrow_amount) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` logs
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY
    assert tx.events['Borrow']['reserve'] == weth
    assert tx.events['Borrow']['user'] == borrower
    assert tx.events['Borrow']['onBehalfOf'] == borrower
    assert tx.events['Borrow']['amount'] == borrow_amount
    assert tx.events['Borrow']['borrowRateMode'] == INTEREST_RATE_MODE_STABLE
    assert tx.events['Borrow']['borrowRate'] == prev_stable_rate
    assert tx.events['Borrow']['referral'] == 0

    # Check `StableDebtToken` logs
    assert tx.events['Mint']['user'] == borrower
    assert tx.events['Mint']['onBehalfOf'] == borrower
    assert tx.events['Mint']['amount'] == borrow_amount
    assert tx.events['Mint']['currentBalance'] == 0
    assert tx.events['Mint']['balanceIncrease'] == 0
    assert tx.events['Mint']['newRate'] == prev_stable_rate
    assert tx.events['Mint']['avgStableRate'] == prev_stable_rate
    assert tx.events['Mint']['newTotalSupply'] == borrow_amount
    assert tx.events['Transfer'][0]['from'] == ZERO_ADDRESS
    assert tx.events['Transfer'][0]['to'] == borrower
    assert tx.events['Transfer'][0]['value'] == borrow_amount

    # Check `WETH` logs
    assert tx.events['Transfer'][1]['src'] == weth_atoken
    assert tx.events['Transfer'][1]['dst'] == borrower
    assert tx.events['Transfer'][1]['wad'] == borrow_amount

    # Check `StableDebtToken` state
    assert weth_stable_debt.balanceOf(borrower) == borrow_amount
    assert weth_stable_debt.getUserLastUpdated(borrower) == tx.timestamp
    assert weth_stable_debt.getTotalSupplyLastUpdated() == tx.timestamp
    assert weth_stable_debt.getUserStableRate(borrower) == prev_stable_rate
    assert weth_stable_debt.totalSupply() == borrow_amount
    assert weth_stable_debt.principalBalanceOf(borrower) == borrow_amount

    # Check `WETH` state
    assert weth.balanceOf(borrower) == borrow_amount

    # Check `LendingPool` state
    calculated_collateral = int(round(terc20_deposit_amount * (price / WEI), 0)) # Note: deposit made in tERC20
    # health = collateral `percentMul()` threshold `wadDiv()` borrowings
    calculated_health = calculated_collateral * tecr20_threshold * WAD // 10_000 // borrow_amount
    (collateral, debt, available_borrow, threshold, ltv, health) = lending_pool.getUserAccountData(borrower)
    assert collateral == calculated_collateral
    assert debt == borrow_amount
    assert threshold == tecr20_threshold
    assert ltv == tecr20_ltv
    assert health == calculated_health


    ### Second Borrower ###
    web3.manager.request_blocking("evm_increaseTime", 4) # ensure some interest is accrued

    # Create tERC20 tokens for `borrower_b` and deposit them into `LendingPool`
    borrower_b = accounts[6]
    terc20_deposit_amount_b = deposit_amount // 100
    terc20.mint(terc20_deposit_amount_b, {'from': borrower_b})
    terc20.approve(lending_pool, terc20_deposit_amount_b, {'from': borrower_b})
    lending_pool.deposit(terc20, terc20_deposit_amount_b, borrower_b, 0, {'from': borrower_b})

    # `borrow()`
    borrow_amount_b = terc20_deposit_amount_b // 100
    tx_b = lending_pool.borrow(
        weth,
        borrow_amount_b,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower_b,
        {'from': borrower_b},
    )

    ## Python Calculations ##

    time_diff = tx_b.timestamp - tx.timestamp
    prev_stable_rate = stable_rate # SRt-1
    prev_overall_stable_rate = overall_stable_rate # ^SRt-1
    prev_total_debt_with_interest = ray_mul(borrow_amount, calculate_compound_interest(prev_overall_stable_rate, time_diff))

    # `updateState()`
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), RAY) # LIt
    variable_borrow_index = RAY # VIt = 1 as variable debt == 0

    # `updateInterestRates()`
    total_stable_debt = prev_total_debt_with_interest + borrow_amount_b # SDt
    total_variable_debt = 0 # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity -= borrow_amount_b
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(prev_overall_stable_rate, prev_total_debt_with_interest, prev_stable_rate, borrow_amount_b, True)
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` logs
    assert tx_b.events['ReserveDataUpdated']['reserve'] == weth
    assert tx_b.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx_b.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx_b.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx_b.events['ReserveDataUpdated']['liquidityIndex'] == liquidity_index
    assert tx_b.events['ReserveDataUpdated']['variableBorrowIndex'] == variable_borrow_index
    assert tx_b.events['Borrow']['reserve'] == weth
    assert tx_b.events['Borrow']['user'] == borrower_b
    assert tx_b.events['Borrow']['onBehalfOf'] == borrower_b
    assert tx_b.events['Borrow']['amount'] == borrow_amount_b
    assert tx_b.events['Borrow']['borrowRateMode'] == INTEREST_RATE_MODE_STABLE
    assert tx_b.events['Borrow']['borrowRate'] == prev_stable_rate
    assert tx_b.events['Borrow']['referral'] == 0

    # Check `StableDebtToken` logs
    assert tx_b.events['Mint']['user'] == borrower_b
    assert tx_b.events['Mint']['onBehalfOf'] == borrower_b
    assert tx_b.events['Mint']['amount'] == borrow_amount_b
    assert tx_b.events['Mint']['currentBalance'] == 0
    assert tx_b.events['Mint']['balanceIncrease'] == 0
    assert tx_b.events['Mint']['newRate'] == prev_stable_rate
    assert tx_b.events['Mint']['avgStableRate'] == overall_stable_rate
    assert tx_b.events['Mint']['newTotalSupply'] == total_debt
    assert tx_b.events['Transfer'][0]['from'] == ZERO_ADDRESS
    assert tx_b.events['Transfer'][0]['to'] == borrower_b
    assert tx_b.events['Transfer'][0]['value'] == borrow_amount_b

    # Check `WETH` logs
    assert tx_b.events['Transfer'][1]['src'] == weth_atoken
    assert tx_b.events['Transfer'][1]['dst'] == borrower_b
    assert tx_b.events['Transfer'][1]['wad'] == borrow_amount_b

    # Check `StableDebtToken` state
    assert weth_stable_debt.balanceOf(borrower_b) == borrow_amount_b
    assert weth_stable_debt.balanceOf(borrower) == total_debt - borrow_amount_b # Note this only works because LRt-1 = ^SRt-1 during the borrow
    assert weth_stable_debt.getUserLastUpdated(borrower_b) == tx_b.timestamp
    assert weth_stable_debt.getTotalSupplyLastUpdated() == tx_b.timestamp
    assert weth_stable_debt.totalSupply() == total_debt
    assert weth_stable_debt.getAverageStableRate() == overall_stable_rate
    assert weth_stable_debt.getUserStableRate(borrower_b) == prev_stable_rate
    assert weth_stable_debt.principalBalanceOf(borrower_b) == borrow_amount_b
    assert weth_stable_debt.principalBalanceOf(borrower) == borrow_amount

    # Check `WETH` state
    assert weth.balanceOf(borrower_b) == borrow_amount_b

    # Check `LendingPool` state
    calculated_collateral = int(round(terc20_deposit_amount_b * (price / WEI), 0)) # Note: deposit made in tERC20
    # health = collateral `percentMul()` threshold `wadDiv()` borrowings
    calculated_health = calculated_collateral * tecr20_threshold * WAD // 10_000 // borrow_amount_b
    (collateral, debt, available_borrow, threshold, ltv, health) = lending_pool.getUserAccountData(borrower_b)
    assert collateral == calculated_collateral
    assert debt == borrow_amount_b
    assert threshold == tecr20_threshold
    assert ltv == tecr20_ltv
    assert health == calculated_health

# Test `borrow()` on behalf of another user
# `depositor` deposits WETH
# `borrower` deposits tERC20 and borrows WETH
# `borrower_b` deposits tERC20 and borrows WETH
def test_borrow_on_behalf():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    deposit_amount = 10_000_000_000_000_000_000
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositor})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Set market lending rate
    lending_rate_oracle.setMarketBorrowRate(weth, MARKET_BORROW_RATE)

    # `deposit()` weth
    lending_pool.deposit(weth, deposit_amount, depositor, 0, {'from': depositor})

    # Add additional reserve
    terc20 = accounts[0].deploy(
        MintableDelegationERC20,
        "Test ERC20",
        "tERC20",
        18,
    )

    # Initialise reserve tERC20
    (terc20_atoken, terc20_stable_debt, terc20_variable_debt) = setup_new_reserve(configurator, terc20, lending_pool, pool_admin)

    # Turn on collateral and borrowing
    (tecr20_ltv, tecr20_threshold, tecr20_bonus) = allow_reserve_collateral_and_borrowing(configurator, terc20, pool_admin)

    # Setup price for tERC20
    price = WEI // 10 # 1 tERC20 : 0.1 ETH
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    ### Second depositor ###

    # Create tERC20 tokens for `second_depositor` and deposit them into `LendingPool`
    second_depositor = accounts[5]

    terc20_deposit_amount = deposit_amount // 10
    terc20.mint(terc20_deposit_amount, {'from': second_depositor})
    terc20.approve(lending_pool, terc20_deposit_amount, {'from': second_depositor})
    ## Deposit from another account on behalf of second_depositor
    tx = lending_pool.deposit(terc20, terc20_deposit_amount, second_depositor, 0, {'from': second_depositor})

    ### Borrower ####

    # Should not be able to borrow on behalf of someone else without approval.
    # `borrow()`
    borrower = accounts[7]
    borrow_amount = terc20_deposit_amount // 1000
    with reverts("59"):
        # Borrower tries to borrow on behalf of receiver
        lending_pool.borrow(
            weth,
            borrow_amount,
            INTEREST_RATE_MODE_STABLE,
            0,
            second_depositor,
            {'from': borrower},
        )

    # Approve to allow a user to borrow
    allowance_amount = borrow_amount + 123
    tx_b = weth_variable_debt.approveDelegation(borrower, allowance_amount, {'from': second_depositor})

    # Check logs and state of `approveDelegation()`
    assert tx_b.events['BorrowAllowanceDelegated']['fromUser'] == second_depositor
    assert tx_b.events['BorrowAllowanceDelegated']['toUser'] == borrower
    assert tx_b.events['BorrowAllowanceDelegated']['asset'] == weth
    assert tx_b.events['BorrowAllowanceDelegated']['amount'] == allowance_amount
    assert weth_variable_debt.borrowAllowance(second_depositor, borrower)  == allowance_amount

    # `borrow()` on behalf of
    tx_c = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        second_depositor,
        {'from': borrower},
    )

    # WETH `updateState()`
    liquidity_index = RAY # LIt
    variable_borrow_index = RAY # VIt

    # WETH `updateInterestRates()`
    total_stable_debt = 0 # SDt
    total_variable_debt = ray_mul(borrow_amount, variable_borrow_index) # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = 0 # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `WETH` logs
    assert tx_c.events['Transfer'][1]['src'] == weth_atoken
    assert tx_c.events['Transfer'][1]['dst'] == borrower
    assert tx_c.events['Transfer'][1]['wad'] == borrow_amount

    # Check `LendingPool` logs
    assert tx_c.events['ReserveDataUpdated'][0]['reserve'] == weth
    assert tx_c.events['ReserveDataUpdated'][0]['variableBorrowRate'] == variable_rate
    assert tx_c.events['ReserveDataUpdated'][0]['stableBorrowRate'] == stable_rate
    assert tx_c.events['ReserveDataUpdated'][0]['liquidityRate'] == liquidity_rate
    assert tx_c.events['ReserveDataUpdated'][0]['variableBorrowIndex'] == variable_borrow_index
    assert tx_c.events['ReserveDataUpdated'][0]['liquidityIndex'] == liquidity_index
    assert tx_c.events['Borrow']['reserve'] == weth
    assert tx_c.events['Borrow']['user'] == borrower
    assert tx_c.events['Borrow']['onBehalfOf'] == second_depositor
    assert tx_c.events['Borrow']['amount'] == borrow_amount
    assert tx_c.events['Borrow']['borrowRateMode'] == INTEREST_RATE_MODE_VARIABLE
    assert tx_c.events['Borrow']['borrowRate'] == variable_rate
    assert tx_c.events['Borrow']['referral'] == 0

    # Check `VariableDebtToken` logs
    assert tx_c.events['Mint']['from'] == borrower
    assert tx_c.events['Mint']['onBehalfOf'] == second_depositor
    assert tx_c.events['Mint']['value'] == borrow_amount
    assert tx_c.events['Mint']['index'] == variable_borrow_index
    assert tx_c.events['Transfer'][0]['to'] == second_depositor
    assert tx_c.events['Transfer'][0]['from'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][0]['value'] == borrow_amount
    assert tx_c.events['BorrowAllowanceDelegated']['fromUser'] == second_depositor
    assert tx_c.events['BorrowAllowanceDelegated']['toUser'] == borrower
    assert tx_c.events['BorrowAllowanceDelegated']['asset'] == weth
    assert tx_c.events['BorrowAllowanceDelegated']['amount'] == allowance_amount - borrow_amount

    # Check `VariableDebtToken` state
    assert weth_variable_debt.borrowAllowance(second_depositor, borrower) == allowance_amount - borrow_amount
    assert weth_variable_debt.balanceOf(second_depositor) == borrow_amount
    assert weth_variable_debt.balanceOf(borrower) == 0

    ### StableDebtToken `borrow()` on behalf of

    # Approve to allow a user to borrow
    allowance_amount = borrow_amount
    tx_d = weth_stable_debt.approveDelegation(borrower, allowance_amount, {'from': second_depositor})

    # `borrow()` on behalf of
    web3.manager.request_blocking("evm_increaseTime", 4) # Ensure time increases
    tx_e = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        second_depositor,
        {'from': borrower},
    )

    # WETH `updateState()`
    time_diff = tx_e.timestamp - tx_c.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt

    # WETH `updateInterestRates()`
    prev_stable_rate = stable_rate
    total_stable_debt = borrow_amount # SDt
    total_variable_debt = ray_mul(borrow_amount, variable_borrow_index) # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount - borrow_amount
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = prev_stable_rate # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `WETH` logs
    assert tx_e.events['Transfer'][1]['src'] == weth_atoken
    assert tx_e.events['Transfer'][1]['dst'] == borrower
    assert tx_e.events['Transfer'][1]['wad'] == borrow_amount

    # Check `LendingPool` logs
    assert tx_e.events['ReserveDataUpdated'][0]['reserve'] == weth
    assert tx_e.events['ReserveDataUpdated'][0]['variableBorrowRate'] == variable_rate
    assert tx_e.events['ReserveDataUpdated'][0]['stableBorrowRate'] == stable_rate
    assert tx_e.events['ReserveDataUpdated'][0]['liquidityRate'] == liquidity_rate
    assert tx_e.events['ReserveDataUpdated'][0]['variableBorrowIndex'] == variable_borrow_index
    assert tx_e.events['ReserveDataUpdated'][0]['liquidityIndex'] == liquidity_index
    assert tx_e.events['Borrow']['reserve'] == weth
    assert tx_e.events['Borrow']['user'] == borrower
    assert tx_e.events['Borrow']['onBehalfOf'] == second_depositor
    assert tx_e.events['Borrow']['amount'] == borrow_amount
    assert tx_e.events['Borrow']['borrowRateMode'] == INTEREST_RATE_MODE_STABLE
    assert tx_e.events['Borrow']['borrowRate'] == prev_stable_rate
    assert tx_e.events['Borrow']['referral'] == 0

    # Check `VariableDebtToken` logs
    assert tx_e.events['Mint']['user'] == borrower
    assert tx_e.events['Mint']['onBehalfOf'] == second_depositor
    assert tx_e.events['Mint']['amount'] == borrow_amount
    assert tx_e.events['Mint']['currentBalance'] == 0
    assert tx_e.events['Mint']['balanceIncrease'] == 0
    assert tx_e.events['Mint']['avgStableRate'] == prev_stable_rate
    assert tx_e.events['Mint']['newTotalSupply'] == borrow_amount
    assert tx_e.events['Transfer'][0]['to'] == second_depositor
    assert tx_e.events['Transfer'][0]['from'] == ZERO_ADDRESS
    assert tx_e.events['Transfer'][0]['value'] == borrow_amount
    assert tx_e.events['BorrowAllowanceDelegated']['fromUser'] == second_depositor
    assert tx_e.events['BorrowAllowanceDelegated']['toUser'] == borrower
    assert tx_e.events['BorrowAllowanceDelegated']['asset'] == weth
    assert tx_e.events['BorrowAllowanceDelegated']['amount'] == allowance_amount - borrow_amount

    # Check `VariableDebtToken` state
    assert weth_stable_debt.borrowAllowance(second_depositor, borrower) == allowance_amount - borrow_amount
    assert weth_stable_debt.balanceOf(second_depositor) == borrow_amount
    assert weth_stable_debt.balanceOf(borrower) == 0


# Test `borrow()` when the stable base rate is zero (i.e. `LendingOracle.getMarketBorrowRate() == 0`)
# `depositor` deposits WETH
# `borrower` deposits tERC20 and borrows WETH
def test_stable_borrow_base_rate_zero():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    deposit_amount = 10_000_000_000_000_000_000
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositor})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # `deposit()` weth
    lending_pool.deposit(weth, deposit_amount, depositor, 0, {'from': depositor})

    # Add additional reserve
    terc20 = accounts[0].deploy(
        MintableDelegationERC20,
        "Test ERC20",
        "tERC20",
        18,
    )

    # Initialise reserve tERC20
    (terc20_atoken, terc20_stable_debt, terc20_variable_debt) = setup_new_reserve(configurator, terc20, lending_pool, pool_admin)

    # Turn on collateral and borrowing
    (tecr20_ltv, tecr20_threshold, tecr20_bonus) = allow_reserve_collateral_and_borrowing(configurator, terc20, pool_admin)

    # Setup price for tERC20
    price = WEI // 10 # 1 tERC20 : 0.1 ETH
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    ### Borrowing ###

    # Create tERC20 tokens for `borrower` and deposit them into `LendingPool`
    borrower = accounts[5]
    terc20_deposit_amount = deposit_amount // 10
    terc20.mint(terc20_deposit_amount, {'from': borrower})
    terc20.approve(lending_pool, terc20_deposit_amount, {'from': borrower})
    lending_pool.deposit(terc20, terc20_deposit_amount, borrower, 0, {'from': borrower})

    # `borrow()`
    borrow_amount = terc20_deposit_amount // 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Calculate values
    utilization_rate = ray_div(borrow_amount, deposit_amount) # Ut
    stable_rate = calculate_stable_borrow_rate(0, strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = weth_stable_debt.getAverageStableRate() # ^SRt
    overall_borrow_rate = ray_div(ray_mul(0, variable_rate) + ray_mul(borrow_amount, overall_stable_rate), 0 + borrow_amount) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Note: we probably don't want these to be zero, else the interest paid on the loan is zero
    assert overall_borrow_rate == 0
    assert liquidity_rate == 0

    # Check `LendingPool` logs
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY
    assert tx.events['Borrow']['reserve'] == weth
    assert tx.events['Borrow']['user'] == borrower
    assert tx.events['Borrow']['onBehalfOf'] == borrower
    assert tx.events['Borrow']['amount'] == borrow_amount
    assert tx.events['Borrow']['borrowRateMode'] == INTEREST_RATE_MODE_STABLE
    assert tx.events['Borrow']['borrowRate'] == 0
    assert tx.events['Borrow']['referral'] == 0

    # Check `StableDebtToken` logs
    assert tx.events['Mint']['user'] == borrower
    assert tx.events['Mint']['onBehalfOf'] == borrower
    assert tx.events['Mint']['amount'] == borrow_amount
    assert tx.events['Mint']['currentBalance'] == 0
    assert tx.events['Mint']['balanceIncrease'] == 0
    assert tx.events['Mint']['newRate'] == 0
    assert tx.events['Mint']['avgStableRate'] == 0
    assert tx.events['Mint']['newTotalSupply'] == borrow_amount
    assert tx.events['Transfer'][0]['from'] == ZERO_ADDRESS
    assert tx.events['Transfer'][0]['to'] == borrower
    assert tx.events['Transfer'][0]['value'] == borrow_amount

    # Check `WETH` logs
    assert tx.events['Transfer'][1]['src'] == weth_atoken
    assert tx.events['Transfer'][1]['dst'] == borrower
    assert tx.events['Transfer'][1]['wad'] == borrow_amount

    # Check `StableDebtToken` state
    assert weth_stable_debt.balanceOf(borrower) == borrow_amount
    assert weth_stable_debt.getUserLastUpdated(borrower) == tx.timestamp
    assert weth_stable_debt.getTotalSupplyLastUpdated() == tx.timestamp
    assert weth_stable_debt.getAverageStableRate() == 0
    assert weth_stable_debt.getUserStableRate(borrower) == 0
    assert weth_stable_debt.getTotalSupplyAndAvgRate() == (borrow_amount, 0)
    assert weth_stable_debt.principalBalanceOf(borrower) == borrow_amount

    # Check `WETH` state
    assert weth.balanceOf(borrower) == borrow_amount

    # Check `LendingPool` state
    calculated_collateral = int(round(terc20_deposit_amount * (price / WEI), 0)) # Note: deposit made in tERC20
    # health = collateral `percentMul()` threshold `wadDiv()` borrowings
    calculated_health = calculated_collateral * tecr20_threshold * WAD // 10_000 // borrow_amount
    (collateral, debt, available_borrow, threshold, ltv, health) = lending_pool.getUserAccountData(borrower)
    assert collateral == calculated_collateral
    assert debt == borrow_amount
    assert threshold == tecr20_threshold
    assert ltv == tecr20_ltv
    assert health == calculated_health

    ### Borrow a second time ###
    web3.manager.request_blocking("evm_increaseTime", 4)

    # `borrow()`
    borrow_amount = terc20_deposit_amount // 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Calculate values
    prev_stable_rate = stable_rate # SRt-1
    total_stable_debt = borrow_amount * 2 # SDt
    total_variable_debt = 0 # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount * 2
    utilization_rate = ray_div(total_debt, total_debt + available_liquidity) # Ut
    stable_rate = calculate_stable_borrow_rate(0, strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = weth_stable_debt.getAverageStableRate() # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Second loan should be greater than 0
    assert overall_borrow_rate > 0
    assert liquidity_rate > 0

    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY
    assert tx.events['Borrow']['reserve'] == weth
    assert tx.events['Borrow']['user'] == borrower
    assert tx.events['Borrow']['onBehalfOf'] == borrower
    assert tx.events['Borrow']['amount'] == borrow_amount
    assert tx.events['Borrow']['borrowRateMode'] == INTEREST_RATE_MODE_STABLE
    assert tx.events['Borrow']['borrowRate'] == prev_stable_rate
    assert tx.events['Borrow']['referral'] == 0

    # Check `StableDebtToken` logs
    assert tx.events['Mint']['user'] == borrower
    assert tx.events['Mint']['onBehalfOf'] == borrower
    assert tx.events['Mint']['amount'] == borrow_amount
    assert tx.events['Mint']['currentBalance'] == borrow_amount
    assert tx.events['Mint']['balanceIncrease'] == 0
    assert tx.events['Mint']['newRate'] == overall_stable_rate
    assert tx.events['Mint']['avgStableRate'] == overall_stable_rate
    assert tx.events['Mint']['newTotalSupply'] == borrow_amount * 2
    assert tx.events['Transfer'][0]['from'] == ZERO_ADDRESS
    assert tx.events['Transfer'][0]['to'] == borrower
    assert tx.events['Transfer'][0]['value'] == borrow_amount


# Test `borrow()` with a variable rate
# `depositor` deposits WETH
# `borrower` deposits tERC20 and borrows WETH
# `borrower_b` deposits tERC20 and borrows WETH
def test_variable_borrow():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    deposit_amount = 10_000_000_000_000_000_000
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositor})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Set market lending rate
    lending_rate_oracle.setMarketBorrowRate(weth, MARKET_BORROW_RATE)

    # `deposit()` weth
    lending_pool.deposit(weth, deposit_amount, depositor, 0, {'from': depositor})

    # Add additional reserve
    terc20 = accounts[0].deploy(
        MintableDelegationERC20,
        "Test ERC20",
        "tERC20",
        18,
    )

    # Initialise reserve tERC20
    (terc20_atoken, terc20_stable_debt, terc20_variable_debt) = setup_new_reserve(configurator, terc20, lending_pool, pool_admin)

    # Turn on collateral and borrowing
    (tecr20_ltv, tecr20_threshold, tecr20_bonus) = allow_reserve_collateral_and_borrowing(configurator, terc20, pool_admin)

    # Setup price for tERC20
    price = WEI // 10 # 1 tERC20 : 0.1 ETH
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    ### First Borrower ###

    # Create tERC20 tokens for `borrower` and deposit them into `LendingPool`
    borrower = accounts[5]
    terc20_deposit_amount = deposit_amount // 10
    terc20.mint(terc20_deposit_amount, {'from': borrower})
    terc20.approve(lending_pool, terc20_deposit_amount, {'from': borrower})
    lending_pool.deposit(terc20, terc20_deposit_amount, borrower, 0, {'from': borrower})

    # `borrow()`
    borrow_amount = terc20_deposit_amount // 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Calculate values

    # `updateState()` occurs before borrow
    liquidity_index = RAY # LIt
    variable_borrow_index = RAY # VIt

    # VariableDebtToken.mint() updates
    scaled_total_supply = 0 + ray_div(borrow_amount, variable_borrow_index) # 0 is previous scaled total supply

    # `updateInterestRates()`
    total_stable_debt = 0 # SDt
    total_variable_debt = borrow_amount # VDt
    total_debt = total_variable_debt + total_stable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = weth_stable_debt.getAverageStableRate() # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` logs
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY
    assert tx.events['Borrow']['reserve'] == weth
    assert tx.events['Borrow']['user'] == borrower
    assert tx.events['Borrow']['onBehalfOf'] == borrower
    assert tx.events['Borrow']['amount'] == borrow_amount
    assert tx.events['Borrow']['borrowRateMode'] == INTEREST_RATE_MODE_VARIABLE
    assert tx.events['Borrow']['borrowRate'] == variable_rate
    assert tx.events['Borrow']['referral'] == 0

    # Check `VariableDebtToken` logs
    assert tx.events['Mint']['from'] == borrower
    assert tx.events['Mint']['onBehalfOf'] == borrower
    assert tx.events['Mint']['value'] == borrow_amount
    assert tx.events['Mint']['index'] == variable_borrow_index
    assert tx.events['Transfer'][0]['from'] == ZERO_ADDRESS
    assert tx.events['Transfer'][0]['to'] == borrower
    assert tx.events['Transfer'][0]['value'] == borrow_amount

    # Check `WETH` logs
    assert tx.events['Transfer'][1]['src'] == weth_atoken
    assert tx.events['Transfer'][1]['dst'] == borrower
    assert tx.events['Transfer'][1]['wad'] == borrow_amount

    # Check `VariableDebtToken` state
    assert weth_variable_debt.balanceOf(borrower) == borrow_amount
    assert weth_variable_debt.scaledBalanceOf(borrower) == borrow_amount
    assert weth_variable_debt.totalSupply() == total_variable_debt
    assert weth_variable_debt.scaledTotalSupply() == scaled_total_supply

    # Check `WETH` state
    assert weth.balanceOf(borrower) == borrow_amount

    # Check `LendingPool` state
    calculated_collateral = int(round(terc20_deposit_amount * (price / WEI), 0)) # Note: deposit made in tERC20
    # health = collateral `percentMul()` threshold `wadDiv()` borrowings
    calculated_health = calculated_collateral * tecr20_threshold * WAD // 10_000 // borrow_amount
    (collateral, debt, available_borrow, threshold, ltv, health) = lending_pool.getUserAccountData(borrower)
    assert collateral == calculated_collateral
    assert debt == borrow_amount
    assert threshold == tecr20_threshold
    assert ltv == tecr20_ltv
    assert health == calculated_health


    ### Second Borrower ###
    web3.manager.request_blocking("evm_increaseTime", 4) # ensure some interest is accrued

    # Create tERC20 tokens for `borrower_b` and deposit them into `LendingPool`
    borrower_b = accounts[6]
    terc20_deposit_amount_b = deposit_amount // 100
    terc20.mint(terc20_deposit_amount_b, {'from': borrower_b})
    terc20.approve(lending_pool, terc20_deposit_amount_b, {'from': borrower_b})
    lending_pool.deposit(terc20, terc20_deposit_amount_b, borrower_b, 0, {'from': borrower_b})

    # `borrow()`
    borrow_amount_b = terc20_deposit_amount_b // 100
    tx_b = lending_pool.borrow(
        weth,
        borrow_amount_b,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower_b,
        {'from': borrower_b},
    )

    ## Python Calculations ##

    # `updateState()`
    time_diff = tx_b.timestamp - tx.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt

    # VariableDebtToken.mint() updates
    scaled_total_supply = scaled_total_supply + ray_div(borrow_amount_b, variable_borrow_index)

    # `updateInterestRates()`
    total_stable_debt = 0 # SDt
    total_variable_debt = ray_mul(scaled_total_supply, variable_borrow_index) # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity -= borrow_amount_b
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = 0 # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` logs
    assert tx_b.events['ReserveDataUpdated']['reserve'] == weth
    assert tx_b.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx_b.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx_b.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx_b.events['ReserveDataUpdated']['liquidityIndex'] == liquidity_index
    assert tx_b.events['ReserveDataUpdated']['variableBorrowIndex'] == variable_borrow_index
    assert tx_b.events['Borrow']['reserve'] == weth
    assert tx_b.events['Borrow']['user'] == borrower_b
    assert tx_b.events['Borrow']['onBehalfOf'] == borrower_b
    assert tx_b.events['Borrow']['amount'] == borrow_amount_b
    assert tx_b.events['Borrow']['borrowRateMode'] == INTEREST_RATE_MODE_VARIABLE
    assert tx_b.events['Borrow']['borrowRate'] == variable_rate
    assert tx_b.events['Borrow']['referral'] == 0

    # Check `VariableDebtToken` logs
    assert tx_b.events['Mint']['from'] == borrower_b
    assert tx_b.events['Mint']['onBehalfOf'] == borrower_b
    assert tx_b.events['Mint']['value'] == borrow_amount_b
    assert tx_b.events['Mint']['index'] == variable_borrow_index
    assert tx_b.events['Transfer'][0]['from'] == ZERO_ADDRESS
    assert tx_b.events['Transfer'][0]['to'] == borrower_b
    assert tx_b.events['Transfer'][0]['value'] == borrow_amount_b

    # Check `WETH` logs
    assert tx_b.events['Transfer'][1]['src'] == weth_atoken
    assert tx_b.events['Transfer'][1]['dst'] == borrower_b
    assert tx_b.events['Transfer'][1]['wad'] == borrow_amount_b

    # Check `VariableDebtToken` state
    assert weth_variable_debt.balanceOf(borrower_b) == borrow_amount_b
    assert weth_variable_debt.scaledBalanceOf(borrower_b) == ray_div(borrow_amount_b, variable_borrow_index)
    assert weth_variable_debt.totalSupply() == total_variable_debt
    assert weth_variable_debt.scaledTotalSupply() == scaled_total_supply

    # Check `WETH` state
    assert weth.balanceOf(borrower_b) == borrow_amount_b

    # Check `LendingPool` state
    calculated_collateral = int(round(terc20_deposit_amount_b * (price / WEI), 0)) # Note: deposit made in tERC20
    # health = collateral `percentMul()` threshold `wadDiv()` borrowings
    calculated_health = calculated_collateral * tecr20_threshold * WAD // 10_000 // borrow_amount_b
    (collateral, debt, available_borrow, threshold, ltv, health) = lending_pool.getUserAccountData(borrower_b)
    assert collateral == calculated_collateral
    assert debt == borrow_amount_b
    assert threshold == tecr20_threshold
    assert ltv == tecr20_ltv
    assert health == calculated_health


##########
# repay()
##########

# Test `repay()` when the stable base rate is zero (i.e. `LendingOracle.getMarketBorrowRate() == 0`)
# `depositor` deposits WETH
# `borrower` deposits tERC20 and borrows WETH then repays WETH
@pytest.mark.xfail(reason='Total Supply incorrectly set to zero when there is supply')
def test_repay_stable_base_rate_zero():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    deposit_amount = 10_000_000_000_000_000_000
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositor})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # `deposit()` weth
    lending_pool.deposit(weth, deposit_amount, depositor, 0, {'from': depositor})

    # Add additional reserve
    terc20 = accounts[0].deploy(
        MintableDelegationERC20,
        "Test ERC20",
        "tERC20",
        18,
    )

    # Initialise reserve tERC20
    (terc20_atoken, terc20_stable_debt, terc20_variable_debt) = setup_new_reserve(configurator, terc20, lending_pool, pool_admin)

    # Turn on collateral and borrowing
    (tecr20_ltv, tecr20_threshold, tecr20_bonus) = allow_reserve_collateral_and_borrowing(configurator, terc20, pool_admin)

    # Setup price for tERC20
    price = WEI // 10 # 1 tERC20 : 0.1 ETH
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    ### Borrowing ###

    # Create tERC20 tokens for `borrower` and deposit them into `LendingPool`
    borrower = accounts[5]
    terc20_deposit_amount = deposit_amount // 10
    terc20.mint(terc20_deposit_amount, {'from': borrower})
    terc20.approve(lending_pool, terc20_deposit_amount, {'from': borrower})
    lending_pool.deposit(terc20, terc20_deposit_amount, borrower, 0, {'from': borrower})

    # `borrow()`
    borrow_amount = terc20_deposit_amount // 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Calculate values
    utilization_rate = ray_div(borrow_amount, deposit_amount) # Ut
    stable_rate = calculate_stable_borrow_rate(0, strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = weth_stable_debt.getAverageStableRate() # ^SRt
    overall_borrow_rate = ray_div(ray_mul(0, variable_rate) + ray_mul(borrow_amount, overall_stable_rate), 0 + borrow_amount) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    ### Repayment ###

    # Ensure interest would accrue if rate was greater than 0
    web3.manager.request_blocking("evm_increaseTime", 1)

    # Give allowance for `LendingPool` to do the repayment
    weth.approve(lending_pool, borrow_amount, {'from': borrower})

    # `repay()`
    repay_amount = 1
    tx = lending_pool.repay(
        weth,
        repay_amount,
        INTEREST_RATE_MODE_STABLE,
        borrower,
        {'from': borrower},
    )

    # Check `StableDebtToken` state
    assert weth_stable_debt.balanceOf(borrower) == borrow_amount - repay_amount
    assert weth_stable_debt.totalSupply() == borrow_amount - repay_amount
    assert weth_stable_debt.getUserLastUpdated(borrower) == tx.timestamp
    assert weth_stable_debt.getTotalSupplyLastUpdated() == tx.timestamp
    assert weth_stable_debt.getUserStableRate(borrower) == 0
    assert weth_stable_debt.principalBalanceOf(borrower) == borrow_amount - repay_amount

    # Check `LendingPool` logs
    assert tx.events['Repay']['reserve'] == weth
    assert tx.events['Repay']['user'] == borrower
    assert tx.events['Repay']['repayer'] == borrower
    assert tx.events['Repay']['amount'] == repay_amount
    assert tx.events['ReserveDataUpdated']['reserve'] == weth
    assert tx.events['ReserveDataUpdated']['liquidityRate'] == 0
    assert tx.events['ReserveDataUpdated']['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx.events['ReserveDataUpdated']['stableBorrowRate'] == 0
    assert tx.events['ReserveDataUpdated']['liquidityIndex'] == RAY
    assert tx.events['ReserveDataUpdated']['variableBorrowIndex'] == RAY

    # Check `StableDebtToken` logs
    assert tx.events['Burn']['user'] == borrower
    assert tx.events['Burn']['amount'] == repay_amount
    assert tx.events['Burn']['currentBalance'] == borrow_amount
    assert tx.events['Burn']['balanceIncrease'] == 0
    assert tx.events['Burn']['avgStableRate'] == 0
    assert tx.events['Burn']['newTotalSupply'] == borrow_amount - repay_amount
    assert tx.events['Transfer'][0]['from'] == borrower
    assert tx.events['Transfer'][0]['to'] == ZERO_ADDRESS
    assert tx.events['Transfer'][0]['value'] == repay_amount

    # Check `WETH` logs
    assert tx.events['Transfer'][1]['src'] == borrower
    assert tx.events['Transfer'][1]['dst'] == weth_atoken
    assert tx.events['Transfer'][1]['wad'] == repay_amount

    # Check `WETH` state
    assert weth.balanceOf(borrower) == borrow_amount - repay_amount


# Test `repay()` with a stable rate
# `depositor` deposits WETH
# `borrower` deposits tERC20 and borrows WETH
# `borrower_b` deposits tERC20 and borrows WETH
# `borrower` partially repays WETH
# `borrower_b` fully repays WETH
def test_repay_stable():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    deposit_amount = 10_000_000_000_000_000_000
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositor})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Set market lending rate
    lending_rate_oracle.setMarketBorrowRate(weth, MARKET_BORROW_RATE)

    # `deposit()` weth
    lending_pool.deposit(weth, deposit_amount, depositor, 0, {'from': depositor})

    # Add additional reserve
    terc20 = accounts[0].deploy(
        MintableDelegationERC20,
        "Test ERC20",
        "tERC20",
        18,
    )

    # Initialise reserve tERC20
    (terc20_atoken, terc20_stable_debt, terc20_variable_debt) = setup_new_reserve(configurator, terc20, lending_pool, pool_admin)

    # Turn on collateral and borrowing
    (tecr20_ltv, tecr20_threshold, tecr20_bonus) = allow_reserve_collateral_and_borrowing(configurator, terc20, pool_admin)

    # Setup price for tERC20
    price = WEI // 10 # 1 tERC20 : 0.1 ETH
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    ### First Borrower ###

    # Create tERC20 tokens for `borrower` and deposit them into `LendingPool`
    borrower = accounts[5]
    terc20_deposit_amount = deposit_amount // 10
    terc20.mint(terc20_deposit_amount, {'from': borrower})
    terc20.approve(lending_pool, terc20_deposit_amount, {'from': borrower})
    lending_pool.deposit(terc20, terc20_deposit_amount, borrower, 0, {'from': borrower})

    # `borrow()`
    borrow_amount = terc20_deposit_amount // 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Calculate values
    prev_stable_rate = lending_rate_oracle.getMarketBorrowRate(weth) # SRt-1

    total_stable_debt = borrow_amount # SDt
    total_variable_debt = 0 # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(RAY, 0, prev_stable_rate, borrow_amount, True) # ^SRt
    overall_borrow_rate = ray_div(ray_mul(0, variable_rate) + ray_mul(borrow_amount, overall_stable_rate), 0 + borrow_amount) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    ### Second Borrower ###
    web3.manager.request_blocking("evm_increaseTime", 4) # ensure some interest is accrued

    # Create tERC20 tokens for `borrower_b` and deposit them into `LendingPool`
    borrower_b = accounts[6]
    terc20_deposit_amount_b = deposit_amount // 100
    terc20.mint(terc20_deposit_amount_b, {'from': borrower_b})
    terc20.approve(lending_pool, terc20_deposit_amount_b, {'from': borrower_b})
    lending_pool.deposit(terc20, terc20_deposit_amount_b, borrower_b, 0, {'from': borrower_b})

    # `borrow()`
    borrow_amount_b = terc20_deposit_amount_b // 100
    tx_b = lending_pool.borrow(
        weth,
        borrow_amount_b,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower_b,
        {'from': borrower_b},
    )

    ## Python Calculations ##

    time_diff = tx_b.timestamp - tx.timestamp
    prev_stable_rate = stable_rate # SRt-1
    prev_overall_stable_rate = overall_stable_rate # ^SRt-1
    prev_total_debt_with_interest = ray_mul(borrow_amount, calculate_compound_interest(prev_overall_stable_rate, time_diff))

    # `updateState()`
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), RAY) # LIt
    variable_borrow_index = RAY # VIt = 1 as variable debt == 0

    # `updateInterestRates()`
    total_stable_debt = prev_total_debt_with_interest + borrow_amount_b # SDt
    total_variable_debt = 0 # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity -= borrow_amount_b
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(prev_overall_stable_rate, prev_total_debt_with_interest, prev_stable_rate, borrow_amount_b, True)
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    ### Partial Repay First Borrower ###

    web3.manager.request_blocking("evm_increaseTime", 4) # ensure some interest is accrued
    prev_user_stable_rate = weth_stable_debt.getUserStableRate(borrower) # Store previous user overall stable rate

    # `repay()`
    repay_amount = borrow_amount # Note interest will be accrued so SDt(x) > borrow_amount
    weth.approve(lending_pool, repay_amount, {'from': borrower})
    tx_c = lending_pool.repay(
        weth,
        repay_amount,
        INTEREST_RATE_MODE_STABLE,
        borrower,
        {'from': borrower}
    )

    ## Python Calculations ##

    time_diff = tx_c.timestamp - tx_b.timestamp
    prev_stable_rate = stable_rate # SRt-1
    prev_overall_stable_rate = overall_stable_rate # ^SRt-1
    prev_total_debt_with_interest = ray_mul(total_debt, calculate_compound_interest(prev_overall_stable_rate, time_diff))

    # `updateState()`
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = RAY # VIt = 1 as variable debt == 0

    # `updateInterestRates()`
    total_stable_debt = prev_total_debt_with_interest - repay_amount # SDt
    total_variable_debt = 0 # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity += repay_amount
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(prev_overall_stable_rate, prev_total_debt_with_interest, prev_user_stable_rate, repay_amount, False)
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # `StableDebt` user balances, `borrower` last update is `tx` and the principal balance is `borrow_amount`
    prev_user_balance = borrow_amount
    curr_user_balance = ray_mul(prev_user_balance, calculate_compound_interest(prev_user_stable_rate, tx_c.timestamp - tx.timestamp))

    # Check `LendingPool` logs
    assert tx_c.events['Repay']['reserve'] == weth
    assert tx_c.events['Repay']['user'] == borrower
    assert tx_c.events['Repay']['repayer'] == borrower
    assert tx_c.events['Repay']['amount'] == repay_amount
    assert tx_c.events['ReserveDataUpdated']['reserve'] == weth
    assert tx_c.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx_c.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx_c.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx_c.events['ReserveDataUpdated']['variableBorrowIndex'] == variable_borrow_index
    assert tx_c.events['ReserveDataUpdated']['liquidityIndex'] == liquidity_index

    # Check `StableDebtToken` logs
    assert tx_c.events['Burn']['user'] == borrower
    assert tx_c.events['Burn']['amount'] == repay_amount
    assert tx_c.events['Burn']['currentBalance'] == curr_user_balance
    assert tx_c.events['Burn']['balanceIncrease'] == curr_user_balance - prev_user_balance
    assert tx_c.events['Burn']['avgStableRate'] == overall_stable_rate
    assert tx_c.events['Burn']['newTotalSupply'] == total_stable_debt
    assert tx_c.events['Transfer'][0]['from'] == borrower
    assert tx_c.events['Transfer'][0]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][0]['value'] == repay_amount

    # Check `WETH` logs
    assert tx_c.events['Transfer'][1]['src'] == borrower
    assert tx_c.events['Transfer'][1]['dst'] == weth_atoken
    assert tx_c.events['Transfer'][1]['wad'] == repay_amount

    # Check `StableDebtToken` state
    assert weth_stable_debt.balanceOf(borrower) == curr_user_balance - repay_amount
    assert weth_stable_debt.totalSupply() == total_stable_debt
    assert weth_stable_debt.getUserLastUpdated(borrower) == tx_c.timestamp
    assert weth_stable_debt.getTotalSupplyLastUpdated() == tx_c.timestamp
    assert weth_stable_debt.getUserStableRate(borrower) == prev_user_stable_rate
    assert weth_stable_debt.principalBalanceOf(borrower) == curr_user_balance - repay_amount

    # Check `WETH` state
    assert weth.balanceOf(borrower) == 0

    # Check `LendingPool` state
    calculated_collateral = int(round(terc20_deposit_amount * (price / WEI), 0)) # Note: deposit made in tERC20
    calculated_health = wad_div(calculated_collateral * tecr20_threshold // 10_000, curr_user_balance - repay_amount)
    (collateral, debt, available_borrow, threshold, ltv, health) = lending_pool.getUserAccountData(borrower)
    assert collateral == calculated_collateral
    assert debt == curr_user_balance - repay_amount
    assert threshold == tecr20_threshold
    assert ltv == tecr20_ltv
    assert health == calculated_health

    ### Full Repay Second Borrower ###

    time_increase = 5 # Time difference for next block
    web3.manager.request_blocking("evm_increaseTime", time_increase)

    user_stable_rate = weth_stable_debt.getUserStableRate(borrower_b)
    repay_amount_b = borrow_amount_b * 2 # Note repays larger than the amount will repay entire debt
    weth.deposit({'from': borrower_b, 'value': repay_amount_b})
    weth.approve(lending_pool, repay_amount_b, {'from': borrower_b})

    # `repay()`
    tx_d = lending_pool.repay(
        weth,
        repay_amount_b,
        INTEREST_RATE_MODE_STABLE,
        borrower_b,
        {'from': borrower_b}
    )

    ## Python Calculations ##
    time_diff = tx_d.timestamp - tx_c.timestamp
    prev_user_stable_rate = user_stable_rate
    prev_stable_rate = stable_rate # SRt-1
    prev_overall_stable_rate = overall_stable_rate # ^SRt-1
    prev_total_debt_with_interest = ray_mul(total_debt, calculate_compound_interest(prev_overall_stable_rate, time_diff))
    prev_user_balance = borrow_amount_b
    curr_user_balance = ray_mul(prev_user_balance, calculate_compound_interest(prev_user_stable_rate, tx_d.timestamp - tx_b.timestamp)) # `borrower_b` last update was `tx_b`

    # `updateState()`
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = RAY # VIt = 1 as variable debt == 0

    # `updateInterestRates()`
    total_stable_debt = prev_total_debt_with_interest - curr_user_balance # SDt
    total_variable_debt = 0 # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity += curr_user_balance
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(prev_overall_stable_rate, prev_total_debt_with_interest, prev_user_stable_rate, curr_user_balance, False)
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` logs
    assert tx_d.events['Repay']['reserve'] == weth
    assert tx_d.events['Repay']['user'] == borrower_b
    assert tx_d.events['Repay']['repayer'] == borrower_b
    assert tx_d.events['Repay']['amount'] == curr_user_balance
    assert tx_d.events['ReserveDataUpdated']['reserve'] == weth
    assert tx_d.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx_d.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx_d.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx_d.events['ReserveDataUpdated']['variableBorrowIndex'] == variable_borrow_index
    assert tx_d.events['ReserveDataUpdated']['liquidityIndex'] == liquidity_index

    # Check `StableDebtToken` logs
    assert tx_d.events['Burn']['user'] == borrower_b
    assert tx_d.events['Burn']['amount'] == curr_user_balance
    assert tx_d.events['Burn']['currentBalance'] == curr_user_balance
    assert tx_d.events['Burn']['balanceIncrease'] == curr_user_balance - prev_user_balance
    assert tx_d.events['Burn']['avgStableRate'] == overall_stable_rate
    assert tx_d.events['Burn']['newTotalSupply'] == total_stable_debt
    assert tx_d.events['Transfer'][0]['from'] == borrower_b
    assert tx_d.events['Transfer'][0]['to'] == ZERO_ADDRESS
    assert tx_d.events['Transfer'][0]['value'] == curr_user_balance

    # Check `WETH` logs
    assert tx_d.events['Transfer'][1]['src'] == borrower_b
    assert tx_d.events['Transfer'][1]['dst'] == weth_atoken
    assert tx_d.events['Transfer'][1]['wad'] == curr_user_balance

    # Check `StableDebtToken` state
    assert weth_stable_debt.balanceOf(borrower_b) == 0
    assert weth_stable_debt.totalSupply() == total_stable_debt
    assert weth_stable_debt.getUserLastUpdated(borrower_b) == 0
    assert weth_stable_debt.getTotalSupplyLastUpdated() == tx_d.timestamp
    assert weth_stable_debt.getUserStableRate(borrower_b) == 0
    assert weth_stable_debt.principalBalanceOf(borrower_b) == 0

    # Check `WETH` state
    assert weth.balanceOf(borrower_b) == repay_amount_b - curr_user_balance + borrow_amount_b

    # Check `LendingPool` state
    calculated_collateral = int(round(terc20_deposit_amount_b * (price / WEI), 0)) # Note: deposit made in tERC20
    calculated_health = (1 << 256) - 1
    (collateral, debt, available_borrow, threshold, ltv, health) = lending_pool.getUserAccountData(borrower_b)
    assert collateral == calculated_collateral
    assert debt == 0
    assert threshold == tecr20_threshold
    assert ltv == tecr20_ltv
    assert health == calculated_health


# Test `repay()` with a stable rate
# `depositor` deposits WETH
# `borrower` deposits tERC20 and borrows WETH
# `borrower_b` deposits tERC20 and borrows WETH
# Repay on behalf of `borrower`
# Repay on behalf of borrower_b`
def test_repay_on_behalf_of():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    deposit_amount = 10_000_000_000_000_000_000
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositor})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Set market lending rate
    lending_rate_oracle.setMarketBorrowRate(weth, MARKET_BORROW_RATE)

    # `deposit()` weth
    lending_pool.deposit(weth, deposit_amount, depositor, 0, {'from': depositor})

    # Add additional reserve
    terc20 = accounts[0].deploy(
        MintableDelegationERC20,
        "Test ERC20",
        "tERC20",
        18,
    )

    # Initialise reserve tERC20
    (terc20_atoken, terc20_stable_debt, terc20_variable_debt) = setup_new_reserve(configurator, terc20, lending_pool, pool_admin)

    # Turn on collateral and borrowing
    (tecr20_ltv, tecr20_threshold, tecr20_bonus) = allow_reserve_collateral_and_borrowing(configurator, terc20, pool_admin)

    # Setup price for tERC20
    price = WEI // 10 # 1 tERC20 : 0.1 ETH
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    ### First Borrower ###

    # Create tERC20 tokens for `borrower` and deposit them into `LendingPool`
    borrower = accounts[5]
    terc20_deposit_amount = deposit_amount // 10
    terc20.mint(terc20_deposit_amount, {'from': borrower})
    terc20.approve(lending_pool, terc20_deposit_amount, {'from': borrower})
    lending_pool.deposit(terc20, terc20_deposit_amount, borrower, 0, {'from': borrower})

    # `borrow()`
    borrow_amount = terc20_deposit_amount // 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Calculate values
    prev_stable_rate = lending_rate_oracle.getMarketBorrowRate(weth) # SRt-1

    total_stable_debt = borrow_amount # SDt
    total_variable_debt = 0 # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(RAY, 0, prev_stable_rate, borrow_amount, True) # ^SRt
    overall_borrow_rate = ray_div(ray_mul(0, variable_rate) + ray_mul(borrow_amount, overall_stable_rate), 0 + borrow_amount) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    ### Second Borrower ###
    web3.manager.request_blocking("evm_increaseTime", 4) # ensure some interest is accrued

    # Create tERC20 tokens for `borrower_b` and deposit them into `LendingPool`
    borrower_b = accounts[6]
    terc20_deposit_amount_b = deposit_amount // 100
    terc20.mint(terc20_deposit_amount_b, {'from': borrower_b})
    terc20.approve(lending_pool, terc20_deposit_amount_b, {'from': borrower_b})
    lending_pool.deposit(terc20, terc20_deposit_amount_b, borrower_b, 0, {'from': borrower_b})

    # `borrow()`
    borrow_amount_b = terc20_deposit_amount_b // 100
    tx_b = lending_pool.borrow(
        weth,
        borrow_amount_b,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower_b,
        {'from': borrower_b},
    )

    ## Python Calculations ##

    time_diff = tx_b.timestamp - tx.timestamp
    prev_stable_rate = stable_rate # SRt-1
    prev_overall_stable_rate = overall_stable_rate # ^SRt-1
    prev_total_debt_with_interest = ray_mul(borrow_amount, calculate_compound_interest(prev_overall_stable_rate, time_diff))

    # `updateState()`
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), RAY) # LIt
    variable_borrow_index = RAY # VIt = 1 as variable debt == 0

    # `updateInterestRates()`
    total_stable_debt = prev_total_debt_with_interest + borrow_amount_b # SDt
    total_variable_debt = 0 # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity -= borrow_amount_b
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(prev_overall_stable_rate, prev_total_debt_with_interest, prev_stable_rate, borrow_amount_b, True)
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    ### Partial Repay First Borrower ###

    repayer = accounts[7]
    web3.manager.request_blocking("evm_increaseTime", 4) # ensure some interest is accrued
    prev_user_stable_rate = weth_stable_debt.getUserStableRate(borrower) # Store previous user overall stable rate

    # `repay()`
    repay_amount = borrow_amount # Note interest will be accrued so SDt(x) > borrow_amount
    weth.deposit({'from': repayer, 'value': repay_amount})
    weth.approve(lending_pool, repay_amount, {'from': repayer})
    tx_c = lending_pool.repay(
        weth,
        repay_amount,
        INTEREST_RATE_MODE_STABLE,
        borrower,
        {'from': repayer}
    )

    ## Python Calculations ##

    time_diff = tx_c.timestamp - tx_b.timestamp
    prev_stable_rate = stable_rate # SRt-1
    prev_overall_stable_rate = overall_stable_rate # ^SRt-1
    prev_total_debt_with_interest = ray_mul(total_debt, calculate_compound_interest(prev_overall_stable_rate, time_diff))

    # `updateState()`
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = RAY # VIt = 1 as variable debt == 0

    # `updateInterestRates()`
    total_stable_debt = prev_total_debt_with_interest - repay_amount # SDt
    total_variable_debt = 0 # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity += repay_amount
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(prev_overall_stable_rate, prev_total_debt_with_interest, prev_user_stable_rate, repay_amount, False)
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # `StableDebt` user balances, `borrower` last update is `tx` and the principal balance is `borrow_amount`
    prev_user_balance = borrow_amount
    curr_user_balance = ray_mul(prev_user_balance, calculate_compound_interest(prev_user_stable_rate, tx_c.timestamp - tx.timestamp))

    # Check `LendingPool` logs
    assert tx_c.events['Repay']['reserve'] == weth
    assert tx_c.events['Repay']['user'] == borrower
    assert tx_c.events['Repay']['repayer'] == repayer
    assert tx_c.events['Repay']['amount'] == repay_amount
    assert tx_c.events['ReserveDataUpdated']['reserve'] == weth
    assert tx_c.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx_c.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx_c.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx_c.events['ReserveDataUpdated']['variableBorrowIndex'] == variable_borrow_index
    assert tx_c.events['ReserveDataUpdated']['liquidityIndex'] == liquidity_index

    # Check `StableDebtToken` logs
    assert tx_c.events['Burn']['user'] == borrower
    assert tx_c.events['Burn']['amount'] == repay_amount
    assert tx_c.events['Burn']['currentBalance'] == curr_user_balance
    assert tx_c.events['Burn']['balanceIncrease'] == curr_user_balance - prev_user_balance
    assert tx_c.events['Burn']['avgStableRate'] == overall_stable_rate
    assert tx_c.events['Burn']['newTotalSupply'] == total_stable_debt
    assert tx_c.events['Transfer'][0]['from'] == borrower
    assert tx_c.events['Transfer'][0]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][0]['value'] == repay_amount

    # Check `WETH` logs
    assert tx_c.events['Transfer'][1]['src'] == repayer
    assert tx_c.events['Transfer'][1]['dst'] == weth_atoken
    assert tx_c.events['Transfer'][1]['wad'] == repay_amount

    # Check `StableDebtToken` state
    assert weth_stable_debt.balanceOf(borrower) == curr_user_balance - repay_amount
    assert weth_stable_debt.totalSupply() == total_stable_debt
    assert weth_stable_debt.getUserLastUpdated(borrower) == tx_c.timestamp
    assert weth_stable_debt.getTotalSupplyLastUpdated() == tx_c.timestamp
    assert weth_stable_debt.getUserStableRate(borrower) == prev_user_stable_rate
    assert weth_stable_debt.principalBalanceOf(borrower) == curr_user_balance - repay_amount

    # Check `WETH` state
    assert weth.balanceOf(repayer) == 0

    # Check `LendingPool` state
    calculated_collateral = int(round(terc20_deposit_amount * (price / WEI), 0)) # Note: deposit made in tERC20
    calculated_health = wad_div(calculated_collateral * tecr20_threshold // 10_000, curr_user_balance - repay_amount)
    (collateral, debt, available_borrow, threshold, ltv, health) = lending_pool.getUserAccountData(borrower)
    assert collateral == calculated_collateral
    assert debt == curr_user_balance - repay_amount
    assert threshold == tecr20_threshold
    assert ltv == tecr20_ltv
    assert health == calculated_health

    ### Full Repay Second Borrower ###

    time_increase = 5 # Time difference for next block
    web3.manager.request_blocking("evm_increaseTime", time_increase)

    user_stable_rate = weth_stable_debt.getUserStableRate(borrower_b)
    repay_amount_b = borrow_amount_b * 2 # Note repays larger than the amount will repay entire debt
    weth.deposit({'from': repayer, 'value': repay_amount_b})
    weth.approve(lending_pool, repay_amount_b, {'from': repayer})

    # `repay()`
    tx_d = lending_pool.repay(
        weth,
        repay_amount_b,
        INTEREST_RATE_MODE_STABLE,
        borrower_b,
        {'from': repayer}
    )

    ## Python Calculations ##
    time_diff = tx_d.timestamp - tx_c.timestamp
    prev_user_stable_rate = user_stable_rate
    prev_stable_rate = stable_rate # SRt-1
    prev_overall_stable_rate = overall_stable_rate # ^SRt-1
    prev_total_debt_with_interest = ray_mul(total_debt, calculate_compound_interest(prev_overall_stable_rate, time_diff))
    prev_user_balance = borrow_amount_b
    curr_user_balance = ray_mul(prev_user_balance, calculate_compound_interest(prev_user_stable_rate, tx_d.timestamp - tx_b.timestamp)) # `borrower_b` last update was `tx_b`

    # `updateState()`
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = RAY # VIt = 1 as variable debt == 0

    # `updateInterestRates()`
    total_stable_debt = prev_total_debt_with_interest - curr_user_balance # SDt
    total_variable_debt = 0 # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity += curr_user_balance
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(prev_overall_stable_rate, prev_total_debt_with_interest, prev_user_stable_rate, curr_user_balance, False)
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` logs
    assert tx_d.events['Repay']['reserve'] == weth
    assert tx_d.events['Repay']['user'] == borrower_b
    assert tx_d.events['Repay']['repayer'] == repayer
    assert tx_d.events['Repay']['amount'] == curr_user_balance
    assert tx_d.events['ReserveDataUpdated']['reserve'] == weth
    assert tx_d.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx_d.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx_d.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx_d.events['ReserveDataUpdated']['variableBorrowIndex'] == variable_borrow_index
    assert tx_d.events['ReserveDataUpdated']['liquidityIndex'] == liquidity_index

    # Check `StableDebtToken` logs
    assert tx_d.events['Burn']['user'] == borrower_b
    assert tx_d.events['Burn']['amount'] == curr_user_balance
    assert tx_d.events['Burn']['currentBalance'] == curr_user_balance
    assert tx_d.events['Burn']['balanceIncrease'] == curr_user_balance - prev_user_balance
    assert tx_d.events['Burn']['avgStableRate'] == overall_stable_rate
    assert tx_d.events['Burn']['newTotalSupply'] == total_stable_debt
    assert tx_d.events['Transfer'][0]['from'] == borrower_b
    assert tx_d.events['Transfer'][0]['to'] == ZERO_ADDRESS
    assert tx_d.events['Transfer'][0]['value'] == curr_user_balance

    # Check `WETH` logs
    assert tx_d.events['Transfer'][1]['src'] == repayer
    assert tx_d.events['Transfer'][1]['dst'] == weth_atoken
    assert tx_d.events['Transfer'][1]['wad'] == curr_user_balance

    # Check `StableDebtToken` state
    assert weth_stable_debt.balanceOf(borrower_b) == 0
    assert weth_stable_debt.totalSupply() == total_stable_debt
    assert weth_stable_debt.getUserLastUpdated(borrower_b) == 0
    assert weth_stable_debt.getTotalSupplyLastUpdated() == tx_d.timestamp
    assert weth_stable_debt.getUserStableRate(borrower_b) == 0
    assert weth_stable_debt.principalBalanceOf(borrower_b) == 0

    # Check `WETH` state
    assert weth.balanceOf(repayer) == repay_amount_b - curr_user_balance

    # Check `LendingPool` state
    calculated_collateral = int(round(terc20_deposit_amount_b * (price / WEI), 0)) # Note: deposit made in tERC20
    calculated_health = (1 << 256) - 1
    (collateral, debt, available_borrow, threshold, ltv, health) = lending_pool.getUserAccountData(borrower_b)
    assert collateral == calculated_collateral
    assert debt == 0
    assert threshold == tecr20_threshold
    assert ltv == tecr20_ltv
    assert health == calculated_health


# Test `repay()` with a variable rate
# `depositor` deposits WETH
# `borrower` deposits tERC20 and borrows WETH
# `borrower_b` deposits tERC20 and borrows WETH
# `borrower` partially repays WETH
# `borrower_b` fully repays WETH
def test_repay_variable():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    deposit_amount = 10_000_000_000_000_000_000
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositor})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Set market lending rate
    lending_rate_oracle.setMarketBorrowRate(weth, MARKET_BORROW_RATE)

    # `deposit()` weth
    lending_pool.deposit(weth, deposit_amount, depositor, 0, {'from': depositor})

    # Add additional reserve
    terc20 = accounts[0].deploy(
        MintableDelegationERC20,
        "Test ERC20",
        "tERC20",
        18,
    )

    # Initialise reserve tERC20
    (terc20_atoken, terc20_stable_debt, terc20_variable_debt) = setup_new_reserve(configurator, terc20, lending_pool, pool_admin)

    # Turn on collateral and borrowing
    (tecr20_ltv, tecr20_threshold, tecr20_bonus) = allow_reserve_collateral_and_borrowing(configurator, terc20, pool_admin)

    # Setup price for tERC20
    price = WEI // 10 # 1 tERC20 : 0.1 ETH
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    ### First Borrower ###

    # Create tERC20 tokens for `borrower` and deposit them into `LendingPool`
    borrower = accounts[5]
    terc20_deposit_amount = deposit_amount // 10
    terc20.mint(terc20_deposit_amount, {'from': borrower})
    terc20.approve(lending_pool, terc20_deposit_amount, {'from': borrower})
    lending_pool.deposit(terc20, terc20_deposit_amount, borrower, 0, {'from': borrower})

    # `borrow()`
    borrow_amount = terc20_deposit_amount // 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    ## Python Calculations ##

    # `updateState()` occurs before borrow
    liquidity_index = RAY # LIt
    variable_borrow_index = RAY # VIt

    # VariableDebtToken.mint() updates
    scaled_total_supply = 0 + ray_div(borrow_amount, variable_borrow_index) # 0 is previous scaled total supply

    # `updateInterestRates()`
    total_stable_debt = 0 # SDt
    total_variable_debt = borrow_amount # VDt
    total_debt = total_variable_debt + total_stable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = weth_stable_debt.getAverageStableRate() # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    ### Second Borrower ###
    web3.manager.request_blocking("evm_increaseTime", 4) # ensure some interest is accrued

    # Create tERC20 tokens for `borrower_b` and deposit them into `LendingPool`
    borrower_b = accounts[6]
    terc20_deposit_amount_b = deposit_amount // 100
    terc20.mint(terc20_deposit_amount_b, {'from': borrower_b})
    terc20.approve(lending_pool, terc20_deposit_amount_b, {'from': borrower_b})
    lending_pool.deposit(terc20, terc20_deposit_amount_b, borrower_b, 0, {'from': borrower_b})

    # `borrow()`
    borrow_amount_b = terc20_deposit_amount_b // 100
    tx_b = lending_pool.borrow(
        weth,
        borrow_amount_b,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower_b,
        {'from': borrower_b},
    )

    ## Python Calculations ##

    # `updateState()`
    time_diff = tx_b.timestamp - tx.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt

    # VariableDebtToken.mint() updates
    scaled_total_supply = scaled_total_supply + ray_div(borrow_amount_b, variable_borrow_index)

    # `updateInterestRates()`
    total_stable_debt = 0 # SDt
    total_variable_debt = ray_mul(scaled_total_supply, variable_borrow_index) # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity -= borrow_amount_b
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = 0 # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    ### Partial Repay First Borrower ###
    web3.manager.request_blocking("evm_increaseTime", 4) # ensure some interest is accrued

    # `repay()`
    repay_amount = borrow_amount # Note interest will be accrued so SDt(x) > borrow_amount
    weth.approve(lending_pool, repay_amount, {'from': borrower})
    tx_c = lending_pool.repay(
        weth,
        repay_amount,
        INTEREST_RATE_MODE_VARIABLE,
        borrower,
        {'from': borrower}
    )

    ## Python Calculations ##

    # `updateState()`
    time_diff = tx_c.timestamp - tx_b.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt

    # VariableDebtToken.burn() updates
    prev_user_balance_with_interest = ray_mul(borrow_amount, variable_borrow_index)
    scaled_total_supply = scaled_total_supply - ray_div(repay_amount, variable_borrow_index)

    # `updateInterestRates()`
    total_stable_debt = 0 # SDt
    total_variable_debt = ray_mul(scaled_total_supply, variable_borrow_index) # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity += repay_amount
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = 0 # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` logs
    assert tx_c.events['Repay']['reserve'] == weth
    assert tx_c.events['Repay']['user'] == borrower
    assert tx_c.events['Repay']['repayer'] == borrower
    assert tx_c.events['Repay']['amount'] == repay_amount
    assert tx_c.events['ReserveDataUpdated']['reserve'] == weth
    assert tx_c.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx_c.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx_c.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx_c.events['ReserveDataUpdated']['variableBorrowIndex'] == variable_borrow_index
    assert tx_c.events['ReserveDataUpdated']['liquidityIndex'] == liquidity_index

    # Check `StableDebtToken` logs
    assert tx_c.events['Burn']['user'] == borrower
    assert tx_c.events['Burn']['amount'] == repay_amount
    assert tx_c.events['Burn']['index'] == variable_borrow_index
    assert tx_c.events['Transfer'][0]['from'] == borrower
    assert tx_c.events['Transfer'][0]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][0]['value'] == repay_amount

    # Check `WETH` logs
    assert tx_c.events['Transfer'][1]['src'] == borrower
    assert tx_c.events['Transfer'][1]['dst'] == weth_atoken
    assert tx_c.events['Transfer'][1]['wad'] == repay_amount

    # Check `VariableDebtToken` state
    scaled_balance = borrow_amount - ray_div(repay_amount, variable_borrow_index)
    actual_balance = ray_mul(scaled_balance, variable_borrow_index)
    assert weth_variable_debt.scaledBalanceOf(borrower) == scaled_balance
    assert weth_variable_debt.balanceOf(borrower) == actual_balance
    assert weth_variable_debt.totalSupply() == total_variable_debt
    assert weth_variable_debt.scaledTotalSupply() == scaled_total_supply

    # Check `WETH` state
    assert weth.balanceOf(borrower) == 0

    # Check `LendingPool` state
    calculated_collateral = int(round(terc20_deposit_amount * (price / WEI), 0)) # Note: deposit made in tERC20
    calculated_health = wad_div(calculated_collateral * tecr20_threshold // 10_000, actual_balance)
    (collateral, debt, available_borrow, threshold, ltv, health) = lending_pool.getUserAccountData(borrower)
    assert collateral == calculated_collateral
    assert debt == actual_balance
    assert threshold == tecr20_threshold
    assert ltv == tecr20_ltv
    assert health == calculated_health

    ### Full Repay Second Borrower ###

    time_increase = 5 # Time difference for next block
    web3.manager.request_blocking("evm_increaseTime", time_increase)

    prev_user_scaled_balance = weth_variable_debt.scaledBalanceOf(borrower_b)
    repay_amount_b = borrow_amount_b * 2 # Note repays larger than the amount will repay entire debt
    weth.deposit({'from': borrower_b, 'value': repay_amount_b})
    weth.approve(lending_pool, repay_amount_b, {'from': borrower_b})

    # `repay()`
    tx_d = lending_pool.repay(
        weth,
        repay_amount_b,
        INTEREST_RATE_MODE_VARIABLE,
        borrower_b,
        {'from': borrower_b}
    )

    ## Python Calculations ##

    # `updateState()`
    time_diff = tx_d.timestamp - tx_c.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt

    # VariableDebtToken.burn() updates
    prev_user_balance = ray_mul(prev_user_scaled_balance, variable_borrow_index)
    scaled_total_supply = scaled_total_supply - ray_div(prev_user_balance, variable_borrow_index)
    assert repay_amount_b >= prev_user_balance
    repay_amount_b = prev_user_balance # repay amount is limited to min(debt, repay_amount)

    # `updateInterestRates()`
    total_stable_debt = 0 # SDt
    total_variable_debt = ray_mul(scaled_total_supply, variable_borrow_index) # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity += repay_amount_b
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = 0 # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` logs
    assert tx_d.events['Repay']['reserve'] == weth
    assert tx_d.events['Repay']['user'] == borrower_b
    assert tx_d.events['Repay']['repayer'] == borrower_b
    assert tx_d.events['Repay']['amount'] == repay_amount_b
    assert tx_d.events['ReserveDataUpdated']['reserve'] == weth
    assert tx_d.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx_d.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx_d.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx_d.events['ReserveDataUpdated']['variableBorrowIndex'] == variable_borrow_index
    assert tx_d.events['ReserveDataUpdated']['liquidityIndex'] == liquidity_index

    # Check `StableDebtToken` logs
    assert tx_d.events['Burn']['user'] == borrower_b
    assert tx_d.events['Burn']['amount'] == repay_amount_b
    assert tx_d.events['Burn']['index'] == variable_borrow_index
    assert tx_d.events['Transfer'][0]['from'] == borrower_b
    assert tx_d.events['Transfer'][0]['to'] == ZERO_ADDRESS
    assert tx_d.events['Transfer'][0]['value'] == repay_amount_b

    # Check `WETH` logs
    assert tx_d.events['Transfer'][1]['src'] == borrower_b
    assert tx_d.events['Transfer'][1]['dst'] == weth_atoken
    assert tx_d.events['Transfer'][1]['wad'] == repay_amount_b

    # Check `VariableDebtToken` state
    scaled_balance = prev_user_scaled_balance - ray_div(repay_amount_b, variable_borrow_index)
    actual_balance = ray_mul(scaled_balance, variable_borrow_index)
    assert weth_variable_debt.scaledBalanceOf(borrower_b) == scaled_balance
    assert weth_variable_debt.balanceOf(borrower_b) == actual_balance
    assert weth_variable_debt.totalSupply() == total_variable_debt
    assert weth_variable_debt.scaledTotalSupply() == scaled_total_supply

    # Check `WETH` state
    assert weth.balanceOf(borrower) == 0

    # Check `LendingPool` state
    calculated_collateral = int(round(terc20_deposit_amount_b * (price / WEI), 0)) # Note: deposit made in tERC20
    calculated_health = (1 << 256) - 1
    (collateral, debt, available_borrow, threshold, ltv, health) = lending_pool.getUserAccountData(borrower_b)
    assert collateral == calculated_collateral
    assert debt == actual_balance
    assert threshold == tecr20_threshold
    assert ltv == tecr20_ltv
    assert health == calculated_health


#######################
# swapBorrowRateMode()
#######################


# Test `swapBorrowRateMode()` variable to stable
# `depositor` deposits WETH
# `borrower` deposits tERC20 and borrows WETH
# `borrower` swaps rate mode
def test_swap_borrow_rate_mode_variable_to_stable():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    deposit_amount = 10_000_000_000_000_000_000
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositor})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Set market lending rate
    lending_rate_oracle.setMarketBorrowRate(weth, MARKET_BORROW_RATE)

    # `deposit()` weth
    lending_pool.deposit(weth, deposit_amount, depositor, 0, {'from': depositor})

    # Add additional reserve
    terc20 = accounts[0].deploy(
        MintableDelegationERC20,
        "Test ERC20",
        "tERC20",
        18,
    )

    # Initialise reserve tERC20
    (terc20_atoken, terc20_stable_debt, terc20_variable_debt) = setup_new_reserve(configurator, terc20, lending_pool, pool_admin)

    # Turn on collateral and borrowing
    (tecr20_ltv, tecr20_threshold, tecr20_bonus) = allow_reserve_collateral_and_borrowing(configurator, terc20, pool_admin)

    # Setup price for tERC20
    price = WEI // 10 # 1 tERC20 : 0.1 ETH
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    # Create tERC20 tokens for `borrower` and deposit them into `LendingPool`
    borrower = accounts[5]
    terc20_deposit_amount = deposit_amount // 10
    terc20.mint(terc20_deposit_amount, {'from': borrower})
    terc20.approve(lending_pool, terc20_deposit_amount, {'from': borrower})
    lending_pool.deposit(terc20, terc20_deposit_amount, borrower, 0, {'from': borrower})

    # `borrow()`
    borrow_amount = terc20_deposit_amount // 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    ## Python Calculations ##

    # `updateState()` occurs before borrow
    liquidity_index = RAY # LIt
    variable_borrow_index = RAY # VIt

    # VariableDebtToken.mint() updates
    scaled_total_supply = 0 + ray_div(borrow_amount, variable_borrow_index) # 0 is previous scaled total supply

    # `updateInterestRates()`
    total_stable_debt = 0 # SDt
    total_variable_debt = borrow_amount # VDt
    total_debt = total_variable_debt + total_stable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = weth_stable_debt.getAverageStableRate() # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # `swapBorrowRateMode()`
    web3.manager.request_blocking("evm_increaseTime", 4) # ensure some interest is accrued
    tx_b = lending_pool.swapBorrowRateMode(
        weth,
        INTEREST_RATE_MODE_VARIABLE,
        {'from': borrower}
    )

    ## Python Calculations ##
    prev_stable_rate = stable_rate

    # `updateState()`
    time_diff = tx_b.timestamp - tx.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt

    # VariableDebtToken.burn() updates
    prev_user_balance_with_interest = ray_mul(borrow_amount, variable_borrow_index)
    scaled_total_supply = 0

    # `updateInterestRates()`
    total_stable_debt = prev_user_balance_with_interest # SDt
    total_variable_debt = 0 # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = available_liquidity # remains unchanged
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(RAY, 0, prev_stable_rate, total_stable_debt, True) # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` logs
    assert tx_b.events['Swap']['reserve'] == weth
    assert tx_b.events['Swap']['user'] == borrower
    assert tx_b.events['Swap']['rateMode'] == INTEREST_RATE_MODE_VARIABLE
    assert tx_b.events['ReserveDataUpdated']['reserve'] == weth
    assert tx_b.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx_b.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx_b.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx_b.events['ReserveDataUpdated']['variableBorrowIndex'] == variable_borrow_index
    assert tx_b.events['ReserveDataUpdated']['liquidityIndex'] == liquidity_index

    # Check `VariableDebtToken` logs
    assert tx_b.events['Burn']['user'] == borrower
    assert tx_b.events['Burn']['amount'] == prev_user_balance_with_interest
    assert tx_b.events['Burn']['index'] == variable_borrow_index
    assert tx_b.events['Transfer'][0]['from'] == borrower
    assert tx_b.events['Transfer'][0]['to'] == ZERO_ADDRESS
    assert tx_b.events['Transfer'][0]['value'] == prev_user_balance_with_interest

    # Check `StableDebtToken` logs
    assert tx_b.events['Mint']['user'] == borrower
    assert tx_b.events['Mint']['onBehalfOf'] == borrower
    assert tx_b.events['Mint']['amount'] == prev_user_balance_with_interest
    assert tx_b.events['Mint']['currentBalance'] == 0
    assert tx_b.events['Mint']['balanceIncrease'] == 0
    assert tx_b.events['Mint']['newRate'] == prev_stable_rate
    assert tx_b.events['Mint']['avgStableRate'] == prev_stable_rate
    assert tx_b.events['Mint']['newTotalSupply'] == prev_user_balance_with_interest
    assert tx_b.events['Transfer'][1]['to'] == borrower
    assert tx_b.events['Transfer'][1]['from'] == ZERO_ADDRESS
    assert tx_b.events['Transfer'][1]['value'] == prev_user_balance_with_interest

    # Check `VariableDebtToken` state
    scaled_balance = 0
    actual_balance = 0
    assert weth_variable_debt.scaledBalanceOf(borrower) == scaled_balance
    assert weth_variable_debt.balanceOf(borrower) == actual_balance
    assert weth_variable_debt.totalSupply() == total_variable_debt
    assert weth_variable_debt.scaledTotalSupply() == scaled_total_supply

    # Check `StableDebtToken` state
    assert weth_stable_debt.balanceOf(borrower) == prev_user_balance_with_interest
    assert weth_stable_debt.getUserLastUpdated(borrower) == tx_b.timestamp
    assert weth_stable_debt.getTotalSupplyLastUpdated() == tx_b.timestamp
    assert weth_stable_debt.getUserStableRate(borrower) == prev_stable_rate
    assert weth_stable_debt.totalSupply() == prev_user_balance_with_interest
    assert weth_stable_debt.principalBalanceOf(borrower) == prev_user_balance_with_interest


    # Check `LendingPool` state
    calculated_collateral = int(round(terc20_deposit_amount * (price / WEI), 0)) # Note: deposit made in tERC20
    calculated_health = wad_div(calculated_collateral * tecr20_threshold // 10_000, total_debt)
    (collateral, debt, available_borrow, threshold, ltv, health) = lending_pool.getUserAccountData(borrower)
    assert collateral == calculated_collateral
    assert debt == total_debt
    assert threshold == tecr20_threshold
    assert ltv == tecr20_ltv
    assert health == calculated_health


# Test `swapBorrowRateMode()` stable to variable
# `depositor` deposits WETH
# `borrower` deposits tERC20 and borrows WETH
# `borrower` swaps rate mode
def test_swap_borrow_rate_mode_stable_to_variable():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    deposit_amount = 10_000_000_000_000_000_000
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositor})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # `deposit()` weth
    lending_pool.deposit(weth, deposit_amount, depositor, 0, {'from': depositor})

    # Add additional reserve
    terc20 = accounts[0].deploy(
        MintableDelegationERC20,
        "Test ERC20",
        "tERC20",
        18,
    )

    # Initialise reserve tERC20
    (terc20_atoken, terc20_stable_debt, terc20_variable_debt) = setup_new_reserve(configurator, terc20, lending_pool, pool_admin)

    # Turn on collateral and borrowing
    (tecr20_ltv, tecr20_threshold, tecr20_bonus) = allow_reserve_collateral_and_borrowing(configurator, terc20, pool_admin)

    # Setup price for tERC20
    price = WEI // 10 # 1 tERC20 : 0.1 ETH
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    ### First Borrower ###

    # Create tERC20 tokens for `borrower` and deposit them into `LendingPool`
    borrower = accounts[5]
    terc20_deposit_amount = deposit_amount // 10
    terc20.mint(terc20_deposit_amount, {'from': borrower})
    terc20.approve(lending_pool, terc20_deposit_amount, {'from': borrower})
    lending_pool.deposit(terc20, terc20_deposit_amount, borrower, 0, {'from': borrower})

    # `borrow()`
    borrow_amount = terc20_deposit_amount // 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Calculate values

    # `updateState()`
    liquidity_index = RAY # LIt
    variable_borrow_index = RAY # VIt

    # `updateInterestRates()`
    total_stable_debt = borrow_amount # SDt
    total_variable_debt = 0 # VDt
    total_debt = total_variable_debt + total_stable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = weth_stable_debt.getAverageStableRate() # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # `swapBorrowRateMode()`
    tx_b = lending_pool.swapBorrowRateMode(
        weth,
        INTEREST_RATE_MODE_STABLE,
        {'from': borrower}
    )

    ## Python Calculations ##

    # `updateState()`
    time_diff = tx_b.timestamp - tx.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = RAY # VIt, since VDt-1 = 0

    # `updateInterestRates()`
    total_stable_debt = 0 # SDt
    total_variable_debt = borrow_amount # VDt, note rate of zero was used so no interest is accrued
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = available_liquidity # remains unchanged
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(RAY, 0, RAY, total_stable_debt, True) # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` logs
    assert tx_b.events['Swap']['reserve'] == weth
    assert tx_b.events['Swap']['user'] == borrower
    assert tx_b.events['Swap']['rateMode'] == INTEREST_RATE_MODE_STABLE
    assert tx_b.events['ReserveDataUpdated']['reserve'] == weth
    assert tx_b.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx_b.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx_b.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx_b.events['ReserveDataUpdated']['variableBorrowIndex'] == variable_borrow_index
    assert tx_b.events['ReserveDataUpdated']['liquidityIndex'] == liquidity_index

    # Check `StableDebtToken` logs
    assert tx_b.events['Burn']['user'] == borrower
    assert tx_b.events['Burn']['amount'] == borrow_amount
    assert tx_b.events['Burn']['currentBalance'] == borrow_amount
    assert tx_b.events['Burn']['balanceIncrease'] == 0
    assert tx_b.events['Burn']['avgStableRate'] == 0
    assert tx_b.events['Burn']['newTotalSupply'] == 0
    assert tx_b.events['Transfer'][0]['from'] == borrower
    assert tx_b.events['Transfer'][0]['to'] == ZERO_ADDRESS
    assert tx_b.events['Transfer'][0]['value'] == borrow_amount

    # Check `VariableDebtToken` logs
    assert tx_b.events['Mint']['from'] == borrower
    assert tx_b.events['Mint']['onBehalfOf'] == borrower
    assert tx_b.events['Mint']['value'] == borrow_amount
    assert tx_b.events['Mint']['index'] == variable_borrow_index
    assert tx_b.events['Transfer'][1]['to'] == borrower
    assert tx_b.events['Transfer'][1]['from'] == ZERO_ADDRESS
    assert tx_b.events['Transfer'][1]['value'] == borrow_amount

    # Check `VariableDebtToken` state
    scaled_balance = borrow_amount
    actual_balance = scaled_balance
    assert weth_variable_debt.scaledBalanceOf(borrower) == scaled_balance
    assert weth_variable_debt.balanceOf(borrower) == actual_balance
    assert weth_variable_debt.totalSupply() == total_variable_debt
    assert weth_variable_debt.scaledTotalSupply() == total_variable_debt

    # Check `StableDebtToken` state
    assert weth_stable_debt.balanceOf(borrower) == 0
    assert weth_stable_debt.getUserLastUpdated(borrower) == 0
    assert weth_stable_debt.getTotalSupplyLastUpdated() == tx_b.timestamp
    assert weth_stable_debt.getUserStableRate(borrower) == 0
    assert weth_stable_debt.totalSupply() == 0
    assert weth_stable_debt.principalBalanceOf(borrower) == 0


    # Check `LendingPool` state
    calculated_collateral = int(round(terc20_deposit_amount * (price / WEI), 0)) # Note: deposit made in tERC20
    calculated_health = wad_div(calculated_collateral * tecr20_threshold // 10_000, total_debt)
    (collateral, debt, available_borrow, threshold, ltv, health) = lending_pool.getUserAccountData(borrower)
    assert collateral == calculated_collateral
    assert debt == total_debt
    assert threshold == tecr20_threshold
    assert ltv == tecr20_ltv
    assert health == calculated_health


##############################
# rebalanceStableBorrowRate()
##############################


# Tests `rebalanceStableBorrowRate()`
# `depositor` deposits WETH
# `borrower` borrows WETH
# `depositor` withdraws WETH such that < 5% remains
# `rebalanceStableBorrowRate(WETH, borrower)`
def test_rebalance_stable_borrow_rate():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    deposit_amount = 10_000_000_000_000_000_000
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositor})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhol, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # `deposit()` weth
    lending_pool.deposit(weth, deposit_amount, depositor, 0, {'from': depositor})

    # Add additional reserve
    terc20 = accounts[0].deploy(
        MintableDelegationERC20,
        "Test ERC20",
        "tERC20",
        18,
    )

    # Initialise reserve tERC20
    (terc20_atoken, terc20_stable_debt, terc20_variable_debt) = setup_new_reserve(configurator, terc20, lending_pool, pool_admin)

    # Turn on collateral and borrowing
    (tecr20_ltv, tecr20_threshold, tecr20_bonus) = allow_reserve_collateral_and_borrowing(configurator, terc20, pool_admin)

    # Setup price for tERC20
    price = WEI // 10 # 1 tERC20 : 0.1 ETH
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    # Create tERC20 tokens for `borrower` and deposit them into `LendingPool`
    borrower = accounts[5]
    terc20_deposit_amount = deposit_amount // 10
    terc20.mint(terc20_deposit_amount, {'from': borrower})
    terc20.approve(lending_pool, terc20_deposit_amount, {'from': borrower})
    lending_pool.deposit(terc20, terc20_deposit_amount, borrower, 0, {'from': borrower})

    # `borrow()`
    borrow_amount = terc20_deposit_amount // 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # `withdraw()` all remaining liquidity
    available_liquidity = weth.balanceOf(weth_atoken)
    withdraw_amount = available_liquidity
    tx_b = lending_pool.withdraw(
        weth,
        withdraw_amount,
        depositor,
        {'from': depositor}
    )

    # `rebalanceStableBorrowRate()`
    web3.manager.request_blocking("evm_increaseTime", 4) # ensure some interest is accrued
    tx_c = lending_pool.rebalanceStableBorrowRate(
        weth,
        borrower,
        {'from': accounts[-1]}
    )

    # `updateState()`
    prev_liquidity_index = tx_b.events['ReserveDataUpdated']['liquidityIndex']
    prev_liquidity_rate = tx_b.events['ReserveDataUpdated']['liquidityRate']
    time_diff = tx_c.timestamp - tx_b.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(prev_liquidity_rate, time_diff), prev_liquidity_index) # LIt
    variable_borrow_index = RAY # VIt, since VDt-1 = 0

    # `updateInterestRates()`
    total_stable_debt = weth_stable_debt.totalSupply() # SDt
    total_variable_debt = 0 # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = 0
    utilization_rate = RAY # Ut
    stable_rate = strategy.stableRateSlope1() + strategy.stableRateSlope2() # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(RAY, 0, stable_rate, total_stable_debt, True) # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` logs
    assert tx_c.events['RebalanceStableBorrowRate']['reserve'] == weth
    assert tx_c.events['RebalanceStableBorrowRate']['user'] == borrower
    assert tx_c.events['ReserveDataUpdated']['reserve'] == weth
    assert tx_c.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx_c.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx_c.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx_c.events['ReserveDataUpdated']['variableBorrowIndex'] == variable_borrow_index
    assert tx_c.events['ReserveDataUpdated']['liquidityIndex'] == liquidity_index

    # Check `StableDebtToken` logs
    assert tx_c.events['Burn']['user'] == borrower
    assert tx_c.events['Burn']['amount'] == borrow_amount
    assert tx_c.events['Burn']['currentBalance'] == borrow_amount
    assert tx_c.events['Burn']['balanceIncrease'] == 0
    assert tx_c.events['Burn']['avgStableRate'] == 0
    assert tx_c.events['Burn']['newTotalSupply'] == 0
    assert tx_c.events['Mint']['user'] == borrower
    assert tx_c.events['Mint']['onBehalfOf'] == borrower
    assert tx_c.events['Mint']['amount'] == borrow_amount
    assert tx_c.events['Mint']['currentBalance'] == 0
    assert tx_c.events['Mint']['balanceIncrease'] == 0
    assert tx_c.events['Mint']['avgStableRate'] == stable_rate
    assert tx_c.events['Mint']['newTotalSupply'] == borrow_amount
    assert tx_c.events['Transfer'][0]['from'] == borrower
    assert tx_c.events['Transfer'][0]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][0]['value'] == borrow_amount

    # Check `StableDebtToken` state
    assert weth_stable_debt.balanceOf(borrower) == borrow_amount
    assert weth_stable_debt.getUserLastUpdated(borrower) == tx_c.timestamp
    assert weth_stable_debt.getTotalSupplyLastUpdated() == tx_c.timestamp
    assert weth_stable_debt.getUserStableRate(borrower) == stable_rate
    assert weth_stable_debt.totalSupply() == borrow_amount
    assert weth_stable_debt.principalBalanceOf(borrower) == borrow_amount

    # Check `LendingPool` state
    calculated_collateral = int(round(terc20_deposit_amount * (price / WEI), 0)) # Note: deposit made in tERC20
    calculated_health = wad_div(calculated_collateral * tecr20_threshold // 10_000, total_debt)
    (collateral, debt, available_borrow, threshold, ltv, health) = lending_pool.getUserAccountData(borrower)
    assert collateral == calculated_collateral
    assert debt == total_debt
    assert threshold == tecr20_threshold
    assert ltv == tecr20_ltv
    assert health == calculated_health


# Tests `rebalanceStableBorrowRate()`
# `depositor` deposits WETH
# `borrower` borrows WETH
# `depositor` withdraws WETH such that < 5% remains
# `rebalanceStableBorrowRate(WETH, random_user)`
@pytest.mark.xfail(reason='Division by zero if user has no stable debt')
def test_rebalance_stable_borrow_rate_with_no_debt():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    deposit_amount = 10_000_000_000_000_000_000
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositor})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhol, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # `deposit()` weth
    lending_pool.deposit(weth, deposit_amount, depositor, 0, {'from': depositor})

    # Add additional reserve
    terc20 = accounts[0].deploy(
        MintableDelegationERC20,
        "Test ERC20",
        "tERC20",
        18,
    )

    # Initialise reserve tERC20
    (terc20_atoken, terc20_stable_debt, terc20_variable_debt) = setup_new_reserve(configurator, terc20, lending_pool, pool_admin)

    # Turn on collateral and borrowing
    (tecr20_ltv, tecr20_threshold, tecr20_bonus) = allow_reserve_collateral_and_borrowing(configurator, terc20, pool_admin)

    # Setup price for tERC20
    price = WEI // 10 # 1 tERC20 : 0.1 ETH
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    # Create tERC20 tokens for `borrower` and deposit them into `LendingPool`
    borrower = accounts[5]
    terc20_deposit_amount = deposit_amount // 10
    terc20.mint(terc20_deposit_amount, {'from': borrower})
    terc20.approve(lending_pool, terc20_deposit_amount, {'from': borrower})
    lending_pool.deposit(terc20, terc20_deposit_amount, borrower, 0, {'from': borrower})

    # `borrow()`
    borrow_amount = terc20_deposit_amount // 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # `withdraw()` all remaining liquidity
    available_liquidity = weth.balanceOf(weth_atoken)
    withdraw_amount = available_liquidity
    tx_b = lending_pool.withdraw(
        weth,
        withdraw_amount,
        depositor,
        {'from': depositor}
    )

    # `rebalanceStableBorrowRate()`, this fails due to a division by zero.
    # Probably cleaner to require a user to have stable debt
    lending_pool.rebalanceStableBorrowRate(
        weth,
        accounts[-1],
        {'from': accounts[-1]}
    )


# Tests `setUserUseReserveAsCollateral()`
def test_set_user_use_reserve_as_collateral():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    user = accounts[4]
    deposit_amount = 10_000_000_000_000_000_000
    weth.deposit({'from': user, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': user})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhol, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # `deposit()` weth
    lending_pool.deposit(weth, deposit_amount, user, 0, {'from': user})

    # `setUserUseReserveAsCollateral()`
    useAsCollateral = True
    tx = lending_pool.setUserUseReserveAsCollateral(weth, useAsCollateral, {'from': user})

    # Check logs and state
    (config,) = lending_pool.getUserConfiguration(user)
    assert config & 2 == 2
    assert tx.events['ReserveUsedAsCollateralEnabled']['reserve'] == weth
    assert tx.events['ReserveUsedAsCollateralEnabled']['user'] == user

    # `setUserUseReserveAsCollateral()` with
    useAsCollateral = False
    tx = lending_pool.setUserUseReserveAsCollateral(weth, useAsCollateral, {'from': user})

    # Check logs and state
    (config,) = lending_pool.getUserConfiguration(user)
    assert config & 2 == 0
    assert tx.events['ReserveUsedAsCollateralDisabled']['reserve'] == weth
    assert tx.events['ReserveUsedAsCollateralDisabled']['user'] == user

    # Add additional reserve
    terc20 = accounts[0].deploy(
        MintableDelegationERC20,
        "Test ERC20",
        "tERC20",
        18,
    )

    # Initialise reserve tERC20
    (terc20_atoken, terc20_stable_debt, terc20_variable_debt) = setup_new_reserve(configurator, terc20, lending_pool, pool_admin)

    # Turn on collateral and borrowing
    (tecr20_ltv, tecr20_threshold, tecr20_bonus) = allow_reserve_collateral_and_borrowing(configurator, terc20, pool_admin)

    # Setup price for tERC20
    price = WEI // 10 # 1 tERC20 : 0.1 ETH
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    # Create tERC20 tokens for `borrower` and deposit them into `LendingPool`
    user = accounts[5]
    terc20_deposit_amount = deposit_amount // 10
    terc20.mint(terc20_deposit_amount, {'from': user})
    terc20.approve(lending_pool, terc20_deposit_amount, {'from': user})
    lending_pool.deposit(terc20, terc20_deposit_amount, user, 0, {'from': user})

    # `setUserUseReserveAsCollateral()` with
    useAsCollateral = False
    tx = lending_pool.setUserUseReserveAsCollateral(terc20, useAsCollateral, {'from': user})

    # Check logs and state
    (config,) = lending_pool.getUserConfiguration(user)
    assert config & 8 == 0
    assert tx.events['ReserveUsedAsCollateralDisabled']['reserve'] == terc20
    assert tx.events['ReserveUsedAsCollateralDisabled']['user'] == user

    # `setUserUseReserveAsCollateral()`
    useAsCollateral = True
    tx = lending_pool.setUserUseReserveAsCollateral(terc20, useAsCollateral, {'from': user})

    # Check logs and state
    (config,) = lending_pool.getUserConfiguration(user)
    assert config & 8 == 8
    assert tx.events['ReserveUsedAsCollateralEnabled']['reserve'] == terc20
    assert tx.events['ReserveUsedAsCollateralEnabled']['user'] == user


####################
# liquidationCall()
####################


# Tests `liquidationCall()` when the stable rate is zero
# principal WETH
# collateral tERC20
def test_liquidation_call_stable_rate_zero():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    deposit_amount = 10 * WEI # 10 ETH
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositor})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # `deposit()` weth
    lending_pool.deposit(weth, deposit_amount, depositor, 0, {'from': depositor})

    # Add additional reserve
    terc20 = accounts[0].deploy(
        MintableDelegationERC20,
        "Test ERC20",
        "tERC20",
        18,
    )

    # Initialise reserve tERC20
    (terc20_atoken, terc20_stable_debt, terc20_variable_debt) = setup_new_reserve(configurator, terc20, lending_pool, pool_admin)

    # Turn on collateral and borrowing
    (tecr20_ltv, tecr20_threshold, tecr20_bonus) = allow_reserve_collateral_and_borrowing(configurator, terc20, pool_admin)

    # Setup price for tERC20
    price = WEI // 10 # 0.1 tERC20 : 1 ETH
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    ### Borrowing ###

    # Create tERC20 tokens for `borrower` and deposit them into `LendingPool`
    borrower = accounts[5]
    terc20_deposit_amount = deposit_amount
    terc20.mint(terc20_deposit_amount, {'from': borrower})
    terc20.approve(lending_pool, terc20_deposit_amount, {'from': borrower})
    lending_pool.deposit(terc20, terc20_deposit_amount, borrower, 0, {'from': borrower})

    # `borrow()`
    borrow_amount = terc20_deposit_amount * price // WEI // 10 # 10% of collateral in ETH
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Calculate values
    total_variable_debt = 0
    total_stable_debt = borrow_amount
    total_debt = total_variable_debt + total_stable_debt
    available_liquidity = deposit_amount - borrow_amount
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(0, strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = weth_stable_debt.getAverageStableRate() # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    ### Liquidation Call ###

    # Drop price for tERC20 to make position unhealthy (debt = collateral)
    price = price // 10 # 0.01 tERC20 : 1 ETH
    tx_b = price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    liquidator = accounts[6]
    debt_to_cover = borrow_amount # Note stable rate is 0 so no interest accrues
    weth.deposit({'from': liquidator, 'value': debt_to_cover})
    weth.approve(lending_pool, debt_to_cover, {'from': liquidator})

    # `liquidationCall()`
    tx_c = lending_pool.liquidationCall(
        terc20,
        weth,
        borrower,
        debt_to_cover,
        False,
        {'from': liquidator}
    )

    # Calculate values
    actual_debt_covered = debt_to_cover * 5 // 10 # max 50% of principal
    collateral_liquidated = percent_mul(actual_debt_covered // price * WEI, weth_bonus)
    bonus_paid = percent_mul(actual_debt_covered, weth_bonus) - actual_debt_covered

    # Check `LendingPool` events
    assert tx_c.events['LiquidationCall']['collateralAsset'] == terc20
    assert tx_c.events['LiquidationCall']['debtAsset'] == weth
    assert tx_c.events['LiquidationCall']['user'] == borrower
    assert tx_c.events['LiquidationCall']['debtToCover'] == actual_debt_covered
    assert tx_c.events['LiquidationCall']['liquidatedCollateralAmount'] == collateral_liquidated
    assert tx_c.events['LiquidationCall']['liquidator'] == liquidator
    assert tx_c.events['LiquidationCall']['receiveAToken'] == False
    # `StableDebtToken.burn()` Transfer
    assert tx_c.events['Transfer'][0]['from'] == borrower
    assert tx_c.events['Transfer'][0]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][0]['value'] == actual_debt_covered
    # `terc20_atoken.burn()` -> `tERC20.transfer()` Transfer
    assert tx_c.events['Transfer'][1]['from'] == terc20_atoken
    assert tx_c.events['Transfer'][1]['to'] == liquidator
    assert tx_c.events['Transfer'][1]['value'] == collateral_liquidated
    # `terc20_atoken.burn()` -> `terc20_atoken.transfer()` Transfer
    assert tx_c.events['Transfer'][2]['from'] == borrower
    assert tx_c.events['Transfer'][2]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][2]['value'] == collateral_liquidated
    # `WETH.safeTransferFrom()` Transfer
    assert tx_c.events['Transfer'][3]['src'] == liquidator
    assert tx_c.events['Transfer'][3]['dst'] == weth_atoken
    assert tx_c.events['Transfer'][3]['wad'] == actual_debt_covered
    # `WETH.StableDebtToken` Burn
    assert tx_c.events['Burn'][0]['user'] == borrower
    assert tx_c.events['Burn'][0]['amount'] == actual_debt_covered
    assert tx_c.events['Burn'][0]['currentBalance'] == borrow_amount
    assert tx_c.events['Burn'][0]['balanceIncrease'] == 0
    assert tx_c.events['Burn'][0]['avgStableRate'] == 0
    assert tx_c.events['Burn'][0]['newTotalSupply'] == borrow_amount - actual_debt_covered
    # `tERC20.AToken` Burn
    assert tx_c.events['Burn'][1]['from'] == borrower
    assert tx_c.events['Burn'][1]['target'] == liquidator
    assert tx_c.events['Burn'][1]['value'] == collateral_liquidated
    assert tx_c.events['Burn'][1]['index'] == RAY

    # Note: due to bug in `StableDebtToken.totalSupply()` when stable rate = 0
    # the event `ReserveDataUpdated` is not accurate.


# Tests `liquidationCall()` with a variable borrow
# principal WETH
# collateral tERC20
def test_liquidation_call_variable():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositor, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, ltv, threshold, bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()`
    borrow_amount = terc20_deposit_amount * price // WEI // 10 # 10% of collateral in ETH
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    liquidity_index = tx.events['ReserveDataUpdated']['liquidityIndex']
    liquidity_rate = tx.events['ReserveDataUpdated']['liquidityRate']
    variable_borrow_index = tx.events['ReserveDataUpdated']['variableBorrowIndex']
    variable_rate = tx.events['ReserveDataUpdated']['variableBorrowRate']

    ### Liquidation Call ###

    # Drop price for tERC20 to make position unhealthy
    price = price // 8
    tx_b = price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    liquidator = accounts[6]
    debt_to_cover = 1_000_000 # less than total debt
    weth.deposit({'from': liquidator, 'value': debt_to_cover})
    weth.approve(lending_pool, debt_to_cover, {'from': liquidator})

    # `liquidationCall()`
    web3.manager.request_blocking("evm_increaseTime", 3) # ensure some interest is accrued
    tx_c = lending_pool.liquidationCall(
        terc20,
        weth,
        borrower,
        debt_to_cover,
        False,
        {'from': liquidator}
    )

    # Calculate values
    actual_debt_covered = debt_to_cover
    collateral_liquidated = percent_mul(actual_debt_covered * WEI // price, bonus)
    bonus_paid = percent_mul(actual_debt_covered, bonus) - actual_debt_covered

    # WETH `updateState()`
    time_diff = tx_c.timestamp - tx.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt

    # WETH `updateInterestRates()`
    total_stable_debt = 0 # SDt
    total_variable_debt = ray_mul(borrow_amount, variable_borrow_index) - debt_to_cover # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount + debt_to_cover
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(RAY, 0, RAY, total_stable_debt, True) # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` events
    assert tx_c.events['LiquidationCall']['collateralAsset'] == terc20
    assert tx_c.events['LiquidationCall']['debtAsset'] == weth
    assert tx_c.events['LiquidationCall']['user'] == borrower
    assert tx_c.events['LiquidationCall']['debtToCover'] == actual_debt_covered
    assert tx_c.events['LiquidationCall']['liquidatedCollateralAmount'] == collateral_liquidated
    assert tx_c.events['LiquidationCall']['liquidator'] == liquidator
    assert tx_c.events['LiquidationCall']['receiveAToken'] == False

    assert tx_c.events['ReserveDataUpdated'][0]['reserve'] == weth
    assert tx_c.events['ReserveDataUpdated'][0]['variableBorrowRate'] == variable_rate
    assert tx_c.events['ReserveDataUpdated'][0]['stableBorrowRate'] == stable_rate
    assert tx_c.events['ReserveDataUpdated'][0]['liquidityRate'] == liquidity_rate
    assert tx_c.events['ReserveDataUpdated'][0]['variableBorrowIndex'] == variable_borrow_index
    assert tx_c.events['ReserveDataUpdated'][0]['liquidityIndex'] == liquidity_index

    assert tx_c.events['ReserveDataUpdated'][1]['reserve'] == terc20
    assert tx_c.events['ReserveDataUpdated'][1]['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx_c.events['ReserveDataUpdated'][1]['stableBorrowRate'] == lending_rate_oracle.getMarketBorrowRate(terc20)
    assert tx_c.events['ReserveDataUpdated'][1]['liquidityRate'] == 0
    assert tx_c.events['ReserveDataUpdated'][1]['variableBorrowIndex'] == RAY
    assert tx_c.events['ReserveDataUpdated'][1]['liquidityIndex'] == RAY

    # `VariableDebtToken.burn()` Transfer
    assert tx_c.events['Transfer'][0]['from'] == borrower
    assert tx_c.events['Transfer'][0]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][0]['value'] == actual_debt_covered

    # `terc20_atoken.burn()` -> `tERC20.transfer()` Transfer
    assert tx_c.events['Transfer'][1]['from'] == terc20_atoken
    assert tx_c.events['Transfer'][1]['to'] == liquidator
    assert tx_c.events['Transfer'][1]['value'] == collateral_liquidated

    # `terc20_atoken.burn()` -> `terc20_atoken.transfer()` Transfer
    assert tx_c.events['Transfer'][2]['from'] == borrower
    assert tx_c.events['Transfer'][2]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][2]['value'] == collateral_liquidated

    # `WETH.safeTransferFrom()` Transfer
    assert tx_c.events['Transfer'][3]['src'] == liquidator
    assert tx_c.events['Transfer'][3]['dst'] == weth_atoken
    assert tx_c.events['Transfer'][3]['wad'] == actual_debt_covered

    # `WETH.VariableDebtToken` Burn
    assert tx_c.events['Burn'][0]['user'] == borrower
    assert tx_c.events['Burn'][0]['amount'] == actual_debt_covered
    assert tx_c.events['Burn'][0]['index'] == variable_borrow_index

    # `tERC20.AToken` Burn
    assert tx_c.events['Burn'][1]['from'] == borrower
    assert tx_c.events['Burn'][1]['target'] == liquidator
    assert tx_c.events['Burn'][1]['value'] == collateral_liquidated
    assert tx_c.events['Burn'][1]['index'] == RAY # tERC20 index is 1 since no borrows


# Tests `liquidationCall()` using both stable and variable borrows
# principal WETH
# collateral tERC20
def test_liquidation_call_stable_and_variable():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositor, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, ltv, threshold, bonus,
    terc20_deposit_amount, price) = setup_borrow()


    # `borrow()` stable
    stable_borrow_amount = terc20_deposit_amount * price // WEI // 10 # 10% of collateral in ETH
    tx = lending_pool.borrow(
        weth,
        stable_borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # `borrow()` variable
    variable_borrow_amount = terc20_deposit_amount * price // WEI // 20 # 5% of collateral in ETH
    tx_b = lending_pool.borrow(
        weth,
        variable_borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    liquidity_index = tx_b.events['ReserveDataUpdated']['liquidityIndex']
    liquidity_rate = tx_b.events['ReserveDataUpdated']['liquidityRate']
    variable_borrow_index = tx_b.events['ReserveDataUpdated']['variableBorrowIndex']
    variable_rate = tx_b.events['ReserveDataUpdated']['variableBorrowRate']
    stable_rate = tx_b.events['ReserveDataUpdated']['stableBorrowRate']

    ### Liquidation Call ###

    # Drop price for tERC20 to make position unhealthy
    price = price // 5
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    # Debt to cover is all the variable debt and some of the stable debt and is less than 50% of the principal
    debt_to_cover = (stable_borrow_amount + variable_borrow_amount) // 2
    liquidator = accounts[6]
    weth.deposit({'from': liquidator, 'value': debt_to_cover})
    weth.approve(lending_pool, debt_to_cover, {'from': liquidator})

    # `liquidationCall()`
    web3.manager.request_blocking("evm_increaseTime", 3) # ensure some interest is accrued
    tx_c = lending_pool.liquidationCall(
        terc20,
        weth,
        borrower,
        debt_to_cover,
        False,
        {'from': liquidator}
    )

    # Calculate values
    actual_debt_covered = debt_to_cover
    collateral_liquidated = percent_mul(actual_debt_covered * WEI // price, bonus)
    bonus_paid = percent_mul(actual_debt_covered, bonus) - actual_debt_covered

    # WETH `updateState()`
    time_diff = tx_c.timestamp - tx_b.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt


    # WETH variable debt calculations
    time_diff = tx_c.timestamp - tx_b.timestamp
    curr_user_variable_debt = ray_mul(variable_borrow_amount, variable_borrow_index)
    assert actual_debt_covered > curr_user_variable_debt
    variable_debt_covered = curr_user_variable_debt

    # WETH stable debt calculations
    time_diff = tx_c.timestamp - tx.timestamp
    prev_user_stable_rate = tx.events['Mint']['newRate']
    prev_overall_stable_rate = tx.events['Mint']['avgStableRate']
    prev_total_stable_debt = stable_borrow_amount
    prev_total_stable_debt_with_interest = ray_mul(prev_total_stable_debt, calculate_compound_interest(prev_overall_stable_rate, time_diff)) # Note only one borrow so user rate is overall rate
    prev_user_stable_balance = stable_borrow_amount
    curr_user_stable_balance = ray_mul(prev_user_stable_balance, calculate_compound_interest(prev_user_stable_rate, time_diff))
    stable_debt_covered = actual_debt_covered - variable_debt_covered

    # WETH `updateInterestRates()`
    total_stable_debt = curr_user_stable_balance - stable_debt_covered # SDt
    total_variable_debt = curr_user_variable_debt - variable_debt_covered # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - stable_borrow_amount - variable_borrow_amount + actual_debt_covered
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(prev_overall_stable_rate, prev_total_stable_debt_with_interest, prev_user_stable_rate, stable_debt_covered, False) # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` events
    assert tx_c.events['LiquidationCall']['collateralAsset'] == terc20
    assert tx_c.events['LiquidationCall']['debtAsset'] == weth
    assert tx_c.events['LiquidationCall']['user'] == borrower
    assert tx_c.events['LiquidationCall']['debtToCover'] == actual_debt_covered
    assert tx_c.events['LiquidationCall']['liquidatedCollateralAmount'] == collateral_liquidated
    assert tx_c.events['LiquidationCall']['liquidator'] == liquidator
    assert tx_c.events['LiquidationCall']['receiveAToken'] == False

    assert tx_c.events['ReserveDataUpdated'][0]['reserve'] == weth
    assert tx_c.events['ReserveDataUpdated'][0]['variableBorrowRate'] == variable_rate
    assert tx_c.events['ReserveDataUpdated'][0]['stableBorrowRate'] == stable_rate
    assert tx_c.events['ReserveDataUpdated'][0]['variableBorrowIndex'] == variable_borrow_index
    assert tx_c.events['ReserveDataUpdated'][0]['liquidityIndex'] == liquidity_index
    assert tx_c.events['ReserveDataUpdated'][0]['liquidityRate'] == liquidity_rate

    assert tx_c.events['ReserveDataUpdated'][1]['reserve'] == terc20
    assert tx_c.events['ReserveDataUpdated'][1]['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx_c.events['ReserveDataUpdated'][1]['stableBorrowRate'] == lending_rate_oracle.getMarketBorrowRate(terc20)
    assert tx_c.events['ReserveDataUpdated'][1]['liquidityRate'] == 0
    assert tx_c.events['ReserveDataUpdated'][1]['variableBorrowIndex'] == RAY
    assert tx_c.events['ReserveDataUpdated'][1]['liquidityIndex'] == RAY

    # `VariableDebtToken.burn()` Transfer
    assert tx_c.events['Transfer'][0]['from'] == borrower
    assert tx_c.events['Transfer'][0]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][0]['value'] == variable_debt_covered

    # `StableDebtToken.burn()` Transfer
    assert tx_c.events['Transfer'][1]['from'] == borrower
    assert tx_c.events['Transfer'][1]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][1]['value'] == stable_debt_covered

    # `terc20_atoken.burn()` -> `tERC20.transfer()` Transfer
    assert tx_c.events['Transfer'][2]['from'] == terc20_atoken
    assert tx_c.events['Transfer'][2]['to'] == liquidator
    assert tx_c.events['Transfer'][2]['value'] == collateral_liquidated

    # `terc20_atoken.burn()` -> `terc20_atoken.transfer()` Transfer
    assert tx_c.events['Transfer'][3]['from'] == borrower
    assert tx_c.events['Transfer'][3]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][3]['value'] == collateral_liquidated

    # `WETH.safeTransferFrom()` Transfer
    assert tx_c.events['Transfer'][4]['src'] == liquidator
    assert tx_c.events['Transfer'][4]['dst'] == weth_atoken
    assert tx_c.events['Transfer'][4]['wad'] == actual_debt_covered

    # `WETH.VariableDebtToken` Burn
    assert tx_c.events['Burn'][0]['user'] == borrower
    assert tx_c.events['Burn'][0]['amount'] == variable_debt_covered
    assert tx_c.events['Burn'][0]['index'] == variable_borrow_index

    # `WETH.StableDebtToken` Burn
    assert tx_c.events['Burn'][1]['user'] == borrower
    assert tx_c.events['Burn'][1]['amount'] == stable_debt_covered
    assert tx_c.events['Burn'][1]['currentBalance'] == curr_user_stable_balance
    assert tx_c.events['Burn'][1]['balanceIncrease'] == curr_user_stable_balance - stable_borrow_amount
    assert tx_c.events['Burn'][1]['avgStableRate'] == overall_stable_rate
    assert tx_c.events['Burn'][1]['newTotalSupply'] == total_stable_debt

    # `tERC20.AToken` Burn
    assert tx_c.events['Burn'][2]['from'] == borrower
    assert tx_c.events['Burn'][2]['target'] == liquidator
    assert tx_c.events['Burn'][2]['value'] == collateral_liquidated
    assert tx_c.events['Burn'][2]['index'] == RAY # tERC20 index is 1 since no borrows


# Tests `liquidationCall()` using both stable and variable borrows
# principal WETH
# collateral tERC20
def test_liquidation_call_with_atokens():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositor, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, ltv, threshold, bonus,
    terc20_deposit_amount, price) = setup_borrow()


    # `borrow()` stable
    stable_borrow_amount = terc20_deposit_amount * price // WEI // 10 # 10% of collateral in ETH
    tx = lending_pool.borrow(
        weth,
        stable_borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # `borrow()` variable
    variable_borrow_amount = terc20_deposit_amount * price // WEI // 20 # 5% of collateral in ETH
    tx_b = lending_pool.borrow(
        weth,
        variable_borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    liquidity_index = tx_b.events['ReserveDataUpdated']['liquidityIndex']
    liquidity_rate = tx_b.events['ReserveDataUpdated']['liquidityRate']
    variable_borrow_index = tx_b.events['ReserveDataUpdated']['variableBorrowIndex']
    variable_rate = tx_b.events['ReserveDataUpdated']['variableBorrowRate']
    stable_rate = tx_b.events['ReserveDataUpdated']['stableBorrowRate']

    ### Liquidation Call ###

    # Drop price for tERC20 to make position unhealthy
    price = price // 5
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    # Debt to cover is all the variable debt and some of the stable debt and is less than 50% of the principal
    debt_to_cover = (stable_borrow_amount + variable_borrow_amount) // 2
    liquidator = accounts[6]
    weth.deposit({'from': liquidator, 'value': debt_to_cover})
    weth.approve(lending_pool, debt_to_cover, {'from': liquidator})

    # `liquidationCall()` receiving aTokens
    web3.manager.request_blocking("evm_increaseTime", 3) # ensure some interest is accrued
    tx_c = lending_pool.liquidationCall(
        terc20,
        weth,
        borrower,
        debt_to_cover,
        True,
        {'from': liquidator}
    )

    # Calculate values
    actual_debt_covered = debt_to_cover
    collateral_liquidated = percent_mul(actual_debt_covered * WEI // price, bonus)
    bonus_paid = percent_mul(actual_debt_covered, bonus) - actual_debt_covered

    # WETH `updateState()`
    time_diff = tx_c.timestamp - tx_b.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt


    # WETH variable debt calculations
    time_diff = tx_c.timestamp - tx_b.timestamp
    curr_user_variable_debt = ray_mul(variable_borrow_amount, variable_borrow_index)
    assert actual_debt_covered > curr_user_variable_debt
    variable_debt_covered = curr_user_variable_debt

    # WETH stable debt calculations
    time_diff = tx_c.timestamp - tx.timestamp
    prev_user_stable_rate = tx.events['Mint']['newRate']
    prev_overall_stable_rate = tx.events['Mint']['avgStableRate']
    prev_total_stable_debt = stable_borrow_amount
    prev_total_stable_debt_with_interest = ray_mul(prev_total_stable_debt, calculate_compound_interest(prev_overall_stable_rate, time_diff)) # Note only one borrow so user rate is overall rate
    prev_user_stable_balance = stable_borrow_amount
    curr_user_stable_balance = ray_mul(prev_user_stable_balance, calculate_compound_interest(prev_user_stable_rate, time_diff))
    stable_debt_covered = actual_debt_covered - variable_debt_covered

    # WETH `updateInterestRates()`
    total_stable_debt = curr_user_stable_balance - stable_debt_covered # SDt
    total_variable_debt = curr_user_variable_debt - variable_debt_covered # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - stable_borrow_amount - variable_borrow_amount + actual_debt_covered
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(prev_overall_stable_rate, prev_total_stable_debt_with_interest, prev_user_stable_rate, stable_debt_covered, False) # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` events
    assert tx_c.events['LiquidationCall']['collateralAsset'] == terc20
    assert tx_c.events['LiquidationCall']['debtAsset'] == weth
    assert tx_c.events['LiquidationCall']['user'] == borrower
    assert tx_c.events['LiquidationCall']['debtToCover'] == actual_debt_covered
    assert tx_c.events['LiquidationCall']['liquidatedCollateralAmount'] == collateral_liquidated
    assert tx_c.events['LiquidationCall']['liquidator'] == liquidator
    assert tx_c.events['LiquidationCall']['receiveAToken'] == True

    assert tx_c.events['ReserveDataUpdated'][0]['reserve'] == weth
    assert tx_c.events['ReserveDataUpdated'][0]['variableBorrowRate'] == variable_rate
    assert tx_c.events['ReserveDataUpdated'][0]['stableBorrowRate'] == stable_rate
    assert tx_c.events['ReserveDataUpdated'][0]['variableBorrowIndex'] == variable_borrow_index
    assert tx_c.events['ReserveDataUpdated'][0]['liquidityIndex'] == liquidity_index
    assert tx_c.events['ReserveDataUpdated'][0]['liquidityRate'] == liquidity_rate

    # `VariableDebtToken.burn()` Transfer
    assert tx_c.events['Transfer'][0]['from'] == borrower
    assert tx_c.events['Transfer'][0]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][0]['value'] == variable_debt_covered

    # `StableDebtToken.burn()` Transfer
    assert tx_c.events['Transfer'][1]['from'] == borrower
    assert tx_c.events['Transfer'][1]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][1]['value'] == stable_debt_covered

    # `terc20_atoken.transfer()` Transfer
    assert tx_c.events['Transfer'][2]['from'] == borrower
    assert tx_c.events['Transfer'][2]['to'] == liquidator
    assert tx_c.events['Transfer'][2]['value'] == collateral_liquidated
    assert tx_c.events['BalanceTransfer']['from'] == borrower
    assert tx_c.events['BalanceTransfer']['to'] == liquidator
    assert tx_c.events['BalanceTransfer']['value'] == collateral_liquidated

    # `WETH.safeTransferFrom()` Transfer
    assert tx_c.events['Transfer'][3]['src'] == liquidator
    assert tx_c.events['Transfer'][3]['dst'] == weth_atoken
    assert tx_c.events['Transfer'][3]['wad'] == actual_debt_covered

    # `WETH.VariableDebtToken` Burn
    assert tx_c.events['Burn'][0]['user'] == borrower
    assert tx_c.events['Burn'][0]['amount'] == variable_debt_covered
    assert tx_c.events['Burn'][0]['index'] == variable_borrow_index

    # `WETH.StableDebtToken` Burn
    assert tx_c.events['Burn'][1]['user'] == borrower
    assert tx_c.events['Burn'][1]['amount'] == stable_debt_covered
    assert tx_c.events['Burn'][1]['currentBalance'] == curr_user_stable_balance
    assert tx_c.events['Burn'][1]['balanceIncrease'] == curr_user_stable_balance - stable_borrow_amount
    assert tx_c.events['Burn'][1]['avgStableRate'] == overall_stable_rate
    assert tx_c.events['Burn'][1]['newTotalSupply'] == total_stable_debt


# Tests `liquidationCall()` maxing out collateral
# principal WETH
# collateral tERC20
def test_liquidation_call_max_collateral():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositor, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, ltv, threshold, bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()`
    borrow_amount = terc20_deposit_amount * price // WEI // 10 # 10% of collateral in ETH
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    liquidity_index = tx.events['ReserveDataUpdated']['liquidityIndex']
    liquidity_rate = tx.events['ReserveDataUpdated']['liquidityRate']
    variable_borrow_index = tx.events['ReserveDataUpdated']['variableBorrowIndex']
    variable_rate = tx.events['ReserveDataUpdated']['variableBorrowRate']

    ### Liquidation Call ###

    # Drop price for tERC20 such that we have 10:1 debt:collateral
    price = price // 1000
    tx_b = price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    liquidator = accounts[6]
    debt_to_cover = borrow_amount
    weth.deposit({'from': liquidator, 'value': debt_to_cover})
    weth.approve(lending_pool, debt_to_cover, {'from': liquidator})

    # `liquidationCall()`
    web3.manager.request_blocking("evm_increaseTime", 4) # ensure some interest is accrued
    tx_c = lending_pool.liquidationCall(
        terc20,
        weth,
        borrower,
        debt_to_cover,
        False,
        {'from': liquidator}
    )

    # Calculate values
    actual_debt_covered = percent_div(terc20_deposit_amount * price // WEI, bonus)
    collateral_liquidated = terc20_deposit_amount
    bonus_paid = percent_mul(actual_debt_covered, bonus) - actual_debt_covered

    # WETH `updateState()`
    time_diff = tx_c.timestamp - tx.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt

    # WETH `updateInterestRates()`
    total_stable_debt = 0 # SDt
    total_variable_debt = ray_mul(borrow_amount, variable_borrow_index) - actual_debt_covered # VDt
    assert weth_variable_debt.totalSupply() == total_variable_debt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount + actual_debt_covered
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(RAY, 0, RAY, total_stable_debt, True) # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` events
    assert tx_c.events['LiquidationCall']['collateralAsset'] == terc20
    assert tx_c.events['LiquidationCall']['debtAsset'] == weth
    assert tx_c.events['LiquidationCall']['user'] == borrower
    assert tx_c.events['LiquidationCall']['debtToCover'] == actual_debt_covered
    assert tx_c.events['LiquidationCall']['liquidatedCollateralAmount'] == collateral_liquidated
    assert tx_c.events['LiquidationCall']['liquidator'] == liquidator
    assert tx_c.events['LiquidationCall']['receiveAToken'] == False

    assert tx_c.events['ReserveDataUpdated'][0]['reserve'] == weth
    assert tx_c.events['ReserveDataUpdated'][0]['variableBorrowRate'] == variable_rate
    assert tx_c.events['ReserveDataUpdated'][0]['stableBorrowRate'] == stable_rate
    assert tx_c.events['ReserveDataUpdated'][0]['liquidityRate'] == liquidity_rate
    assert tx_c.events['ReserveDataUpdated'][0]['variableBorrowIndex'] == variable_borrow_index
    assert tx_c.events['ReserveDataUpdated'][0]['liquidityIndex'] == liquidity_index

    assert tx_c.events['ReserveDataUpdated'][1]['reserve'] == terc20
    assert tx_c.events['ReserveDataUpdated'][1]['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx_c.events['ReserveDataUpdated'][1]['stableBorrowRate'] == lending_rate_oracle.getMarketBorrowRate(terc20)
    assert tx_c.events['ReserveDataUpdated'][1]['liquidityRate'] == 0
    assert tx_c.events['ReserveDataUpdated'][1]['variableBorrowIndex'] == RAY
    assert tx_c.events['ReserveDataUpdated'][1]['liquidityIndex'] == RAY

    # `VariableDebtToken.burn()` Transfer
    assert tx_c.events['Transfer'][0]['from'] == borrower
    assert tx_c.events['Transfer'][0]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][0]['value'] == actual_debt_covered

    # `terc20_atoken.burn()` -> `tERC20.transfer()` Transfer
    assert tx_c.events['Transfer'][1]['from'] == terc20_atoken
    assert tx_c.events['Transfer'][1]['to'] == liquidator
    assert tx_c.events['Transfer'][1]['value'] == collateral_liquidated

    # `terc20_atoken.burn()` -> `terc20_atoken.transfer()` Transfer
    assert tx_c.events['Transfer'][2]['from'] == borrower
    assert tx_c.events['Transfer'][2]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][2]['value'] == collateral_liquidated

    # `WETH.safeTransferFrom()` Transfer
    assert tx_c.events['Transfer'][3]['src'] == liquidator
    assert tx_c.events['Transfer'][3]['dst'] == weth_atoken
    assert tx_c.events['Transfer'][3]['wad'] == actual_debt_covered

    # `WETH.VariableDebtToken` Burn
    assert tx_c.events['Burn'][0]['user'] == borrower
    assert tx_c.events['Burn'][0]['amount'] == actual_debt_covered
    assert tx_c.events['Burn'][0]['index'] == variable_borrow_index

    # `tERC20.AToken` Burn
    assert tx_c.events['Burn'][1]['from'] == borrower
    assert tx_c.events['Burn'][1]['target'] == liquidator
    assert tx_c.events['Burn'][1]['value'] == collateral_liquidated
    assert tx_c.events['Burn'][1]['index'] == RAY # tERC20 index is 1 since no borrows


# Tests `liquidationCall()` ourself
# principal WETH
# collateral tERC20
def test_liquidation_call_self():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositor, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, ltv, threshold, bonus,
    terc20_deposit_amount, price) = setup_borrow()


    # `borrow()` stable
    stable_borrow_amount = terc20_deposit_amount * price // WEI // 10 # 10% of collateral in ETH
    tx = lending_pool.borrow(
        weth,
        stable_borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # `borrow()` variable
    variable_borrow_amount = terc20_deposit_amount * price // WEI // 20 # 5% of collateral in ETH
    tx_b = lending_pool.borrow(
        weth,
        variable_borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    liquidity_index = tx_b.events['ReserveDataUpdated']['liquidityIndex']
    liquidity_rate = tx_b.events['ReserveDataUpdated']['liquidityRate']
    variable_borrow_index = tx_b.events['ReserveDataUpdated']['variableBorrowIndex']
    variable_rate = tx_b.events['ReserveDataUpdated']['variableBorrowRate']
    stable_rate = tx_b.events['ReserveDataUpdated']['stableBorrowRate']

    ### Liquidation Call ###

    # Drop price for tERC20 to make position unhealthy
    price = price // 5
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    # Debt to cover is all the variable debt and some of the stable debt and is less than 50% of the principal
    debt_to_cover = (stable_borrow_amount + variable_borrow_amount) // 2
    liquidator = borrower # set this to ourself
    weth.deposit({'from': liquidator, 'value': debt_to_cover})
    weth.approve(lending_pool, debt_to_cover, {'from': liquidator})

    # `liquidationCall()`
    web3.manager.request_blocking("evm_increaseTime", 3) # ensure some interest is accrued
    tx_c = lending_pool.liquidationCall(
        terc20,
        weth,
        borrower,
        debt_to_cover,
        False,
        {'from': liquidator}
    )

    # Calculate values
    actual_debt_covered = debt_to_cover
    collateral_liquidated = percent_mul(actual_debt_covered * WEI // price, bonus)
    bonus_paid = percent_mul(actual_debt_covered, bonus) - actual_debt_covered

    # WETH `updateState()`
    time_diff = tx_c.timestamp - tx_b.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt


    # WETH variable debt calculations
    time_diff = tx_c.timestamp - tx_b.timestamp
    curr_user_variable_debt = ray_mul(variable_borrow_amount, variable_borrow_index)
    assert actual_debt_covered > curr_user_variable_debt
    variable_debt_covered = curr_user_variable_debt

    # WETH stable debt calculations
    time_diff = tx_c.timestamp - tx.timestamp
    prev_user_stable_rate = tx.events['Mint']['newRate']
    prev_overall_stable_rate = tx.events['Mint']['avgStableRate']
    prev_total_stable_debt = stable_borrow_amount
    prev_total_stable_debt_with_interest = ray_mul(prev_total_stable_debt, calculate_compound_interest(prev_overall_stable_rate, time_diff)) # Note only one borrow so user rate is overall rate
    prev_user_stable_balance = stable_borrow_amount
    curr_user_stable_balance = ray_mul(prev_user_stable_balance, calculate_compound_interest(prev_user_stable_rate, time_diff))
    stable_debt_covered = actual_debt_covered - variable_debt_covered

    # WETH `updateInterestRates()`
    total_stable_debt = curr_user_stable_balance - stable_debt_covered # SDt
    total_variable_debt = curr_user_variable_debt - variable_debt_covered # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - stable_borrow_amount - variable_borrow_amount + actual_debt_covered
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = calculate_overall_stable_rate(prev_overall_stable_rate, prev_total_stable_debt_with_interest, prev_user_stable_rate, stable_debt_covered, False) # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` events
    assert tx_c.events['LiquidationCall']['collateralAsset'] == terc20
    assert tx_c.events['LiquidationCall']['debtAsset'] == weth
    assert tx_c.events['LiquidationCall']['user'] == borrower
    assert tx_c.events['LiquidationCall']['debtToCover'] == actual_debt_covered
    assert tx_c.events['LiquidationCall']['liquidatedCollateralAmount'] == collateral_liquidated
    assert tx_c.events['LiquidationCall']['liquidator'] == liquidator
    assert tx_c.events['LiquidationCall']['receiveAToken'] == False

    assert tx_c.events['ReserveDataUpdated'][0]['reserve'] == weth
    assert tx_c.events['ReserveDataUpdated'][0]['variableBorrowRate'] == variable_rate
    assert tx_c.events['ReserveDataUpdated'][0]['stableBorrowRate'] == stable_rate
    assert tx_c.events['ReserveDataUpdated'][0]['variableBorrowIndex'] == variable_borrow_index
    assert tx_c.events['ReserveDataUpdated'][0]['liquidityIndex'] == liquidity_index
    assert tx_c.events['ReserveDataUpdated'][0]['liquidityRate'] == liquidity_rate

    assert tx_c.events['ReserveDataUpdated'][1]['reserve'] == terc20
    assert tx_c.events['ReserveDataUpdated'][1]['variableBorrowRate'] == strategy.baseVariableBorrowRate()
    assert tx_c.events['ReserveDataUpdated'][1]['stableBorrowRate'] == lending_rate_oracle.getMarketBorrowRate(terc20)
    assert tx_c.events['ReserveDataUpdated'][1]['liquidityRate'] == 0
    assert tx_c.events['ReserveDataUpdated'][1]['variableBorrowIndex'] == RAY
    assert tx_c.events['ReserveDataUpdated'][1]['liquidityIndex'] == RAY

    # `VariableDebtToken.burn()` Transfer
    assert tx_c.events['Transfer'][0]['from'] == borrower
    assert tx_c.events['Transfer'][0]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][0]['value'] == variable_debt_covered

    # `StableDebtToken.burn()` Transfer
    assert tx_c.events['Transfer'][1]['from'] == borrower
    assert tx_c.events['Transfer'][1]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][1]['value'] == stable_debt_covered

    # `terc20_atoken.burn()` -> `tERC20.transfer()` Transfer
    assert tx_c.events['Transfer'][2]['from'] == terc20_atoken
    assert tx_c.events['Transfer'][2]['to'] == liquidator
    assert tx_c.events['Transfer'][2]['value'] == collateral_liquidated

    # `terc20_atoken.burn()` -> `terc20_atoken.transfer()` Transfer
    assert tx_c.events['Transfer'][3]['from'] == borrower
    assert tx_c.events['Transfer'][3]['to'] == ZERO_ADDRESS
    assert tx_c.events['Transfer'][3]['value'] == collateral_liquidated

    # `WETH.safeTransferFrom()` Transfer
    assert tx_c.events['Transfer'][4]['src'] == liquidator
    assert tx_c.events['Transfer'][4]['dst'] == weth_atoken
    assert tx_c.events['Transfer'][4]['wad'] == actual_debt_covered

    # `WETH.VariableDebtToken` Burn
    assert tx_c.events['Burn'][0]['user'] == borrower
    assert tx_c.events['Burn'][0]['amount'] == variable_debt_covered
    assert tx_c.events['Burn'][0]['index'] == variable_borrow_index

    # `WETH.StableDebtToken` Burn
    assert tx_c.events['Burn'][1]['user'] == borrower
    assert tx_c.events['Burn'][1]['amount'] == stable_debt_covered
    assert tx_c.events['Burn'][1]['currentBalance'] == curr_user_stable_balance
    assert tx_c.events['Burn'][1]['balanceIncrease'] == curr_user_stable_balance - stable_borrow_amount
    assert tx_c.events['Burn'][1]['avgStableRate'] == overall_stable_rate
    assert tx_c.events['Burn'][1]['newTotalSupply'] == total_stable_debt

    # `tERC20.AToken` Burn
    assert tx_c.events['Burn'][2]['from'] == borrower
    assert tx_c.events['Burn'][2]['target'] == liquidator
    assert tx_c.events['Burn'][2]['value'] == collateral_liquidated
    assert tx_c.events['Burn'][2]['index'] == RAY


#############
# flashLoan()
#############


# Test `flashLoan()`
@pytest.mark.xfail(reason='Available liquidity incorrectly calculated')
def test_flash_loan():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositor, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, ltv, threshold, bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()` such that we will have interesting calculations
    borrow_amount = terc20_deposit_amount * price // WEI // 10 # 10% of collateral in ETH
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Store previous state for calculations
    liquidity_index = tx.events['ReserveDataUpdated']['liquidityIndex']
    liquidity_rate = tx.events['ReserveDataUpdated']['liquidityRate']
    variable_borrow_index = tx.events['ReserveDataUpdated']['variableBorrowIndex']
    variable_rate = tx.events['ReserveDataUpdated']['variableBorrowRate']

    # Contract which will `executeOperations()` in the flash loan
    receiver = accounts[6].deploy(FlashLoanTests, lending_pool)

    # transfer sufficient WETH funds to repay premium
    weth.deposit({'from':accounts[0], 'value': deposit_amount})
    weth.transfer(receiver, deposit_amount, {'from': accounts[0]})

    # `flashLoan()`
    web3.manager.request_blocking("evm_increaseTime", 7) # ensure some interest is accrued
    flash_amount = weth.balanceOf(weth_atoken)
    tx_b = lending_pool.flashLoan(
        receiver,
        [weth],
        [flash_amount],
        [INTEREST_RATE_MODE_NONE],
        accounts[6],
        b'',
        0,
        {'from': accounts[6]}
    )

    # WETH `updateState()`
    time_diff = tx_b.timestamp - tx.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt

    # WETH `cumulateToLiquidityIndex()``
    premium = flash_amount * 9 // 10_000
    total_liquidity = ray_mul(deposit_amount, liquidity_index)
    liquidity_index = ray_mul(ray_div(wad_to_ray(premium), wad_to_ray(total_liquidity)) + RAY, liquidity_index)

    # WETH `updateInterestRates()`
    total_stable_debt = 0 # SDt
    total_variable_debt = ray_mul(borrow_amount, variable_borrow_index) # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount + premium
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = 0 # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `LendingPool` logs
    assert tx_b.events['FlashLoan']['target'] == receiver
    assert tx_b.events['FlashLoan']['initiator'] == accounts[6]
    assert tx_b.events['FlashLoan']['asset'] == weth
    assert tx_b.events['FlashLoan']['amount'] == flash_amount
    assert tx_b.events['FlashLoan']['premium'] == premium
    assert tx_b.events['FlashLoan']['referralCode'] == 0
    assert tx_b.events['ReserveDataUpdated']['reserve'] == weth
    assert tx_b.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx_b.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx_b.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx_b.events['ReserveDataUpdated']['variableBorrowIndex'] == variable_borrow_index
    assert tx_b.events['ReserveDataUpdated']['liquidityIndex'] == liquidity_index


# Test `flashLoan()` with variable borrow
def test_flash_loan_variable():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositor, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, ltv, threshold, bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()` such that we will have interesting calculations
    borrow_amount = terc20_deposit_amount * price // WEI // 5 # 5% of collateral in ETH
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Store previous state for calculations
    liquidity_index = tx.events['ReserveDataUpdated']['liquidityIndex']
    liquidity_rate = tx.events['ReserveDataUpdated']['liquidityRate']
    variable_borrow_index = tx.events['ReserveDataUpdated']['variableBorrowIndex']
    variable_rate = tx.events['ReserveDataUpdated']['variableBorrowRate']

    # Contract which will `executeOperations()` in the flash loan
    receiver = accounts[0].deploy(FlashLoanTests, lending_pool)

    # Give flash loaner collateral to borrow
    flash_loaner = accounts[6]
    flash_collateral_amount = deposit_amount // 20
    terc20.mint(flash_collateral_amount, {'from': flash_loaner})
    terc20.approve(lending_pool.address, flash_collateral_amount, {'from': flash_loaner})
    lending_pool.deposit(terc20.address, flash_collateral_amount, flash_loaner, 0, {'from': flash_loaner})

    # `flashLoan()`
    web3.manager.request_blocking("evm_increaseTime", 5) # ensure some interest is accrued
    flash_amount = flash_collateral_amount * price // WEI // 5 # 5% of collateral in ETH
    tx_b = lending_pool.flashLoan(
        receiver,
        [weth],
        [flash_amount],
        [INTEREST_RATE_MODE_VARIABLE],
        flash_loaner,
        b'',
        0,
        {'from': flash_loaner}
    )

    # WETH `updateState()`
    time_diff = tx_b.timestamp - tx.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt

    user_scaled_balance = ray_div(flash_amount, variable_borrow_index)
    total_scaled_debt = borrow_amount + user_scaled_balance

    # WETH `updateInterestRates()`
    total_stable_debt = 0 # SDt
    total_variable_debt = ray_mul(total_scaled_debt, variable_borrow_index) # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount - flash_amount
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = 0 # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `WETH` logs
    assert tx_b.events['Transfer'][0]['src'] == weth_atoken
    assert tx_b.events['Transfer'][0]['dst'] == receiver
    assert tx_b.events['Transfer'][0]['wad'] == flash_amount

    # Check `LendingPool` logs
    assert tx_b.events['FlashLoan']['target'] == receiver
    assert tx_b.events['FlashLoan']['initiator'] == accounts[6]
    assert tx_b.events['FlashLoan']['asset'] == weth
    assert tx_b.events['FlashLoan']['amount'] == flash_amount
    assert tx_b.events['FlashLoan']['premium'] == flash_amount * 9 // 10000
    assert tx_b.events['FlashLoan']['referralCode'] == 0
    assert tx_b.events['ReserveDataUpdated']['reserve'] == weth
    assert tx_b.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx_b.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx_b.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx_b.events['ReserveDataUpdated']['variableBorrowIndex'] == variable_borrow_index
    assert tx_b.events['ReserveDataUpdated']['liquidityIndex'] == liquidity_index
    assert tx_b.events['Borrow']['reserve'] == weth
    assert tx_b.events['Borrow']['user'] == flash_loaner
    assert tx_b.events['Borrow']['onBehalfOf'] == flash_loaner
    assert tx_b.events['Borrow']['amount'] == flash_amount
    assert tx_b.events['Borrow']['borrowRateMode'] == INTEREST_RATE_MODE_VARIABLE
    assert tx_b.events['Borrow']['borrowRate'] == variable_rate
    assert tx_b.events['Borrow']['referral'] == 0

    # Check `VariableDebtToken` logs
    assert tx_b.events['Mint']['from'] == flash_loaner
    assert tx_b.events['Mint']['onBehalfOf'] == flash_loaner
    assert tx_b.events['Mint']['value'] == flash_amount
    assert tx_b.events['Mint']['index'] == variable_borrow_index
    assert tx_b.events['Transfer'][1]['to'] == flash_loaner
    assert tx_b.events['Transfer'][1]['from'] == ZERO_ADDRESS
    assert tx_b.events['Transfer'][1]['value'] == flash_amount


# Test `flashLoan()` with stable borrow
def test_flash_loan_stable():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositor, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, ltv, threshold, bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()` such that we will have interesting calculations
    borrow_amount = terc20_deposit_amount * price // WEI // 5 # 5% of collateral in ETH
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Store previous state for calculations
    liquidity_index = tx.events['ReserveDataUpdated']['liquidityIndex']
    liquidity_rate = tx.events['ReserveDataUpdated']['liquidityRate']
    variable_borrow_index = tx.events['ReserveDataUpdated']['variableBorrowIndex']
    variable_rate = tx.events['ReserveDataUpdated']['variableBorrowRate']
    prev_stable_rate = tx.events['ReserveDataUpdated']['stableBorrowRate']

    # Contract which will `executeOperations()` in the flash loan
    receiver = accounts[0].deploy(FlashLoanTests, lending_pool)

    # Give flash loaner collateral to borrow
    flash_loaner = accounts[6]
    flash_collateral_amount = deposit_amount // 20
    terc20.mint(flash_collateral_amount, {'from': flash_loaner})
    terc20.approve(lending_pool.address, flash_collateral_amount, {'from': flash_loaner})
    lending_pool.deposit(terc20.address, flash_collateral_amount, flash_loaner, 0, {'from': flash_loaner})

    # `flashLoan()`
    web3.manager.request_blocking("evm_increaseTime", 5) # ensure some interest is accrued
    flash_amount = flash_collateral_amount * price // WEI // 20 # 5% of collateral in ETH
    tx_b = lending_pool.flashLoan(
        receiver,
        [weth],
        [flash_amount],
        [INTEREST_RATE_MODE_STABLE],
        flash_loaner,
        b'',
        0,
        {'from': flash_loaner}
    )

    # WETH `updateState()`
    time_diff = tx_b.timestamp - tx.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt

    # WETH `updateInterestRates()`
    total_stable_debt = flash_amount # SDt
    total_variable_debt = ray_mul(borrow_amount, variable_borrow_index) # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount - flash_amount
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = prev_stable_rate # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `WETH` logs
    assert tx_b.events['Transfer'][0]['src'] == weth_atoken
    assert tx_b.events['Transfer'][0]['dst'] == receiver
    assert tx_b.events['Transfer'][0]['wad'] == flash_amount

    # Check `LendingPool` logs
    assert tx_b.events['FlashLoan']['target'] == receiver
    assert tx_b.events['FlashLoan']['initiator'] == accounts[6]
    assert tx_b.events['FlashLoan']['asset'] == weth
    assert tx_b.events['FlashLoan']['amount'] == flash_amount
    assert tx_b.events['FlashLoan']['premium'] == flash_amount * 9 // 10000
    assert tx_b.events['FlashLoan']['referralCode'] == 0
    assert tx_b.events['ReserveDataUpdated']['reserve'] == weth
    assert tx_b.events['ReserveDataUpdated']['variableBorrowRate'] == variable_rate
    assert tx_b.events['ReserveDataUpdated']['stableBorrowRate'] == stable_rate
    assert tx_b.events['ReserveDataUpdated']['liquidityRate'] == liquidity_rate
    assert tx_b.events['ReserveDataUpdated']['variableBorrowIndex'] == variable_borrow_index
    assert tx_b.events['ReserveDataUpdated']['liquidityIndex'] == liquidity_index
    assert tx_b.events['Borrow']['reserve'] == weth
    assert tx_b.events['Borrow']['user'] == flash_loaner
    assert tx_b.events['Borrow']['onBehalfOf'] == flash_loaner
    assert tx_b.events['Borrow']['amount'] == flash_amount
    assert tx_b.events['Borrow']['borrowRateMode'] == INTEREST_RATE_MODE_STABLE
    assert tx_b.events['Borrow']['borrowRate'] == prev_stable_rate
    assert tx_b.events['Borrow']['referral'] == 0

    # Check `StableDebtToken` logs
    assert tx_b.events['Mint']['user'] == flash_loaner
    assert tx_b.events['Mint']['onBehalfOf'] == flash_loaner
    assert tx_b.events['Mint']['amount'] == flash_amount
    assert tx_b.events['Mint']['currentBalance'] == 0
    assert tx_b.events['Mint']['balanceIncrease'] == 0
    assert tx_b.events['Mint']['newRate'] == prev_stable_rate
    assert tx_b.events['Mint']['avgStableRate'] == overall_stable_rate
    assert tx_b.events['Mint']['newTotalSupply'] == total_stable_debt
    assert tx_b.events['Transfer'][1]['to'] == flash_loaner
    assert tx_b.events['Transfer'][1]['from'] == ZERO_ADDRESS
    assert tx_b.events['Transfer'][1]['value'] == flash_amount


# Test `flashLoan()` multiple flash loans
def test_flash_loan_multiple():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositor, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, ltv, threshold, bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()` such that we will have interesting calculations
    borrow_amount = terc20_deposit_amount * price // WEI // 5 # 20% of collateral in ETH
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Store previous state for calculations
    liquidity_index = tx.events['ReserveDataUpdated']['liquidityIndex']
    liquidity_rate = tx.events['ReserveDataUpdated']['liquidityRate']
    variable_borrow_index = tx.events['ReserveDataUpdated']['variableBorrowIndex']
    variable_rate = tx.events['ReserveDataUpdated']['variableBorrowRate']
    prev_stable_rate = tx.events['ReserveDataUpdated']['stableBorrowRate']

    # Contract which will `executeOperations()` in the flash loan
    receiver = accounts[0].deploy(FlashLoanTests, lending_pool)

    # Give flash loaner collateral to borrow
    flash_loaner = accounts[6]
    flash_collateral_amount = deposit_amount // 20
    terc20.mint(deposit_amount, {'from': flash_loaner})
    terc20.approve(lending_pool.address, flash_collateral_amount, {'from': flash_loaner})
    lending_pool.deposit(terc20.address, flash_collateral_amount, flash_loaner, 0, {'from': flash_loaner})

    # Give receiver enough balance to cover premium
    terc20.transfer(receiver, deposit_amount // 2, {'from': flash_loaner})

    # `flashLoan()`
    # 1: WETH, INTEREST_RATE_MODE_STABLE
    # 2: WETH, INTEREST_RATE_MODE_VARIABLE
    # 3: tERC20, INTEREST_RATE_MODE_NONE
    web3.manager.request_blocking("evm_increaseTime", 5) # ensure some interest is accrued
    flash_amounts = [flash_collateral_amount * price // WEI // 10, flash_collateral_amount * price // WEI // 5, terc20_deposit_amount]
    tx_b = lending_pool.flashLoan(
        receiver,
        [weth, weth, terc20],
        flash_amounts,
        [INTEREST_RATE_MODE_STABLE, INTEREST_RATE_MODE_VARIABLE, INTEREST_RATE_MODE_NONE],
        flash_loaner,
        b'',
        0,
        {'from': flash_loaner}
    )

    ### Flash Loan 1

    # WETH `updateState()`
    time_diff = tx_b.timestamp - tx.timestamp
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt

    # WETH `updateInterestRates()`
    total_stable_debt = flash_amounts[0] # SDt
    total_variable_debt = ray_mul(borrow_amount, variable_borrow_index) # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount - flash_amounts[0] - flash_amounts[1]
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = prev_stable_rate # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `WETH` logs
    assert tx_b.events['Transfer'][0]['src'] == weth_atoken
    assert tx_b.events['Transfer'][0]['dst'] == receiver
    assert tx_b.events['Transfer'][0]['wad'] == flash_amounts[0]

    # Check `LendingPool` logs
    assert tx_b.events['FlashLoan'][0]['target'] == receiver
    assert tx_b.events['FlashLoan'][0]['initiator'] == flash_loaner
    assert tx_b.events['FlashLoan'][0]['asset'] == weth
    assert tx_b.events['FlashLoan'][0]['amount'] == flash_amounts[0]
    assert tx_b.events['FlashLoan'][0]['premium'] == flash_amounts[0] * 9 // 10000
    assert tx_b.events['FlashLoan'][0]['referralCode'] == 0
    assert tx_b.events['ReserveDataUpdated'][0]['reserve'] == weth
    assert tx_b.events['ReserveDataUpdated'][0]['variableBorrowRate'] == variable_rate
    assert tx_b.events['ReserveDataUpdated'][0]['stableBorrowRate'] == stable_rate
    assert tx_b.events['ReserveDataUpdated'][0]['liquidityRate'] == liquidity_rate
    assert tx_b.events['ReserveDataUpdated'][0]['variableBorrowIndex'] == variable_borrow_index
    assert tx_b.events['ReserveDataUpdated'][0]['liquidityIndex'] == liquidity_index
    assert tx_b.events['Borrow'][0]['reserve'] == weth
    assert tx_b.events['Borrow'][0]['user'] == flash_loaner
    assert tx_b.events['Borrow'][0]['onBehalfOf'] == flash_loaner
    assert tx_b.events['Borrow'][0]['amount'] == flash_amounts[0]
    assert tx_b.events['Borrow'][0]['borrowRateMode'] == INTEREST_RATE_MODE_STABLE
    assert tx_b.events['Borrow'][0]['borrowRate'] == prev_stable_rate
    assert tx_b.events['Borrow'][0]['referral'] == 0

    # Check `StableDebtToken` logs
    assert tx_b.events['Mint'][0]['user'] == flash_loaner
    assert tx_b.events['Mint'][0]['onBehalfOf'] == flash_loaner
    assert tx_b.events['Mint'][0]['amount'] == flash_amounts[0]
    assert tx_b.events['Mint'][0]['currentBalance'] == 0
    assert tx_b.events['Mint'][0]['balanceIncrease'] == 0
    assert tx_b.events['Mint'][0]['newRate'] == prev_stable_rate
    assert tx_b.events['Mint'][0]['avgStableRate'] == overall_stable_rate
    assert tx_b.events['Mint'][0]['newTotalSupply'] == total_stable_debt
    assert tx_b.events['Transfer'][3]['to'] == flash_loaner
    assert tx_b.events['Transfer'][3]['from'] == ZERO_ADDRESS
    assert tx_b.events['Transfer'][3]['value'] == flash_amounts[0]

    ### Flash Loan 2

    # WETH `updateState()`
    time_diff = 0
    liquidity_index = ray_mul(calculate_linear_interest(liquidity_rate, time_diff), liquidity_index) # LIt
    variable_borrow_index = ray_mul(calculate_compound_interest(variable_rate, time_diff), variable_borrow_index) # VIt

    prev_stable_rate = stable_rate
    user_scaled_balance = ray_div(flash_amounts[1], variable_borrow_index)
    total_scaled_debt = borrow_amount + user_scaled_balance

    # WETH `updateInterestRates()`
    total_stable_debt = flash_amounts[0] # SDt
    total_variable_debt = ray_mul(total_scaled_debt, variable_borrow_index) # VDt
    total_debt = total_stable_debt + total_variable_debt # Dt
    available_liquidity = deposit_amount - borrow_amount - flash_amounts[0] - flash_amounts[1]
    utilization_rate = ray_div(total_debt, available_liquidity + total_debt) # Ut
    stable_rate = calculate_stable_borrow_rate(lending_rate_oracle.getMarketBorrowRate(weth), strategy.stableRateSlope1(), strategy.stableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # SRt
    variable_rate = calculate_variable_borrow_rate(strategy.baseVariableBorrowRate(), strategy.variableRateSlope1(), strategy.variableRateSlope2(), utilization_rate, strategy.OPTIMAL_UTILIZATION_RATE()) # VRt
    overall_stable_rate = overall_stable_rate # ^SRt
    overall_borrow_rate = calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate) # ^Rt
    liquidity_rate = ray_mul(overall_borrow_rate, utilization_rate) # LRt

    # Check `WETH` logs
    assert tx_b.events['Transfer'][1]['src'] == weth_atoken
    assert tx_b.events['Transfer'][1]['dst'] == receiver
    assert tx_b.events['Transfer'][1]['wad'] == flash_amounts[1]

    # Check `LendingPool` logs
    assert tx_b.events['FlashLoan'][1]['target'] == receiver
    assert tx_b.events['FlashLoan'][1]['initiator'] == flash_loaner
    assert tx_b.events['FlashLoan'][1]['asset'] == weth
    assert tx_b.events['FlashLoan'][1]['amount'] == flash_amounts[1]
    assert tx_b.events['FlashLoan'][1]['premium'] == flash_amounts[1] * 9 // 10000
    assert tx_b.events['FlashLoan'][1]['referralCode'] == 0
    assert tx_b.events['ReserveDataUpdated'][1]['reserve'] == weth
    assert tx_b.events['ReserveDataUpdated'][1]['variableBorrowRate'] == variable_rate
    assert tx_b.events['ReserveDataUpdated'][1]['stableBorrowRate'] == stable_rate
    assert tx_b.events['ReserveDataUpdated'][1]['liquidityRate'] == liquidity_rate
    assert tx_b.events['ReserveDataUpdated'][1]['variableBorrowIndex'] == variable_borrow_index
    assert tx_b.events['ReserveDataUpdated'][1]['liquidityIndex'] == liquidity_index
    assert tx_b.events['Borrow'][1]['reserve'] == weth
    assert tx_b.events['Borrow'][1]['user'] == flash_loaner
    assert tx_b.events['Borrow'][1]['onBehalfOf'] == flash_loaner
    assert tx_b.events['Borrow'][1]['amount'] == flash_amounts[1]
    assert tx_b.events['Borrow'][1]['borrowRateMode'] == INTEREST_RATE_MODE_VARIABLE
    assert tx_b.events['Borrow'][1]['borrowRate'] == variable_rate
    assert tx_b.events['Borrow'][1]['referral'] == 0

    # Check `VariableDebtToken` logs
    assert tx_b.events['Mint'][1]['from'] == flash_loaner
    assert tx_b.events['Mint'][1]['onBehalfOf'] == flash_loaner
    assert tx_b.events['Mint'][1]['value'] == flash_amounts[1]
    assert tx_b.events['Mint'][1]['index'] == variable_borrow_index
    assert tx_b.events['Transfer'][4]['to'] == flash_loaner
    assert tx_b.events['Transfer'][4]['from'] == ZERO_ADDRESS
    assert tx_b.events['Transfer'][4]['value'] == flash_amounts[1]

    ### Flash Loan 3

    # Check `tERC20` logs
    assert tx_b.events['Transfer'][2]['from'] == terc20_atoken
    assert tx_b.events['Transfer'][2]['to'] == receiver
    assert tx_b.events['Transfer'][2]['value'] == flash_amounts[2]
    assert tx_b.events['Transfer'][5]['to'] == terc20_atoken
    assert tx_b.events['Transfer'][5]['from'] == receiver
    assert tx_b.events['Transfer'][5]['value'] == flash_amounts[2] + flash_amounts[2] * 9 // 10000

    # Check `LendingPool` logs
    assert tx_b.events['FlashLoan'][2]['target'] == receiver
    assert tx_b.events['FlashLoan'][2]['initiator'] == flash_loaner
    assert tx_b.events['FlashLoan'][2]['asset'] == terc20
    assert tx_b.events['FlashLoan'][2]['amount'] == flash_amounts[2]
    assert tx_b.events['FlashLoan'][2]['premium'] == flash_amounts[2] * 9 // 10000
    assert tx_b.events['FlashLoan'][2]['referralCode'] == 0

    # Note `ReserveDataUpdated` logs are inaccurate

###################
# Modifiers & Misc
###################


# Tests `whenNotPaused` modifier
def test_when_not_paused():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    deposit_amount = 1
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositor})

    # Pause LendingPool
    configurator.setPoolPause(True, {'from': emergency_admin})

    # deposit()
    with reverts('64'):
        referral_code = 0
        lending_pool.deposit(weth, deposit_amount, depositor, referral_code, {'from': depositor})


# Tests `onlyLendingPoolConfigurator`
def test_only_lending_pool_configurator():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    with reverts('27'):
        lending_pool.setReserveInterestRateStrategyAddress(weth, accounts[3], {'from': accounts[3]})


# Tests when there is 128 reserves
@pytest.mark.skip()
def test_max_reserves():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Users
    alice = accounts[6] # deposits in all reserves
    bob = accounts[7] # deposits in first reserve then borrows, withdraws and repays

    # Create reserves and have alice
    max_reserves = 127
    price = WEI # 1 tERC20 : 1 ETH
    alice_deposit_amount = WEI
    assets = []
    atokens = []
    stable_tokens = []
    variable_tokens = []
    for i in range(max_reserves):
        # Add additional reserve
        assets.append(
            accounts[0].deploy(
                MintableDelegationERC20,
                str(i) + " Test ERC20",
                str(i) + "ERC20",
                18,
            )
        )

        # Initialise reserve ERC20
        (terc20_atoken, terc20_stable_debt, terc20_variable_debt) = setup_new_reserve(configurator, assets[i], lending_pool, pool_admin)

        atokens.append(terc20_atoken)
        stable_tokens.append(terc20_stable_debt)
        variable_tokens.append(terc20_variable_debt)

        # Turn on collateral and borrowing
        allow_reserve_collateral_and_borrowing(configurator, assets[i], pool_admin)

        # Setup price for tERC20
        if (i == 0):
            price_oracle.setAssetPrice(assets[i], price * 1_000, {'from': accounts[0]})
        else:
            price_oracle.setAssetPrice(assets[i], price, {'from': accounts[0]})

        # Deposit in reserve for Alice

        assets[i].mint(alice_deposit_amount, {'from': alice})
        assets[i].approve(lending_pool, alice_deposit_amount, {'from': alice})
        lending_pool.deposit(assets[i], alice_deposit_amount, alice, 0, {'from': alice})

    # Deposit in first reserve for Bob
    bob_deposit_amount = WEI
    assets[0].mint(bob_deposit_amount, {'from': bob})
    assets[0].approve(lending_pool, bob_deposit_amount, {'from': bob})
    lending_pool.deposit(assets[0], bob_deposit_amount, bob, 0, {'from': bob})

    # Bob borrows
    bob_borrow_amount = bob_deposit_amount // 10_000
    for i in range(1, max_reserves):
        # Stable
        lending_pool.borrow(
            assets[i],
            bob_borrow_amount,
            INTEREST_RATE_MODE_STABLE,
            0,
            bob,
            {'from': bob},
        )

        # Variable
        lending_pool.borrow(
            assets[i],
            bob_borrow_amount,
            INTEREST_RATE_MODE_VARIABLE,
            0,
            bob,
            {'from': bob},
        )

    # Bob `borrow()`
    bob_withdraw_amount = bob_deposit_amount // 10_000
    lending_pool.withdraw(
        assets[0],
        bob_withdraw_amount,
        bob,
        {'from': bob},
    )

    # Bob `repay()` stable
    bob_repay_amount = (1 << 256) - 1
    assets[1].mint(bob_deposit_amount, {'from': bob})
    assets[1].approve(lending_pool, bob_deposit_amount, {'from': bob})
    lending_pool.repay(
        assets[1],
        bob_repay_amount,
        INTEREST_RATE_MODE_STABLE,
        bob,
        {'from': bob},
    )

    # Bob `repay()` stable
    bob_repay_amount = (1 << 256) - 1
    assets[2].mint(bob_deposit_amount, {'from': bob})
    assets[2].approve(lending_pool, bob_deposit_amount, {'from': bob})
    lending_pool.repay(
        assets[2],
        bob_repay_amount,
        INTEREST_RATE_MODE_VARIABLE,
        bob,
        {'from': bob},
    )
