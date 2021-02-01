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
    MAX_UINT256, allow_reserve_collateral_and_borrowing, MARKET_BORROW_RATE,
    setup_new_reserve, WEI, INTEREST_RATE_MODE_STABLE, INTEREST_RATE_MODE_NONE, INTEREST_RATE_MODE_VARIABLE,
    calculate_stable_borrow_rate, calculate_variable_borrow_rate,
    calculate_compound_interest, RAY_DIV_WAD, calculate_linear_interest, calculate_overall_borrow_rate,
    calculate_overall_stable_rate,
)

import pytest
import time

################
# transfer()
################

# Test cannot mint to 0x0
def test_deposit_0x0():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Configure reserve collateral and borrowing
    (ltv, threhold, bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    receiver = accounts[5]
    deposit_amount = 100
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool.address, deposit_amount, {'from': depositor})

    # deposit()
    referral_code = 500
    with reverts():
        lending_pool.deposit(weth.address, deposit_amount, ZERO_ADDRESS, referral_code, {'from': depositor})

# Test cannot withdraw to 0x0
def test_withdraw_0x0():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Configure reserve collateral and borrowing
    (ltv, threhold, bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    receiver = accounts[5]
    deposit_amount = 100
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool.address, deposit_amount, {'from': depositor})

    # deposit()
    referral_code = 500
    lending_pool.deposit(weth.address, deposit_amount, depositor, referral_code, {'from': depositor})

    # attempt to withdraw to the 0x0 address
    lending_pool.withdraw(weth.address, deposit_amount, ZERO_ADDRESS,
            {'from': depositor})

    # The zero address now has weth tokens
    assert weth.balanceOf(ZERO_ADDRESS) == deposit_amount


# Test basic functionality of Atoken transfers
def test_transfers():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Configure reserve collateral and borrowing
    (ltv, threhold, bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    receiver = accounts[5]
    deposit_amount = 100
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool.address, deposit_amount, {'from': depositor})

    # deposit()
    referral_code = 500
    lending_pool.deposit(weth.address, deposit_amount, depositor, referral_code, {'from': depositor})

    # Check `AToken` state
    assert atoken.balanceOf(depositor) == deposit_amount
    assert atoken.scaledBalanceOf(depositor) == deposit_amount
    assert atoken.totalSupply() == deposit_amount

    # Transfer atokens

    # Should be able to transfer to self
    tx = atoken.transfer(depositor, deposit_amount, {'from': depositor})
    assert tx.events['Transfer']['from'] == depositor
    assert tx.events['Transfer']['to'] == depositor
    assert tx.events['Transfer']['value'] == deposit_amount

    # Should be able to transfer to others
    tx = atoken.transfer(receiver, deposit_amount, {'from': depositor})
    assert tx.events['Transfer']['from'] == depositor
    assert tx.events['Transfer']['to'] == receiver
    assert tx.events['Transfer']['value'] == deposit_amount

    assert atoken.balanceOf(depositor) == 0
    assert atoken.balanceOf(receiver) == deposit_amount

    # Check basic limits
    with reverts():
        # Should not be able to transfer beyond empty balance
        atoken.transfer(receiver, 1, {'from': depositor})
        # Should not be able to transfer to self extra balance
        atoken.transfer(receiver, deposit_amount + 1, {'from': receiver})
        # Should not be able to overflow
        atoken.transfer(depositor, MAX_UINT256 - 1 , {'from': receiver})


    # Should be able to transfer some back
    atoken.transfer(depositor, deposit_amount/2 , {'from': receiver})

    assert atoken.balanceOf(depositor) == deposit_amount/2
    assert atoken.balanceOf(receiver) == deposit_amount/2


# Test basic validation of atokens
def test_validation():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Configure reserve collateral and borrowing
    (ltv, threhold, bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    receiver = accounts[5]
    deposit_amount = 100
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool.address, deposit_amount, {'from': depositor})

    # deposit()
    referral_code = 500
    tx = lending_pool.deposit(weth.address, deposit_amount, depositor, referral_code, {'from': depositor})

    with reverts('29'):
        # Should not be able to transfer beyond empty balance
        atoken.mint(depositor, 100, 0, {'from': depositor})
        atoken.burn(depositor, depositor, 100, 0, {'from': depositor})


# Test deposit and withdrawal logic
# Looks at calculations of interest, orders of deposits and correct withdrawal
# amounts
def test_deposit_withdraw():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositor = accounts[4]
    depositor2 = accounts[11]
    depositor3 = accounts[12]
    deposit_amount = 1_000_000_000_000
    weth.deposit({'from': depositor, 'value': deposit_amount})
    weth.approve(lending_pool.address, deposit_amount, {'from': depositor})
    weth.deposit({'from': depositor2, 'value': deposit_amount})
    weth.approve(lending_pool.address, deposit_amount, {'from': depositor2})
    weth.deposit({'from': depositor3, 'value': deposit_amount})
    weth.approve(lending_pool.address, deposit_amount, {'from': depositor3})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Set market lending rate
    lending_rate_oracle.setMarketBorrowRate(weth.address, MARKET_BORROW_RATE)

    # `deposit()` weth
    lending_pool.deposit(weth.address, deposit_amount, depositor, 0, {'from': depositor})

    # Check the atoken balance of the first depositor
    assert weth_atoken.balanceOf(depositor) == deposit_amount

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
    price =  WEI // 10 # 1 tERC20 : 0.1 ETH
    price_oracle.setAssetPrice(terc20.address, price, {'from': accounts[0]})

    ### First Borrower ###

    # Create tERC20 tokens for `borrower` and deposit them into `LendingPool`
    borrower = accounts[5]
    terc20_deposit_amount = (deposit_amount * 5 + 1) // 0.3  # The collateral will allow us to borrow up half the amount of the original deposit. (30% ltv)
    terc20.mint(terc20_deposit_amount, {'from': borrower})
    terc20.approve(lending_pool.address, terc20_deposit_amount, {'from': borrower})
    lending_pool.deposit(terc20.address, terc20_deposit_amount, borrower, 0, {'from': borrower})

    # `borrow()`

    # Should not be able to borrow more than the original deposit
    with reverts('11'):
        tx1 = lending_pool.borrow(
            weth.address,
            deposit_amount // 2 + 1,
            INTEREST_RATE_MODE_STABLE,
            0,
            borrower,
            {'from': borrower},
        )

    # Should be able to borrow the deposit amount however
    borrow_amount = deposit_amount // 2
    tx1 = lending_pool.borrow(
        weth.address,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        borrower,
        {'from': borrower},
    )

    # The token balance should have increased
    # Calculate the normalized reserve income of weth
    reserve_data = lending_pool.getReserveData(weth.address)
    time_diff = 0

    cumulated = ray_mul(calculate_linear_interest(reserve_data[3], time_diff), reserve_data[1])

    assert cumulated == lending_pool.getReserveNormalizedIncome(weth.address)

    # Wait for some interest to accrue
    web3.manager.request_blocking("evm_increaseTime", 4)

    ### Second Borrower ###

    # Create tERC20 tokens for `second_borrower_funder` and deposit them into `LendingPool`
    second_borrower_funder = accounts[10]
    ## The account that will actually borrow
    second_borrower = accounts[6]
    ## The account that will perform the borrow on behalf of the second borrower
    borrow_behalf = accounts[7]
    terc20.mint(terc20_deposit_amount, {'from': second_borrower_funder})
    terc20.approve(lending_pool.address, terc20_deposit_amount, {'from': second_borrower_funder})
    ## Borrow on behalf of a random user
    tx2 = lending_pool.deposit(terc20.address, terc20_deposit_amount, second_borrower, 10, {'from': second_borrower_funder})

    # Calculate the normalized reserve income of weth
    reserve_data = lending_pool.getReserveData(weth.address)
    time_diff = tx2.timestamp - tx1.timestamp
    cumulated = ray_mul(calculate_linear_interest(reserve_data[3], time_diff), reserve_data[1])
    assert cumulated == lending_pool.getReserveNormalizedIncome(weth.address)
    assert weth_atoken.balanceOf(depositor) == ray_mul(cumulated, deposit_amount)

    ## Allow borrow_behalf to borrow on behalf of second_borrower
    weth_stable_debt.approveDelegation(borrow_behalf, borrow_amount, {'from': second_borrower})

    tx3 = lending_pool.borrow(
        weth.address,
        borrow_amount,
        INTEREST_RATE_MODE_STABLE,
        0,
        second_borrower,
        {'from': borrow_behalf},
    )

    ## Check the balances
    reserve_data = lending_pool.getReserveData(weth.address)
    time_diff = 0
    cumulated = ray_mul(calculate_linear_interest(reserve_data[3], time_diff), reserve_data[1])
    assert cumulated == lending_pool.getReserveNormalizedIncome(weth.address)
    assert weth_atoken.balanceOf(depositor) == ray_mul(cumulated, deposit_amount)
    # We have borrowed all the weth
    assert weth.balanceOf(weth_atoken.address) == 0

    assert terc20_atoken.balanceOf(second_borrower_funder) == 0
    assert terc20_atoken.balanceOf(second_borrower) == terc20_deposit_amount
    assert weth.balanceOf(borrow_behalf) == borrow_amount
    assert weth_stable_debt.balanceOf(second_borrower) == borrow_amount
    assert weth.balanceOf(second_borrower) == 0

    # A second depositor comes along and deposits weth
    tx4 = lending_pool.deposit(weth.address, deposit_amount, depositor2, 45, {'from': depositor2})
    ## Check the balance of depositor2
    reserve_data = lending_pool.getReserveData(weth.address)
    assert weth_atoken.scaledBalanceOf(depositor2) == ray_div(deposit_amount, reserve_data[1])

    # Wait for some interest to accrue
    web3.manager.request_blocking("evm_increaseTime", 4)
    tx5 = lending_pool.deposit(weth.address, deposit_amount, depositor3, 0, {'from': depositor3})

    # Depositors interest should be 1 > 2 > 3.
    reserve_data = lending_pool.getReserveData(weth.address)
    time_diff = 0
    cumulated = ray_mul(calculate_linear_interest(reserve_data[3], time_diff), reserve_data[1])
    assert cumulated == lending_pool.getReserveNormalizedIncome(weth.address)
    # Check the balances
    assert weth_atoken.scaledBalanceOf(depositor) == deposit_amount
    ## The last deposit should be scaled
    assert weth_atoken.scaledBalanceOf(depositor3) == ray_div(deposit_amount, reserve_data[1])

    assert weth_atoken.balanceOf(depositor) == ray_mul(cumulated, weth_atoken.scaledBalanceOf(depositor))
    assert weth_atoken.balanceOf(depositor2) == ray_mul(cumulated, weth_atoken.scaledBalanceOf(depositor2))
    assert weth_atoken.balanceOf(depositor3) == ray_mul(cumulated, weth_atoken.scaledBalanceOf(depositor3))

    assert weth_atoken.balanceOf(depositor) > weth_atoken.balanceOf(depositor2)
    assert weth_atoken.balanceOf(depositor2) > weth_atoken.balanceOf(depositor3)


    ## Verify basic withdrawal logic
    # At this point:
    # Depositor, Depositor2 and Depositor3 have deposited `deposit_amount` of
    # weth.
    # There have been 2 borrows each requesting half of the deposit_amount.
    # There should remain 2 `deposit_amount` weth left and should be withdrawable

    assert weth.balanceOf(weth_atoken.address) == 2* deposit_amount

    # Initial depositor can withdraw excess due to interest.
    lending_pool.withdraw(weth.address, deposit_amount + 1, ZERO_ADDRESS, {'from': depositor} )

    with reverts('5'):
        # The depositor cannot withdraw all the remaining funds
        lending_pool.withdraw(weth.address, deposit_amount - 1, ZERO_ADDRESS, {'from': depositor} )

    with reverts():
        # The second depositor cannot withdraw more than was deposited
        lending_pool.withdraw(weth.address, deposit_amount, ZERO_ADDRESS, {'from': depositor2} )

    # The second depositor can withdraw the remaining underlying weth
    lending_pool.withdraw(weth.address, deposit_amount - 1, ZERO_ADDRESS, {'from': depositor2} )

    with reverts():
        # The third depositor cannot withdraw anything
        lending_pool.withdraw(weth.address, 1, ZERO_ADDRESS, {'from': depositor2} )




