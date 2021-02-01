from brownie import (
    accounts, AToken, AaveOracle, DelegationAwareAToken,
    DefaultReserveInterestRateStrategy, GenericLogic,
    LendingPool, LendingPoolAddressesProvider, LendingPoolConfigurator,
    LendingPoolAddressesProviderRegistry, LendingPoolCollateralManager, MintableDelegationERC20,
    reverts, ReserveLogic, StableDebtToken, ValidationLogic, VariableDebtToken,
    WETH9, ZERO_ADDRESS, web3
)

from helpers import (
    ray_div, ray_mul, wad_div, RAY, WAD, setup_and_deploy_configuration_with_reserve,
    allow_reserve_collateral_and_borrowing, MARKET_BORROW_RATE,
    setup_new_reserve, WEI, INTEREST_RATE_MODE_STABLE, INTEREST_RATE_MODE_NONE, INTEREST_RATE_MODE_VARIABLE,
    calculate_stable_borrow_rate, calculate_variable_borrow_rate,
    calculate_compound_interest, RAY_DIV_WAD, calculate_linear_interest, calculate_overall_borrow_rate,
    calculate_overall_stable_rate, WEI, setup_borrow,
)

import pytest
import time


#####################
# validateDeposit()
#####################

# Tests `validateDeposit()` when frozen
def test_deposit_frozen():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositer = accounts[4]
    deposit_amount = 1_000_000_000
    weth.deposit({'from': depositer, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositer})

    # Freeze LendingPool
    configurator.freezeReserve(weth, {'from': pool_admin})

    # deposit()
    with reverts('3'):
        referral_code = 0
        lending_pool.deposit(weth, deposit_amount, depositer, referral_code, {'from': depositer})


# Tests `validateDeposit()` when deactivated
def test_deposit_deactivated():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositer = accounts[4]
    deposit_amount = 1
    weth.deposit({'from': depositer, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositer})

    # Deactivate `LendingPool`
    configurator.deactivateReserve(weth, {'from': pool_admin})

    # deposit()
    with reverts('2'):
        referral_code = 0
        lending_pool.deposit(weth, deposit_amount, depositer, referral_code, {'from': depositer})


# Tests `validateDeposit()` sending zero funds
def test_deposit_invalid_amount():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositer = accounts[4]
    deposit_amount = 1
    weth.deposit({'from': depositer, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositer})

    # deposit()
    with reverts('1'):
        referral_code = 0
        lending_pool.deposit(weth, 0, depositer, referral_code, {'from': depositer})

#####################
# validateWithdraw()
#####################

# Test `withdraw()` invalid amount
def test_withdraw_invalid_amount():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositer_a = accounts[4]
    amount = 1
    weth.deposit({'from': depositer_a, 'value': amount})
    weth.approve(lending_pool, amount, {'from': depositer_a})

    # `deposit()`
    referral_code = 0
    lending_pool.deposit(weth, amount, depositer_a, referral_code, {'from': depositer_a})

    # `withdraw()` zero
    with reverts('1'):
        lending_pool.withdraw(weth, 0, depositer_a, {'from': depositer_a})


# Test `withdraw()` insufficient balance
def test_withdraw_insufficient_balance():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositer_a = accounts[4]
    amount = 1
    weth.deposit({'from': depositer_a, 'value': amount})
    weth.approve(lending_pool, amount, {'from': depositer_a})

    # `deposit()`
    referral_code = 0
    lending_pool.deposit(weth, amount, depositer_a, referral_code, {'from': depositer_a})

    # `withdraw()` more than balance
    with reverts('5'):
        lending_pool.withdraw(weth, amount + 1, depositer_a, {'from': depositer_a})


# Test `withdraw()` when deactivated
def test_withdraw_deactivated():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositer_a = accounts[4]
    amount = 1
    weth.deposit({'from': depositer_a, 'value': amount})
    weth.approve(lending_pool, amount, {'from': depositer_a})

    # `deposit()`
    referral_code = 0
    lending_pool.deposit(weth, amount, depositer_a, referral_code, {'from': depositer_a})

    # Note this actually reverts due to deactivateReserve() having liquidity
    with reverts():
        # Deactivate `LendingPool`
        configurator.deactivateReserve(weth, {'from': pool_admin})

        # `withdraw()` while deactivated
        lending_pool.withdraw(weth, 1, depositer_a, {'from': depositer_a})


##################
# validateBorrow()
##################


# `validateBorrow()` while frozen
def test_borrow_while_frozen():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # Attempt to `borrow()` while frozen
    configurator.freezeReserve(weth, {'from': pool_admin})
    with reverts('3'):
        borrow_amount = 5
        lending_pool.borrow(
            weth,
            borrow_amount,
            INTEREST_RATE_MODE_STABLE,
            0,
            borrower,
            {'from': borrower},
        )

    with reverts('3'):
        borrow_amount = 5
        lending_pool.borrow(
            weth,
            borrow_amount,
            INTEREST_RATE_MODE_VARIABLE,
            0,
            borrower,
            {'from': borrower},
        )

# `validateBorrow()` borrow zero
def test_borrow_zero():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # Attempt to `borrow()` 0 units
    with reverts('1'):
        borrow_amount = 0
        lending_pool.borrow(
            weth,
            borrow_amount,
            INTEREST_RATE_MODE_STABLE,
            0,
            borrower,
            {'from': borrower},
        )

    with reverts('1'):
        borrow_amount = 0
        lending_pool.borrow(
            weth,
            borrow_amount,
            INTEREST_RATE_MODE_VARIABLE,
            0,
            borrower,
            {'from': borrower},
        )


# `validateBorrow()` with borrowing on reserve disabled
def test_borrowing_disable_borrowing_on_reserve():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # Attempt to `borrow()` borrowing is disabled
    configurator.disableBorrowingOnReserve(weth, {'from': pool_admin})
    with reverts('7'):
        borrow_amount = 5
        lending_pool.borrow(
            weth,
            borrow_amount,
            INTEREST_RATE_MODE_STABLE,
            0,
            borrower,
            {'from': borrower},
        )

    with reverts('7'):
        borrow_amount = 5
        lending_pool.borrow(
            weth,
            borrow_amount,
            INTEREST_RATE_MODE_VARIABLE,
            0,
            borrower,
            {'from': borrower},
        )


# `validateBorrow()` with bad interest rate mode
def test_borrowing_bad_interest_rate_mode():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # Attempt to `borrow()` with interest made node none or just invalid
    with reverts('8'):
        borrow_amount = 5
        lending_pool.borrow(
            weth,
            borrow_amount,
            INTEREST_RATE_MODE_NONE,
            0,
            borrower,
            {'from': borrower},
        )

    with reverts('8'):
        borrow_amount = 5
        lending_pool.borrow(
            weth,
            borrow_amount,
            10,
            0,
            borrower,
            {'from': borrower},
        )


# `validateBorrow()` with no collateral
def test_borrowing_no_collateral():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # Attempt to `borrow()` with no collateral
    with reverts('9'):
        borrow_amount = 5
        lending_pool.borrow(
            weth,
            borrow_amount,
            INTEREST_RATE_MODE_STABLE,
            0,
            accounts[9],
            {'from': accounts[9]},
        )

    with reverts('9'):
        borrow_amount = 5
        lending_pool.borrow(
            weth,
            borrow_amount,
            INTEREST_RATE_MODE_VARIABLE,
            0,
            accounts[9],
            {'from': accounts[9]},
        )


# `validateBorrow()` with bad health factor
def test_borrowing_bad_health_factor():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()` so we can manipulate health factor
    borrow_amount = int(terc20_deposit_amount // 10 * 0.3)
    lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Decrease tERC20 to 10% of it's value to ruin our health factor
    price_oracle.setAssetPrice(terc20, price // 10, {'from': accounts[0]})

    # We now have bad health factor
    with reverts('10'):
        lending_pool.borrow(
            weth,
            1,
            INTEREST_RATE_MODE_STABLE,
            0,
            borrower,
            {'from': borrower},
        )
    with reverts('10'):
        lending_pool.borrow(
            weth,
            1,
            INTEREST_RATE_MODE_VARIABLE,
            0,
            borrower,
            {'from': borrower},
        )


# `validateBorrow()` with insufficient collateral
def test_borrowing_insufficient_colalteral():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # Attempt to `borrow()` with insufficient collateral
    borrow_amount = terc20_deposit_amount # Note terc20 is priced less than Eth
    with reverts('11'):
        lending_pool.borrow(
            weth,
            borrow_amount,
            INTEREST_RATE_MODE_STABLE,
            0,
            borrower,
            {'from': borrower},
        )

    with reverts('11'):
        lending_pool.borrow(
            weth,
            borrow_amount,
            INTEREST_RATE_MODE_VARIABLE,
            0,
            borrower,
            {'from': borrower},
        )


# `validateBorrow()` with stable borrowing on reserve disabled
# Note this test fails due to a bug in the code
# See the check on https://github.com/aave/protocol-v2/blob/eea6d38f243b909fc3cf82a581c45b8bc3d2390e/contracts/protocol/libraries/logic/ValidationLogic.sol#L200
@pytest.mark.xfail(reason='Ineffective rate mode check')
def test_borrowing_disable_stable_borrowing_on_reserve():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # Attempt to `borrow()` while stable borrowing is disabled
    configurator.disableReserveStableRate(weth, {'from': pool_admin})
    borrow_amount = 5
    with reverts('12'):
        lending_pool.borrow(
            weth,
            borrow_amount,
            INTEREST_RATE_MODE_STABLE,
            0,
            borrower,
            {'from': borrower},
        )

    # Variable borrowing is still allowed
    lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )


# `validateBorrow()` stable borrow from collateralised reserve
# Note this test fails due to a bug in the code
# See the check on https://github.com/aave/protocol-v2/blob/eea6d38f243b909fc3cf82a581c45b8bc3d2390e/contracts/protocol/libraries/logic/ValidationLogic.sol#L200
@pytest.mark.xfail(reason='Ineffective rate mode check')
def test_borrowing_stable_borrow_same_as_collateral():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # Attempt to `borrow()` the same currency as the collateral (but less than the collateral)
    borrow_amount = 5
    with reverts('13'):
        lending_pool.borrow(
            terc20,
            borrow_amount,
            INTEREST_RATE_MODE_STABLE,
            0,
            borrower,
            {'from': borrower},
        )

    # Variable borrowing is still allowed
    lending_pool.borrow(
        terc20,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )


# `validateBorrow()` stable borrow more than max allowable
# Note this test fails due to a bug in the code
# See the check on https://github.com/aave/protocol-v2/blob/eea6d38f243b909fc3cf82a581c45b8bc3d2390e/contracts/protocol/libraries/logic/ValidationLogic.sol#L200
@pytest.mark.xfail(reason='Ineffective rate mode check')
def test_borrowing_stable_borrow_more_than_max():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # Increase price to ensure we have sufficient colalteral
    price_oracle.setAssetPrice(terc20, price * 1000, {'from': accounts[0]})

    # Attempt to `borrow()` more than 25% of the asset's liquidity
    borrow_amount = deposit_amount * 3 // 10 # > 25% of liquidity
    with reverts('14'):
        lending_pool.borrow(
            weth,
            borrow_amount,
            INTEREST_RATE_MODE_STABLE,
            0,
            borrower,
            {'from': borrower},
        )

    # Variable borrowing is still allowed
    lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )


##################
# validateRepay()
##################


# Test `validateRepay()` when reserve is not active
def test_repay_deactivated():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Deactivate `LendingPool`
    configurator.deactivateReserve(weth, {'from': pool_admin})

    with reverts('2'):
        lending_pool.repay(
            weth,
            1,
            INTEREST_RATE_MODE_STABLE,
            accounts[3],
            {'from': accounts[3]}
        )

    with reverts('2'):
        lending_pool.repay(
            weth,
            1,
            INTEREST_RATE_MODE_VARIABLE,
            accounts[3],
            {'from': accounts[3]}
        )


# Test `validateRepay()` when the amount is zero
def test_repay_zero():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    with reverts('1'):
        lending_pool.repay(
            weth,
            0,
            INTEREST_RATE_MODE_STABLE,
            accounts[3],
            {'from': accounts[3]}
        )

    with reverts('1'):
        lending_pool.repay(
            weth,
            0,
            INTEREST_RATE_MODE_VARIABLE,
            accounts[3],
            {'from': accounts[3]}
        )


# Test `validateRepay()` when the debt is zero
def test_repay_with_no_debt():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    with reverts('15'):
        lending_pool.repay(
            weth,
            1,
            INTEREST_RATE_MODE_STABLE,
            accounts[3],
            {'from': accounts[3]}
        )

    with reverts('15'):
        lending_pool.repay(
            weth,
            1,
            INTEREST_RATE_MODE_VARIABLE,
            accounts[3],
            {'from': accounts[3]}
        )


# Test `validateRepay()` on behalf of with max value
def test_repay_max_on_behalf_of():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositer = accounts[4]
    deposit_amount = 10_000_000_000_000_000_000
    weth.deposit({'from': depositer, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositer})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Set market lending rate
    lending_rate_oracle.setMarketBorrowRate(weth, MARKET_BORROW_RATE)

    # `deposit()` weth
    lending_pool.deposit(weth, deposit_amount, depositer, 0, {'from': depositer})

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
    borrow_amount = terc20_deposit_amount // 1000
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    with reverts('16'):
        lending_pool.repay(
            weth,
            (1 << 256) - 1,
            INTEREST_RATE_MODE_STABLE,
            borrower,
            {'from': accounts[-1]}
        )

    # `borrow()`
    borrow_amount = terc20_deposit_amount // 1000
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    with reverts('16'):
        lending_pool.repay(
            weth,
            (1 << 256) - 1,
            INTEREST_RATE_MODE_VARIABLE,
            borrower,
            {'from': accounts[-1]}
        )


########################
# validateSwapRateMode()
########################


# Test `validateSwapRateMode()` when reserve is not active
def test_swap_rate_deactivated():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Deactivate `LendingPool`
    configurator.deactivateReserve(weth, {'from': pool_admin})

    with reverts('2'):
        lending_pool.swapBorrowRateMode(
            weth,
            INTEREST_RATE_MODE_STABLE,
            {'from': accounts[3]}
        )

    with reverts('2'):
        lending_pool.swapBorrowRateMode(
            weth,
            INTEREST_RATE_MODE_VARIABLE,
            {'from': accounts[3]}
        )


# Test `validateSwapRateMode()` when reserve is frozen
def test_swap_rate_frozen():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Freeze `LendingPool`
    configurator.freezeReserve(weth, {'from': pool_admin})

    with reverts('3'):
        lending_pool.swapBorrowRateMode(
            weth,
            INTEREST_RATE_MODE_STABLE,
            {'from': accounts[3]}
        )

    with reverts('3'):
        lending_pool.swapBorrowRateMode(
            weth,
            INTEREST_RATE_MODE_VARIABLE,
            {'from': accounts[3]}
        )


# Test `validateSwapRateMode()` without stable debt
def test_swap_rate_no_stable_debt():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()` variable debt
    lending_pool.borrow(
        weth,
        10,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    with reverts('17'):
        lending_pool.swapBorrowRateMode(
            weth,
            INTEREST_RATE_MODE_STABLE,
            {'from': borrower}
        )


# Test `validateSwapRateMode()` without variable debt
def test_swap_rate_no_variable_debt():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()` stable debt
    lending_pool.borrow(
        weth,
        10,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    with reverts('18'):
        lending_pool.swapBorrowRateMode(
            weth,
            INTEREST_RATE_MODE_VARIABLE,
            {'from': borrower}
        )


# Test `validateSwapRateMode()` swap to stable when it is used as collateral
def test_swap_rate_to_stable_with_collateral():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()`
    lending_pool.borrow(
        weth,
        10,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Deposit WETH to use as collateral
    weth.deposit({'from': borrower, 'value': WEI})
    weth.approve(lending_pool, WEI, {'from': borrower})
    lending_pool.deposit(weth, WEI, borrower, 0, {'from': borrower})

    # Attempt to swap with collateral
    with reverts('13'):
        lending_pool.swapBorrowRateMode(
            weth,
            INTEREST_RATE_MODE_VARIABLE,
            {'from': borrower}
        )


# Test `validateSwapRateMode()` with bad rate mode
def test_swap_rate_bad_mode():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()`
    lending_pool.borrow(
        weth,
        10,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )
    lending_pool.borrow(
        weth,
        10,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Attempt to swap with collateral
    with reverts('8'):
        lending_pool.swapBorrowRateMode(
            weth,
            INTEREST_RATE_MODE_NONE,
            {'from': borrower}
        )

    # Attempt to swap with collateral
    with reverts():
        lending_pool.swapBorrowRateMode(
            weth,
            3,
            {'from': borrower}
        )

    # Attempt to swap with collateral
    with reverts():
        lending_pool.swapBorrowRateMode(
            weth,
            (1 << 256) - 1,
            {'from': borrower}
        )


#####################################
# validateRebalanceStableBorrowRate()
#####################################


# Test `validateRebalanceStableBorrowRate()` when reserve is not active
def test_rebalance_deactivated():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositer = accounts[4]
    deposit_amount = 1
    weth.deposit({'from': depositer, 'value': deposit_amount})
    weth.approve(lending_pool, deposit_amount, {'from': depositer})

    # Deactivate `LendingPool`
    configurator.deactivateReserve(weth, {'from': pool_admin})

    # deposit()
    with reverts('2'):
        referral_code = 0
        lending_pool.rebalanceStableBorrowRate(weth, depositer, {'from': accounts[-1]})


# Test `validateRebalanceStableBorrowRate()` when below threshold
def test_rebalance_below_liquidity_threshold():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()`
    borrow_amount = terc20_deposit_amount // 1_000
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # `rebalanceStableBorrowRate()` with less than the liquidity threshold
    available_liquidity = weth.balanceOf(weth_atoken)
    total_debt = weth_stable_debt.totalSupply()
    assert total_debt / (available_liquidity + total_debt) < 0.95
    with reverts('22'):
        lending_pool.rebalanceStableBorrowRate(
            weth,
            borrower,
            {'from': accounts[-1]}
        )


# Test `validateRebalanceStableBorrowRate()` with less than the rate threshold
def test_rebalance_below_rate_threshold():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # Setup price for tERC20
    price = WEI * 1000 # 1 tERC20 : 1000 ETH
    price_oracle.setAssetPrice(terc20, price, {'from': accounts[0]})

    available_liquidity = weth.balanceOf(weth_atoken)

    # `borrow()` variable to set a high overall rate
    borrow_amount = available_liquidity * 99 // 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # `borrow()` stable getting a very high rate
    available_liquidity = weth.balanceOf(weth_atoken)
    tx = lending_pool.borrow(
        weth,
        available_liquidity,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # `rebalanceStableBorrowRate()` with less than the rate threshold (but more than liquidity threshold)
    available_liquidity = weth.balanceOf(weth_atoken)
    total_debt = weth_stable_debt.totalSupply()
    assert total_debt / (available_liquidity + total_debt) >= 0.95 # ensure we pass the liquidity threshold check
    with reverts('22'):
        lending_pool.rebalanceStableBorrowRate(
            weth,
            borrower,
            {'from': accounts[-1]}
        )


######################################
# validateSetUseReserveAsCollateral()
######################################


# Tests `validateSetUseReserveAsCollateral()` with zero balance
def test_validate_reserve_as_collateral_no_balance():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # `setUserUseReserveAsCollateral()`
    with reverts('19'):
        lending_pool.setUserUseReserveAsCollateral(weth, True, {'from': accounts[4]})


# Tests `validateSetUseReserveAsCollateral()` when no reserve exists
def test_validate_reserve_as_collateral_no_reserve():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # `setUserUseReserveAsCollateral()`
    with reverts():

        lending_pool.setUserUseReserveAsCollateral(accounts[2], True, {'from': accounts[4]})


# Tests `validateSetUseReserveAsCollateral()` when using that a collateral for a borrow
def test_validate_reserve_as_collateral_deposit_used():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()` variable to set a high overall rate
    borrow_amount = terc20_deposit_amount / 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # `setUserUseReserveAsCollateral()`
    with reverts('20'):
        lending_pool.setUserUseReserveAsCollateral(terc20, False, {'from': borrower})


#############################
# validateLiquidationCall()
#############################


# Tests `validateLiquidationCall()` when deactivated
def test_liquidation_call_deactivated():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

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

    # Deactivate WETH
    configurator.deactivateReserve(weth, {'from': pool_admin})


    # Note reverts in the delegate call all return '23'
    with reverts('2'):
        lending_pool.liquidationCall(weth, terc20, accounts[1], 1, False, {'from': accounts[2]})

    with reverts('2'):
        lending_pool.liquidationCall(terc20, weth, accounts[1], 1, False, {'from': accounts[2]})


# Tests `validateLiquidationCall()` with valid health factor
def test_liquidation_call_health_factor():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price) = setup_borrow()

    # `borrow()` variable to set a high overall rate
    borrow_amount = terc20_deposit_amount / 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    with reverts('42'):
        # Good health factor
        lending_pool.liquidationCall(weth, terc20, borrower, 1, False, {'from': accounts[7]})

    with reverts('42'):
        # Maximum health factor
        lending_pool.liquidationCall(weth, terc20, depositer, 1, False, {'from': accounts[7]})


# Tests `validateLiquidationCall()` when not using as collateral
def test_liquidation_call_not_used_as_collateral():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    a_erc20, a_erc20_atoken, a_erc20_stable_debt, a_erc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    a_erc20_deposit_amount, price_a) = setup_borrow()

    # `borrow()` variable to set a high overall rate
    borrow_amount = a_erc20_deposit_amount / 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Add additional reserve
    b_erc20 = accounts[0].deploy(
        MintableDelegationERC20,
        "b ERC20",
        "bERC20",
        5,
    )

    # Initialise reserve tERC20
    (b_erc20_atoken, b_erc20_stable_debt, b_erc20_variable_debt) = setup_new_reserve(configurator, b_erc20, lending_pool, pool_admin)

    # Turn on collateral and borrowing
    (b_ecr20_ltv, b_ecr20_threshold, b_ecr20_bonus) = allow_reserve_collateral_and_borrowing(configurator, b_erc20, pool_admin)

    # Setup price for tERC20
    price_b = WEI // 10 # 1 bERC20 : 0.1 ETH
    price_oracle.setAssetPrice(b_erc20, price_b, {'from': accounts[0]})

    # `deposit()` some b_erc20 and turn off use as collateral
    b_erc20_deposit_amount = deposit_amount
    b_erc20.mint(b_erc20_deposit_amount, {'from': borrower})
    b_erc20.approve(lending_pool, b_erc20_deposit_amount, {'from': borrower})
    lending_pool.deposit(b_erc20, b_erc20_deposit_amount, borrower, 0, {'from': borrower})
    lending_pool.setUserUseReserveAsCollateral(b_erc20, False, {'from': borrower})

    # Tank price for aERC20 so we have bad health factor
    price_a = price_a // 1_000
    price_oracle.setAssetPrice(a_erc20, price_a, {'from': accounts[0]})

    with reverts('43'):
        # Attempt to liquidate collateral that is not being used as collateral
        lending_pool.liquidationCall(weth, b_erc20, borrower, 1, False, {'from': accounts[7]})


# Tests `validateLiquidationCall()` when there is no debt in that asset
def test_liquidation_call_with_no_debt():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    a_erc20, a_erc20_atoken, a_erc20_stable_debt, a_erc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    a_erc20_deposit_amount, price_a) = setup_borrow()

    # `borrow()` variable to set a high overall rate
    borrow_amount = a_erc20_deposit_amount / 100
    tx = lending_pool.borrow(
        weth,
        borrow_amount,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # Tank price for aERC20 so we have bad health factor
    price_a = price_a // 1_000
    price_oracle.setAssetPrice(a_erc20, price_a, {'from': accounts[0]})

    with reverts('44'):
        lending_pool.liquidationCall(a_erc20, a_erc20, borrower, 1, False, {'from': accounts[7]})


#####################
# validateFlashLoan()
#####################


# Tests `validateFlashLoan()`
def test_validate_flash_loan():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    a_erc20, a_erc20_atoken, a_erc20_stable_debt, a_erc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    a_erc20_deposit_amount, price_a) = setup_borrow()

    with reverts('73'):
        lending_pool.flashLoan(
            accounts[0],
            [weth, weth],
            [1],
            [INTEREST_RATE_MODE_NONE],
            accounts[1],
            b'',
            0,
            {'from': accounts[1]}
        )


####################
# validateTransfer()
####################


# Tests `validateTransfer()`
def test_validate_transfer():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
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

    with reverts('6'):
        terc20_atoken.transfer(accounts[2], terc20_deposit_amount * 9 // 10, {'from': borrower})
