from brownie import (
    accounts, AToken, AaveOracle, AaveProtocolDataProvider, DelegationAwareAToken,
    DefaultReserveInterestRateStrategy, GenericLogic,
    LendingPool, LendingPoolAddressesProvider, LendingPoolConfigurator,
    LendingPoolAddressesProviderRegistry, LendingPoolCollateralManager,
    ReserveLogic, StableDebtToken, ValidationLogic, VariableDebtToken,
    WETH9, WETHGateway, ZERO_ADDRESS,
)
import helpers
from Crypto.Hash import keccak
import pytest


# Deployment of LendingPool
def test_deploy_lending_pool():
    # Dependent contracts
    accounts[0].deploy(ReserveLogic)
    accounts[0].deploy(GenericLogic)
    accounts[0].deploy(ValidationLogic)

    ### LendingPool ###
    lending_pool = accounts[0].deploy(LendingPool)

    # LendingPool constants and getters
    assert lending_pool.MAX_STABLE_RATE_BORROW_SIZE_PERCENT() == 2500
    assert lending_pool.FLASHLOAN_PREMIUM_TOTAL() == 9
    assert lending_pool.MAX_NUMBER_RESERVES() == 128
    assert lending_pool.LENDINGPOOL_REVISION() == 2
    empty_reserve_data = ((0,), 0, 0, 0, 0, 0, 0, ZERO_ADDRESS, ZERO_ADDRESS, ZERO_ADDRESS, ZERO_ADDRESS, 0)
    assert lending_pool.getReserveData(ZERO_ADDRESS) == empty_reserve_data
    assert lending_pool.getConfiguration(ZERO_ADDRESS) == (0,)
    assert lending_pool.getUserConfiguration(ZERO_ADDRESS) == (0,)
    assert lending_pool.getReserveNormalizedIncome(ZERO_ADDRESS) == 0
    assert lending_pool.getReserveNormalizedVariableDebt(ZERO_ADDRESS) == 0
    assert lending_pool.paused() == False
    assert lending_pool.getReservesList() == []
    assert lending_pool.getAddressesProvider() == ZERO_ADDRESS
    # assert lending_pool.getUserAccountData(accounts[1]) == (0, 0, 0, 0, 0, 0) reverts


# Deployment of WETH9
# Note: since we are using local testnet ganache ether we don't need to use WETH9Mocked.
def test_deploy_weth9():
    ### WETH9 ###
    weth9 = accounts[0].deploy(WETH9)

    # WETH9 constants and getters
    assert weth9.name() == 'Wrapped Ether'
    assert weth9.symbol() == 'WETH'
    assert weth9.decimals() == 18
    assert weth9.totalSupply() == 0


# Deployment of AToken
def test_deploy_atoken():
    # Dependent contracts
    accounts[0].deploy(ReserveLogic)
    accounts[0].deploy(GenericLogic)
    accounts[0].deploy(ValidationLogic)
    lending_pool = accounts[0].deploy(LendingPool)
    weth9 = accounts[0].deploy(WETH9)

    ### AToken ###
    atoken = accounts[0].deploy(
        AToken,
        lending_pool.address,
        weth9,
        ZERO_ADDRESS,
        'Aave interest bearing WETH',
        'aWETH',
        ZERO_ADDRESS
    )

    # AToken constants and getters
    assert atoken.POOL() == lending_pool.address
    assert atoken.UNDERLYING_ASSET_ADDRESS() == weth9.address
    assert atoken.RESERVE_TREASURY_ADDRESS() == ZERO_ADDRESS
    hasher = keccak.new(digest_bits=256)
    hasher.update(b'Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)')
    assert str(atoken.PERMIT_TYPEHASH())[2:] == hasher.hexdigest()


# Deployment of DelegationAwareAToken
def test_deploy_delegation_aware_atoken():
    # Dependent contracts
    accounts[0].deploy(ReserveLogic)
    accounts[0].deploy(GenericLogic)
    accounts[0].deploy(ValidationLogic)
    lending_pool = accounts[0].deploy(LendingPool)
    weth9 = accounts[0].deploy(WETH9)

    ### DelegationAwareAToken ###
    atoken = accounts[0].deploy(
        DelegationAwareAToken,
        lending_pool.address,
        weth9, ZERO_ADDRESS,
        'Aave interest bearing WETH',
        'aWETH',
        ZERO_ADDRESS
    )

    # DelegationAwareAToken constants and getters
    assert atoken.POOL() == lending_pool.address
    assert atoken.UNDERLYING_ASSET_ADDRESS() == weth9.address
    assert atoken.RESERVE_TREASURY_ADDRESS() == ZERO_ADDRESS
    hasher = keccak.new(digest_bits=256)
    hasher.update(b'Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)')
    assert str(atoken.PERMIT_TYPEHASH())[2:] == hasher.hexdigest()


# Deployment of DefaultReserveInterestRateStrategy
def test_deploy_default_reserve_interest_rates():
    # Dependent contracts
    accounts[0].deploy(ReserveLogic)
    accounts[0].deploy(GenericLogic)
    accounts[0].deploy(ValidationLogic)
    lending_pool = accounts[0].deploy(LendingPool)

    ### DefaultReserveInterestRateStrategy ###
    optimalUtilizationRate = 1
    baseVariableBorrowRate = 2
    variableRateSlope1 = 3
    variableRateSlope2 = 4
    stableRateSlope1 = 5
    stableRateSlope2 = 6
    drirs = accounts[0].deploy(
        DefaultReserveInterestRateStrategy,
        lending_pool.address,
        optimalUtilizationRate,
        baseVariableBorrowRate,
        variableRateSlope1,
        variableRateSlope2,
        stableRateSlope1,
        stableRateSlope2,
    )

    # DefaultReserveInterestRateStrategy constants and getters
    assert drirs.OPTIMAL_UTILIZATION_RATE() == optimalUtilizationRate
    assert drirs.EXCESS_UTILIZATION_RATE() == 1_000_000_000_000_000_000_000_000_000 - optimalUtilizationRate
    assert drirs.variableRateSlope1() == variableRateSlope1
    assert drirs.variableRateSlope2() == variableRateSlope2
    assert drirs.stableRateSlope1() == stableRateSlope1
    assert drirs.stableRateSlope2() == stableRateSlope2
    assert drirs.baseVariableBorrowRate() == baseVariableBorrowRate
    assert drirs.getMaxVariableBorrowRate() == baseVariableBorrowRate + variableRateSlope1 + variableRateSlope2


# Deployment of StableDebtToken
def test_deploy_stable_debt_token():
    # Dependent contracts
    accounts[0].deploy(ReserveLogic)
    accounts[0].deploy(GenericLogic)
    accounts[0].deploy(ValidationLogic)
    lending_pool = accounts[0].deploy(LendingPool)
    weth9 = accounts[0].deploy(WETH9)

    ### StableDebtToken ###
    stable_debt_token = accounts[0].deploy(
        StableDebtToken,
        lending_pool.address,
        weth9.address,
        'Aave stable debt bearing WETH',
        'stableDebtWETH',
        ZERO_ADDRESS,
    )

    # StableDebtToken constants and getters
    assert stable_debt_token.UNDERLYING_ASSET_ADDRESS() == weth9.address
    assert stable_debt_token.POOL() == lending_pool.address
    assert stable_debt_token.DEBT_TOKEN_REVISION() == 0x01
    assert stable_debt_token.getAverageStableRate() == 0
    assert stable_debt_token.getUserLastUpdated(accounts[0]) == 0
    assert stable_debt_token.getUserStableRate(accounts[0]) == 0
    assert stable_debt_token.balanceOf(accounts[0]) == 0
    assert stable_debt_token.getSupplyData() == (0, 0, 0, 0)
    assert stable_debt_token.getTotalSupplyAndAvgRate() == (0, 0)
    assert stable_debt_token.totalSupply() == 0
    assert stable_debt_token.getTotalSupplyLastUpdated() == 0
    assert stable_debt_token.principalBalanceOf(accounts[0]) == 0


# Deployment of VariableDebtToken
def test_deploy_variable_debt_token():
    # Dependent contracts
    accounts[0].deploy(ReserveLogic)
    accounts[0].deploy(GenericLogic)
    accounts[0].deploy(ValidationLogic)
    lending_pool = accounts[0].deploy(LendingPool)
    weth9 = accounts[0].deploy(WETH9)

    ### VariableDebtToken ###
    variable_debt_token = accounts[0].deploy(
        VariableDebtToken,
        lending_pool.address,
        weth9.address,
        'Aave stable debt bearing WETH',
        'stableDebtWETH',
        ZERO_ADDRESS,
    )

    # StableDebtToken constants and getters
    assert variable_debt_token.UNDERLYING_ASSET_ADDRESS() == weth9.address
    assert variable_debt_token.POOL() == lending_pool.address
    assert variable_debt_token.DEBT_TOKEN_REVISION() == 0x01
    assert variable_debt_token.balanceOf(accounts[0]) == 0
    assert variable_debt_token.scaledBalanceOf(accounts[0]) == 0
    assert variable_debt_token.totalSupply() == 0
    assert variable_debt_token.scaledTotalSupply() == 0
    assert variable_debt_token.getScaledUserBalanceAndSupply(accounts[0]) == (0, 0)


# Deployment of LendingPoolConfigurator
@pytest.mark.xfail(reason="CONFIGURATOR_REVISION is set to internal")
def test_deploy_lending_pool_configurator():
    ### LendingPoolConfigurator ###
    configurator = accounts[0].deploy(LendingPoolConfigurator)

    # LendingPoolConfigurator constants and getters
    assert configurator.CONFIGURATOR_REVISION() == 0x03 # this is internal when all others are public


# Deployment of LendingPoolAddressesProvider
def test_deploy_lending_pool_addresses_provider():
    ### LendingPoolAddressesProvider ###
    addresses_provider = accounts[0].deploy(LendingPoolAddressesProvider)

    # LendingPoolAddressesProvider constants and getters
    assert addresses_provider.getAddress(b'\x00' * 32) == ZERO_ADDRESS
    assert addresses_provider.getLendingPool() == ZERO_ADDRESS
    assert addresses_provider.getLendingPoolConfigurator() == ZERO_ADDRESS
    assert addresses_provider.getLendingPoolCollateralManager() == ZERO_ADDRESS
    assert addresses_provider.getPoolAdmin() == ZERO_ADDRESS
    assert addresses_provider.getEmergencyAdmin() == ZERO_ADDRESS
    assert addresses_provider.getPriceOracle() == ZERO_ADDRESS
    assert addresses_provider.getLendingRateOracle() == ZERO_ADDRESS


# Deployment of LendingPoolAddressesProviderRegistry
def test_deploy_lending_pool_addresses_provider_registry():
    addresses_provider_registry = accounts[0].deploy(LendingPoolAddressesProviderRegistry)

    # LendingPoolAddressesProviderRegistry constants and getters
    assert addresses_provider_registry.getAddressesProvidersList() == []
    assert addresses_provider_registry.getAddressesProviderIdByAddress(accounts[0]) == 0


# Deployment of LendingPoolCollateralManager
def test_deploy_lending_pool_collateral_manager():
    ### LendingPoolCollateralManager ###
    lending_pool_colalteral_manager = accounts[0].deploy(LendingPoolCollateralManager)

def test_deploy_aave_oracle():
    # Dependent contracts
    weth9 = accounts[0].deploy(WETH9)

    ### AaveOracle ###
    aave_oracle = accounts[0].deploy(
        AaveOracle,
        [],
        [],
        ZERO_ADDRESS,
        weth9.address
    )

    # AaveOracle constants and getters
    aave_oracle.getSourceOfAsset(weth9.address) == ZERO_ADDRESS
    aave_oracle.getFallbackOracle() == ZERO_ADDRESS


# Deployment of AaveProtocolDataProvider
def test_deploy_aave_protocol_data_provider():
    # Required Contracts
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle) = helpers.setup_and_deploy()

    ### AaveProtocolDataProvider ###
    data_provider = accounts[0].deploy(AaveProtocolDataProvider, addresses_provider.address)
    assert data_provider.getAllReservesTokens() == []
    assert data_provider.getAllATokens() == []
    assert data_provider.getReserveTokensAddresses(accounts[1]) == (ZERO_ADDRESS, ZERO_ADDRESS, ZERO_ADDRESS)


# Deployment of WETHGateway
def test_deploy_weth_gateway():
    # Required contracts
    (addresses_provider, lending_pool, configurator, collateral_manager,
    pool_admin, emergency_admin, price_oracle, lending_rate_oracle, weth9, atoken,
    stable_debt, variable_debt, strategy) = helpers.setup_and_deploy_configuration()

    ### WETHGateway ###
    gateway = accounts[0].deploy(WETHGateway, weth9.address, lending_pool.address)

    assert gateway.getWETHAddress() == weth9.address
    assert gateway.getLendingPoolAddress() == lending_pool.address
