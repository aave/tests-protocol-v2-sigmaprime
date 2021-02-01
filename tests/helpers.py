from brownie import (
    accounts, AToken, Contract, DefaultReserveInterestRateStrategy,
    GenericLogic, LendingPool, LendingPool2,
    LendingPoolAddressesProvider, LendingPoolConfigurator,
    LendingPoolCollateralManager, LendingRateOracle, MintableDelegationERC20, PriceOracle, ReserveLogic,
    reverts, StableDebtToken, VariableDebtToken, ValidationLogic, WETH9, ZERO_ADDRESS
)

from Crypto.Hash import keccak
import pytest

# Wei (10^18)
WEI = 1_000_000_000_000_000_000

# WadRayMath
RAY = 1000000000000000000000000000
WAD = 1000000000000000000
RAY_DIV_WAD = RAY // WAD

# PercentMath
PERCENTAGE_FACTOR = 10_000
HALF_PERCENT = 5_000

SECONDS_PER_YEAR = 60 * 60 * 24 * 365

# MAX UINT256
MAX_UINT256 = (1 << 256) - 1

# ReserveConfiguration map constants
LIQUIDATION_THRESHOLD_START_BIT_POSITION = 16
LIQUIDATION_BONUS_START_BIT_POSITION = 32
RESERVE_DECIMALS_START_BIT_POSITION = 48
IS_ACTIVE_START_BIT_POSITION = 56
IS_FROZEN_START_BIT_POSITION = 57
BORROWING_ENABLED_START_BIT_POSITION = 58
STABLE_BORROWING_ENABLED_START_BIT_POSITION = 59
RESERVE_FACTOR_START_BIT_POSITION = 64

# UserConfiguration map constants
BORROWING_MASK = 0x5555555555555555555555555555555555555555555555555555555555555555

# Interest rate modes used in `LendingPool`
INTEREST_RATE_MODE_NONE = 0
INTEREST_RATE_MODE_STABLE = 1
INTEREST_RATE_MODE_VARIABLE = 2

# Default values for `DefaultReserveInterestRateStrategy` constructor
OPTIMAL_UTILIZATION_RATE = 2 * RAY // 10 # 20%
BASE_VARIABLE_BORROW_RATE = 2 * RAY // 100 # 2.00%
VARIABLE_RATE_SLOPE_1 = RAY // 100 # 1.00%
VARIABLE_RATE_SLOPE_2 = 5 * RAY // 100 # 5.00%
STABLE_RATE_SLOPE_1 = 4 * RAY // 100 # 4.00%
STABLE_RATE_SLOPE_2 = 7 * RAY // 100 # 7.00%

# Lending Rate Oracle - market borrow rate
MARKET_BORROW_RATE = 30000000000000000000000000 # 3.00%

# Default Reserve Parameters
LTV = 3_000 # 30%
THRESHOLD = 5_000 # 50%
BONUS = 11_000 # 110%


#################################
# Setup and Deployment functions
#################################


# Deploy and initialize contracts required for `LendingPool`.
# Additionally, set `LendingPool` and `LendingPoolConfiguration` to the proxy contracts.
def setup_and_deploy():
    # Dependent contracts
    accounts[0].deploy(ReserveLogic)
    accounts[0].deploy(GenericLogic)
    accounts[0].deploy(ValidationLogic)

    # Deployed contracts
    provider = accounts[0].deploy(LendingPoolAddressesProvider)
    pool = accounts[0].deploy(LendingPool)
    configurator = accounts[0].deploy(LendingPoolConfigurator)
    collateral_manager = accounts[0].deploy(LendingPoolCollateralManager)
    pool_admin = accounts[1]
    emergency_admin = accounts[2]
    price_oracle = accounts[0].deploy(PriceOracle)
    lending_rate_oracle = accounts[0].deploy(LendingRateOracle)

    # Setups & Initialization
    provider.setLendingPoolImpl(pool.address)
    provider.setLendingPoolConfiguratorImpl(configurator.address)
    provider.setLendingPoolCollateralManager(collateral_manager.address)
    provider.setPoolAdmin(pool_admin)
    provider.setEmergencyAdmin(emergency_admin)
    provider.setPriceOracle(price_oracle)
    provider.setLendingRateOracle(lending_rate_oracle)

    # Proxy the required contracts
    pool_proxy = Contract.from_abi(LendingPool, provider.getLendingPool(), pool.abi)
    configurator_proxy = Contract.from_abi(LendingPoolConfigurator, provider.getLendingPoolConfigurator(), configurator.abi)


    return (provider, pool_proxy, configurator_proxy, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle)


# Deploys and setup require contracts for `LendingPoolConfiguration`
def setup_and_deploy_configuration():
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
        weth.address,
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
        "stableDebtWETH",
        incentivesController,
    )
    variable_debt = accounts[0].deploy(
        VariableDebtToken,
        lending_pool.address,
        weth.address,
        "Aave variable debt bearing WETH",
        "variableDebtWETH",
        incentivesController,
    )
    strategy = deploy_default_strategy(addresses_provider.address)

    return (addresses_provider, lending_pool, configurator, collateral_manager,
        pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
        stable_debt, variable_debt, strategy)


# Deploys and setup require contracts for `LendingPoolConfiguration`
def setup_and_deploy_configuration_with_reserve():
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken,
    stable_debt, variable_debt, strategy) = setup_and_deploy_configuration()

    # initReserve()
    (atoken_proxy, stable_proxy, variable_proxy) = setup_new_reserve(configurator, weth, lending_pool, pool_admin)

    # Set price oracle, weth and usd prices
    price_oracle.setAssetPrice(weth.address, WEI, {'from': accounts[0]})
    price_oracle.setEthUsdPrice(500)

    return (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, atoken_proxy,
    stable_proxy, variable_proxy, strategy)


# Add and initialise an additional reserve, creating require tokens
def setup_new_reserve(configurator, asset, lending_pool, pool_admin):
    # Deploy contracts required for a Reserve
    incentivesController = ZERO_ADDRESS
    reserveTreasuryAddress = ZERO_ADDRESS
    atoken = accounts[0].deploy(
        AToken,
        lending_pool.address,
        asset.address,
        reserveTreasuryAddress,
        'Aave interest bearing ' + asset.symbol(),
        'a' +  asset.symbol(),
        incentivesController
    )
    stable_debt = accounts[0].deploy(
        StableDebtToken,
        lending_pool.address,
        asset.address,
        "Aave stable debt bearing " + asset.symbol(),
        "stableDebt" + asset.symbol(),
        incentivesController,
    )
    variable_debt = accounts[0].deploy(
        VariableDebtToken,
        lending_pool.address,
        asset.address,
        "Aave variable debt bearing " + asset.symbol(),
        "variableDebt" + asset.symbol(),
        incentivesController,
    )
    strategy = deploy_default_strategy(lending_pool.getAddressesProvider())

    (atoken_proxy, stable_proxy, variable_proxy) = init_reserve_and_set_proxies(configurator, atoken, stable_debt, variable_debt, asset, strategy, pool_admin)

    return (atoken_proxy, stable_proxy, variable_proxy)


# Initialises the reserve and returns the proxied token contracts
def init_reserve_and_set_proxies(configurator, atoken, stable_debt, variable_debt, asset, strategy, pool_admin):
    # initReserve()
    tx = configurator.initReserve(
        atoken.address,
        stable_debt.address,
        variable_debt.address,
        asset.decimals(),
        strategy.address,
        {'from': pool_admin},
    )

    # Update proxy addresses
    init_event = tx.events['ReserveInitialized']
    atoken_proxy_address = init_event['aToken']
    stable_proxy_address = init_event['stableDebtToken']
    variable_proxy_address = init_event['variableDebtToken']

    atoken_proxy = Contract.from_abi(AToken, atoken_proxy_address, atoken.abi)
    stable_proxy = Contract.from_abi(StableDebtToken, stable_proxy_address, stable_debt.abi)
    variable_proxy = Contract.from_abi(VariableDebtToken, variable_proxy_address, variable_debt.abi)

    return (atoken_proxy, stable_proxy, variable_proxy)


# Turn on reserve borrowing and collateral at default rates
def allow_reserve_collateral_and_borrowing(configurator, asset, pool_admin, params=None):
    configurator.enableBorrowingOnReserve(asset.address, True, {'from': pool_admin})
    if (params != None):
        (ltv, threshold, bonus) = params
        configurator.configureReserveAsCollateral(asset.address, ltv, threshold, bonus, {'from': pool_admin})
        return (ltv, threshold, bonus)
    else:
        configurator.configureReserveAsCollateral(asset.address, LTV, THRESHOLD, BONUS, {'from': pool_admin})
        return (LTV, THRESHOLD, BONUS)



# Deploys a `DefaultReserveInterestRateStrategy` with the default configuration.
def deploy_default_strategy(addresses_provider):
    return accounts[0].deploy(
        DefaultReserveInterestRateStrategy,
        addresses_provider,
        OPTIMAL_UTILIZATION_RATE,
        BASE_VARIABLE_BORROW_RATE,
        VARIABLE_RATE_SLOPE_1,
        VARIABLE_RATE_SLOPE_2,
        STABLE_RATE_SLOPE_1,
        STABLE_RATE_SLOPE_2,
    )


# Helper for testing `borrow()` functionality
# Makes a `depositer` deposit WETH
# Creates a `borrower` with a tERC20 allowance to the `LendingPool`
def setup_borrow():
    # Deploy and initialize contracts (initializes a weth reserve)
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy) = setup_and_deploy_configuration_with_reserve()

    # Create asset and give allowance to lending pool
    depositer = accounts[4]
    deposit_amount = 10_000_000_000_000_000_000
    weth.deposit({'from': depositer, 'value': deposit_amount})
    weth.approve(lending_pool.address, deposit_amount, {'from': depositer})

    # Turn on collateral and borrowing
    (weth_ltv, weth_threhold, weth_bonus) = allow_reserve_collateral_and_borrowing(configurator, weth, pool_admin)

    # Set market lending rate
    lending_rate_oracle.setMarketBorrowRate(weth.address, MARKET_BORROW_RATE)

    # `deposit()` weth
    lending_pool.deposit(weth.address, deposit_amount, depositer, 0, {'from': depositer})

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
    price_oracle.setAssetPrice(terc20.address, price, {'from': accounts[0]})

    # Create tERC20 tokens for `borrower` and deposit them into `LendingPool`
    borrower = accounts[5]
    terc20_deposit_amount = deposit_amount // 10
    terc20.mint(terc20_deposit_amount, {'from': borrower})
    terc20.approve(lending_pool.address, terc20_deposit_amount, {'from': borrower})
    lending_pool.deposit(terc20.address, terc20_deposit_amount, borrower, 0, {'from': borrower})

    return (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth, weth_atoken,
    weth_stable_debt, weth_variable_debt, strategy, depositer, deposit_amount, borrower,
    terc20, terc20_atoken, terc20_stable_debt, terc20_variable_debt, tecr20_ltv, tecr20_threshold, tecr20_bonus,
    terc20_deposit_amount, price)


#######################
# Calculation functions
#######################


# `WadRayMath.rayMul()`
def ray_mul(a, b):
    return (a * b + RAY // 2) // RAY


# `WadRayMath.rayDiv()`
def ray_div(a, b):
    return (a * RAY + b // 2) // b


# `WadRayMath.wadMul()`
def wad_mul(a, b):
    return (a * b + WAD // 2) // WAD


# `WadRayMath.wadDiv()`
def wad_div(a, b):
    return (a * WAD + b // 2) // b


# `WadRayMath.wadToRay()`
def wad_to_ray(a):
    return a * RAY_DIV_WAD


# `PercentMath.percentMul()`
def percent_mul(a, b):
    return (a * b + HALF_PERCENT) // PERCENTAGE_FACTOR



# `PercentMath.percentMul()`
def percent_div(a, b):
    return (a * PERCENTAGE_FACTOR + b // 2) // b


# Calculates the compound interest rate according to `MathUtils.calculateCompoundedInterest()`
# Note: `exp = currentTimestamp - lastUpdateTimestamp`
def calculate_compound_interest(rate, exp):
    if exp == 0:
        return RAY

    exp_minus_one = exp - 1

    exp_minus_two = 0
    if exp > 2:
        exp_minus_two = exp - 2

    rate_per_second = rate // SECONDS_PER_YEAR

    base_power_two = ray_mul(rate_per_second, rate_per_second)
    base_power_three = ray_mul(base_power_two, rate_per_second)

    second_term = exp * exp_minus_one * base_power_two // 2
    third_term = exp * exp_minus_one * exp_minus_two * base_power_three // 6

    return RAY + rate_per_second * exp + second_term + third_term


# Calculates the linear interest rate according to `MathUtils.calculateLinearInterest()`
def calculate_linear_interest(rate, time):
    return rate * time // SECONDS_PER_YEAR + RAY


# Stable Borrow Rate SRt
# See `DefaultReserveInterestRateStrategy.calculateInterestRates()`
def calculate_stable_borrow_rate(base_rate, slope_1, slope_2, utilization_rate, optimal_utilization_rate):
    borrow_rate = base_rate
    if utilization_rate <= optimal_utilization_rate:
        # base + Ut / Uoptimal * slope1
        borrow_rate += ray_mul(slope_1, ray_div(utilization_rate, optimal_utilization_rate))
    else:
        # base + slope1 + (Ut - Uoptimal) / (1 - Uoptimal) * slope2
        borrow_rate += slope_1 + ray_mul(ray_div(utilization_rate - optimal_utilization_rate, RAY - optimal_utilization_rate), slope_2)
    return borrow_rate


# Variable Borrow Rate VRt
# See `DefaultReserveInterestRateStrategy.calculateInterestRates()`
# Note: differs from stable rate due to order of operations which gives different rounding
def calculate_variable_borrow_rate(base_rate, slope_1, slope_2, utilization_rate, optimal_utilization_rate):
    if utilization_rate <= optimal_utilization_rate:
        # base + Ut / Uoptimal * slope1
        return base_rate + ray_div(ray_mul(utilization_rate, slope_1), optimal_utilization_rate)
    else:
        # base + slope1 + (Ut - Uoptimal) / (1 - Uoptimal) * slope2
        return base_rate + slope_1 + ray_mul(slope_2, ray_div(utilization_rate - optimal_utilization_rate, RAY - optimal_utilization_rate))


# Overall Stable Borrow Rate (increasing amount)
# prev_rate: ^SRt-1
# prev_total: SDt-1 *(1 + ^SRt-1/Tyear)^Tyear  previous total supply plus interest up until the current timestamp
# curr_rate: SRt the stable rate used for the borrow (set by the previous transaction's `updateInterestRates()`)
# amount: borrow amount
# isBorrow: bool - is the amount increasing the total (borrow) or decreasing the total (repay)
# See `StableDebtToken.mint()
def calculate_overall_stable_rate(prev_rate, prev_total, curr_rate, amount, isBorrow):
    if prev_total + amount == 0:
        return RAY

    if isBorrow:
        return ray_div(
            ray_mul(prev_rate, wad_to_ray(prev_total)) + ray_mul(curr_rate, wad_to_ray(amount)),
            wad_to_ray(prev_total + amount)
        )
    else:
        return ray_div(
            ray_mul(prev_rate, wad_to_ray(prev_total)) - ray_mul(curr_rate, wad_to_ray(amount)),
            wad_to_ray(prev_total - amount)
        )


# Overall Borrow Rate ^Rt
# See `DefaultReserveInterestRateStrategy._getOverallBorrowRate()`
def calculate_overall_borrow_rate(total_stable_debt, total_variable_debt, overall_stable_rate, variable_rate):
    total_debt = total_stable_debt + total_variable_debt
    if total_debt == 0:
        return 0

    weighted_stable_rate = ray_mul(wad_to_ray(total_stable_debt), overall_stable_rate)
    weighted_variable_rate = ray_mul(wad_to_ray(total_variable_debt), variable_rate)

    return ray_div(weighted_stable_rate + weighted_variable_rate, wad_to_ray(total_debt))
