from brownie import (
    accounts, GenericLogic, LendingPool, LendingPool2,
    LendingPoolAddressesProvider, LendingPoolConfigurator,
    LendingPoolCollateralManager, ReserveLogic, reverts, ValidationLogic,
    ZERO_ADDRESS,
)

from Crypto.Hash import keccak
import pytest

# Takes bytes and increases the length to 32 by appending zero bytes.
def increase_bytes_to_32(in_bytes):
    if (len(in_bytes) > 32):
        raise ValueError("Too long")

    return in_bytes + b'\x00' * (32 - len(in_bytes))


# Test `setLendingPool()`
def test_addresses_provider_set_lending_pool():
    # Dependent contracts
    accounts[0].deploy(ReserveLogic)
    accounts[0].deploy(GenericLogic)
    accounts[0].deploy(ValidationLogic)
    lending_pool = accounts[0].deploy(LendingPool)


    ### LendingPoolAddressProvider ###
    owner = accounts[0]
    addresses_provider = owner.deploy(LendingPoolAddressesProvider)

    # Pre-checks
    lending_pool_id_bytes = increase_bytes_to_32(b'LENDING_POOL')
    assert addresses_provider.getLendingPool() == ZERO_ADDRESS
    assert addresses_provider.getAddress(lending_pool_id_bytes) == ZERO_ADDRESS

    # setLendingPoolImpl()
    tx = addresses_provider.setLendingPoolImpl(lending_pool.address)

    # Verify logs
    assert tx.events['LendingPoolUpdated']['newAddress'] == lending_pool.address, "Underlying address incorrect"
    assert tx.events['ProxyCreated']['newAddress'] != ZERO_ADDRESS, "Proxy not created"
    assert tx.events['ProxyCreated']['id'].hex() == lending_pool_id_bytes.hex(), "Invalid id"
    lending_pool_proxy_address = tx.events['ProxyCreated']['newAddress']

    # Verify getters
    assert addresses_provider.getLendingPool() == lending_pool_proxy_address, "invalid proxy address"
    assert addresses_provider.getAddress(lending_pool_id_bytes) == lending_pool_proxy_address, "invalid proxy address"

    # Create a second `LendingPool` but with a higher revision to pass `initialize()`
    lending_pool_2 = accounts[0].deploy(LendingPool2)

    # setLendingPoolImpl() a second time
    tx = addresses_provider.setLendingPoolImpl(lending_pool_2.address)

    # Verify logs
    assert tx.events['LendingPoolUpdated']['newAddress'] == lending_pool_2.address, "Underlying address incorrect"

    # Verify getters
    assert addresses_provider.getLendingPool() == lending_pool_proxy_address, "proxy address should not change"
    assert addresses_provider.getAddress(lending_pool_id_bytes) == lending_pool_proxy_address, "proxy address should not change"


# Test `setAddressAsProxy()`
def test_addresses_provider_set_address_as_proxy():
    # Dependent contracts
    accounts[0].deploy(ReserveLogic)
    accounts[0].deploy(GenericLogic)
    accounts[0].deploy(ValidationLogic)
    lending_pool = accounts[0].deploy(LendingPool)


    ### LendingPoolAddressProvider ###
    owner = accounts[0]
    addresses_provider = owner.deploy(LendingPoolAddressesProvider)

    # Pre-checks
    lending_pool_id_bytes = increase_bytes_to_32(b'LENDING_POOL')
    assert addresses_provider.getLendingPool() == ZERO_ADDRESS
    assert addresses_provider.getAddress(lending_pool_id_bytes) == ZERO_ADDRESS

    # setAddressAsProxy()
    tx = addresses_provider.setAddressAsProxy(lending_pool_id_bytes, lending_pool.address)

    # Verify logs
    assert tx.events['AddressSet']['newAddress'] == lending_pool.address, "Underlying address incorrect"
    assert tx.events['AddressSet']['hasProxy'] == True, "Underlying address incorrect"
    assert tx.events['AddressSet']['id'].hex() == lending_pool_id_bytes.hex(), "Invalid id"
    assert tx.events['ProxyCreated']['newAddress'] != ZERO_ADDRESS, "Proxy not created"
    assert tx.events['ProxyCreated']['id'].hex() == lending_pool_id_bytes.hex(), "Invalid id"
    lending_pool_proxy_address = tx.events['ProxyCreated']['newAddress']

    # Verify getters
    assert addresses_provider.getLendingPool() == lending_pool_proxy_address, "invalid proxy address"
    assert addresses_provider.getAddress(lending_pool_id_bytes) == lending_pool_proxy_address, "invalid proxy address"

    # Create a second `LendingPool` but with a higher revision to pass `initialize()`
    lending_pool_2 = accounts[0].deploy(LendingPool2)

    # setAddressAsProxy() a second time
    tx = addresses_provider.setAddressAsProxy(lending_pool_id_bytes, lending_pool_2.address)

    # Verify logs
    assert tx.events['AddressSet']['newAddress'] == lending_pool_2.address, "Underlying address incorrect"
    assert tx.events['AddressSet']['hasProxy'] == True, "Underlying address incorrect"
    assert tx.events['AddressSet']['id'].hex() == lending_pool_id_bytes.hex(), "Invalid id"

    # Verify getters
    assert addresses_provider.getLendingPool() == lending_pool_proxy_address, "proxy address should not change"
    assert addresses_provider.getAddress(lending_pool_id_bytes) == lending_pool_proxy_address, "proxy address should not change"


# Test `setLendingPoolConfiguratorImpl()`
def test_addresses_provider_set_lending_pool_configurator():
    # Dependent contracts
    configurator = accounts[0].deploy(LendingPoolConfigurator)


    ### LendingPoolAddressProvider ###
    owner = accounts[0]
    addresses_provider = owner.deploy(LendingPoolAddressesProvider)

    # Pre-checks
    configurator_id_bytes = increase_bytes_to_32(b'LENDING_POOL_CONFIGURATOR')
    assert addresses_provider.getLendingPoolConfigurator() == ZERO_ADDRESS
    assert addresses_provider.getAddress(configurator_id_bytes) == ZERO_ADDRESS

    # setLendingPoolConfiguratorImpl()
    tx = addresses_provider.setLendingPoolConfiguratorImpl(configurator.address)

    # Verify logs
    assert tx.events['LendingPoolConfiguratorUpdated']['newAddress'] == configurator.address, "Underlying address incorrect"
    assert tx.events['ProxyCreated']['newAddress'] != ZERO_ADDRESS, "Proxy not created"
    assert tx.events['ProxyCreated']['id'].hex() == configurator_id_bytes.hex(), "Invalid id"
    configurator_proxy_address = tx.events['ProxyCreated']['newAddress']

    # Verify getters
    assert addresses_provider.getLendingPoolConfigurator() == configurator_proxy_address, "invalid proxy address"
    assert addresses_provider.getAddress(configurator_id_bytes) == configurator_proxy_address, "invalid proxy address"


# Test `setLendingPoolCollateralManager()`
def test_addresses_provider_set_lending_pool_collateral_manager():
    # Dependent contracts
    collateral_manager = accounts[0].deploy(LendingPoolCollateralManager)


    ### LendingPoolAddressProvider ###
    owner = accounts[0]
    addresses_provider = owner.deploy(LendingPoolAddressesProvider)

    # Pre-checks
    collateral_manager_id_bytes = increase_bytes_to_32(b'COLLATERAL_MANAGER')
    assert addresses_provider.getLendingPoolCollateralManager() == ZERO_ADDRESS
    assert addresses_provider.getAddress(collateral_manager_id_bytes) == ZERO_ADDRESS

    # setLendingPoolCollateralManager()
    tx = addresses_provider.setLendingPoolCollateralManager(collateral_manager.address)

    # Verify logs
    assert tx.events['LendingPoolCollateralManagerUpdated']['newAddress'] == collateral_manager.address, "Address incorrect"

    # Verify getters
    assert addresses_provider.getLendingPoolCollateralManager() == collateral_manager.address, "invalid address"
    assert addresses_provider.getAddress(collateral_manager_id_bytes) == collateral_manager.address, "invalid address"

    # Create a second collateral manager
    collateral_manager_2 = accounts[0].deploy(LendingPoolCollateralManager)

    # setLendingPoolCollateralManager()
    tx = addresses_provider.setLendingPoolCollateralManager(collateral_manager_2.address)

    # Verify logs
    assert tx.events['LendingPoolCollateralManagerUpdated']['newAddress'] == collateral_manager_2.address, "Address incorrect"

    # Verify getters
    assert addresses_provider.getLendingPoolCollateralManager() == collateral_manager_2.address, "invalid address"
    assert addresses_provider.getAddress(collateral_manager_id_bytes) == collateral_manager_2.address, "invalid address"


# Test `setPoolAdmin()`
def test_addresses_provider_set_pool_admin():
    ### LendingPoolAddressProvider ###
    owner = accounts[0]
    addresses_provider = owner.deploy(LendingPoolAddressesProvider)

    # Pre-checks
    pool_admin_id_bytes = increase_bytes_to_32(b'POOL_ADMIN')
    assert addresses_provider.getPoolAdmin() == ZERO_ADDRESS
    assert addresses_provider.getAddress(pool_admin_id_bytes) == ZERO_ADDRESS

    # setPoolAdmin()
    admin = accounts[3]
    tx = addresses_provider.setPoolAdmin(admin)

    # Verify logs
    assert tx.events['ConfigurationAdminUpdated']['newAddress'] == admin, "Address incorrect"

    # Verify getters
    assert addresses_provider.getPoolAdmin() == admin, "invalid address"
    assert addresses_provider.getAddress(pool_admin_id_bytes) == admin, "invalid address"


# Test `setEmergencyAdmin()`
def test_addresses_provider_set_emergency_admin():
    ### LendingPoolAddressProvider ###
    owner = accounts[0]
    addresses_provider = owner.deploy(LendingPoolAddressesProvider)

    # Pre-checks
    emergency_admin_id_bytes = increase_bytes_to_32(b'EMERGENCY_ADMIN')
    assert addresses_provider.getEmergencyAdmin() == ZERO_ADDRESS
    assert addresses_provider.getAddress(emergency_admin_id_bytes) == ZERO_ADDRESS

    # setEmergencyAdmin()
    admin = accounts[3]
    tx = addresses_provider.setEmergencyAdmin(admin)

    # Verify logs
    assert tx.events['EmergencyAdminUpdated']['newAddress'] == admin, "Address incorrect"

    # Verify getters
    assert addresses_provider.getEmergencyAdmin() == admin, "invalid address"
    assert addresses_provider.getAddress(emergency_admin_id_bytes) == admin, "invalid address"


# Test `setPriceOracle()`
def test_addresses_provider_set_price_oracle():
    ### LendingPoolAddressProvider ###
    owner = accounts[0]
    addresses_provider = owner.deploy(LendingPoolAddressesProvider)

    # Pre-checks
    oracle_id_bytes = increase_bytes_to_32(b'PRICE_ORACLE')
    assert addresses_provider.getPriceOracle() == ZERO_ADDRESS
    assert addresses_provider.getAddress(oracle_id_bytes) == ZERO_ADDRESS

    # setPriceOracle()
    oracle = accounts[3]
    tx = addresses_provider.setPriceOracle(oracle)

    # Verify logs
    assert tx.events['PriceOracleUpdated']['newAddress'] == oracle, "Address incorrect"

    # Verify getters
    assert addresses_provider.getPriceOracle() == oracle, "invalid address"
    assert addresses_provider.getAddress(oracle_id_bytes) == oracle, "invalid address"


# Test `setLendingRateOracle()`
def test_addresses_provider_set_lending_rate_oracle():
    ### LendingPoolAddressProvider ###
    owner = accounts[0]
    addresses_provider = owner.deploy(LendingPoolAddressesProvider)

    # Pre-checks
    oracle_id_bytes = increase_bytes_to_32(b'LENDING_RATE_ORACLE')
    assert addresses_provider.getLendingRateOracle() == ZERO_ADDRESS
    assert addresses_provider.getAddress(oracle_id_bytes) == ZERO_ADDRESS

    # setLendingRateOracle()
    oracle = accounts[3]
    tx = addresses_provider.setLendingRateOracle(oracle)

    # Verify logs
    assert tx.events['LendingRateOracleUpdated']['newAddress'] == oracle, "Address incorrect"

    # Verify getters
    assert addresses_provider.getLendingRateOracle() == oracle, "invalid address"
    assert addresses_provider.getAddress(oracle_id_bytes) == oracle, "invalid address"

    # Update the oracle again
    oracle_2 = accounts[5]
    tx = addresses_provider.setLendingRateOracle(oracle_2)

    # Verify logs
    assert tx.events['LendingRateOracleUpdated']['newAddress'] == oracle_2, "Address incorrect"

    # Verify getters
    assert addresses_provider.getLendingRateOracle() == oracle_2, "invalid address"
    assert addresses_provider.getAddress(oracle_id_bytes) == oracle_2, "invalid address"


# Test `setAddress()`
def test_addresses_provider_set_address():
    ### LendingPoolAddressProvider ###
    owner = accounts[0]
    addresses_provider = owner.deploy(LendingPoolAddressesProvider)

    # Pre-checks
    oracle_id_bytes = increase_bytes_to_32(b'LENDING_RATE_ORACLE')
    assert addresses_provider.getLendingRateOracle() == ZERO_ADDRESS
    assert addresses_provider.getAddress(oracle_id_bytes) == ZERO_ADDRESS

    # setAddress()
    oracle = accounts[3]
    tx = addresses_provider.setAddress(oracle_id_bytes, oracle)

    # Verify logs
    assert tx.events['AddressSet']['id'].hex() == oracle_id_bytes.hex(), "ID incorrect"
    assert tx.events['AddressSet']['newAddress'] == oracle, "Address incorrect"
    assert tx.events['AddressSet']['hasProxy'] == False, "hasProxy incorrect"

    # Verify getters
    assert addresses_provider.getLendingRateOracle() == oracle, "invalid address"
    assert addresses_provider.getAddress(oracle_id_bytes) == oracle, "invalid address"

    # Update the oracle again
    oracle_2 = accounts[5]
    tx = addresses_provider.setAddress(oracle_id_bytes, oracle_2)

    # Verify logs
    assert tx.events['AddressSet']['id'].hex() == oracle_id_bytes.hex(), "ID incorrect"
    assert tx.events['AddressSet']['newAddress'] == oracle_2, "Address incorrect"
    assert tx.events['AddressSet']['hasProxy'] == False, "hasProxy incorrect"

    # Verify getters
    assert addresses_provider.getLendingRateOracle() == oracle_2, "invalid address"
    assert addresses_provider.getAddress(oracle_id_bytes) == oracle_2, "invalid address"


##################
# Malicious Tests
##################


# Test `onlyOwner()`
def test_addresses_provider_only_owner():
    # Dependent contracts
    accounts[0].deploy(ReserveLogic)
    accounts[0].deploy(GenericLogic)
    accounts[0].deploy(ValidationLogic)
    lending_pool = accounts[0].deploy(LendingPool)


    ### LendingPoolAddressProvider ###
    owner = accounts[0]
    addresses_provider = owner.deploy(LendingPoolAddressesProvider)

    # Pre-checks
    lending_pool_id_bytes = increase_bytes_to_32(b'LENDING_POOL')
    assert addresses_provider.getLendingPool() == ZERO_ADDRESS
    assert addresses_provider.getAddress(lending_pool_id_bytes) == ZERO_ADDRESS

    # setLendingPoolImpl() not from the owner
    with reverts("Ownable: caller is not the owner"):
        addresses_provider.setLendingPoolImpl(lending_pool.address, {'from': accounts[5]})


# Test overwriting a proxy address
@pytest.mark.xfail(reason='Overwrites proxy address')
def test_proxy_overwrite():
    # Dependent contracts
    accounts[0].deploy(ReserveLogic)
    accounts[0].deploy(GenericLogic)
    accounts[0].deploy(ValidationLogic)
    lending_pool = accounts[0].deploy(LendingPool)

    ### LendingPoolAddressProvider ###
    owner = accounts[0]
    addresses_provider = owner.deploy(LendingPoolAddressesProvider)

    # setLendingPoolImpl()
    tx = addresses_provider.setLendingPoolImpl(lending_pool.address)

    # Check we're upgraded to a proxy
    lending_pool_proxy_address = tx.events['ProxyCreated']['newAddress']
    assert addresses_provider.getLendingPool() == lending_pool_proxy_address, "invalid proxy address"

    # Overwrite the proxy
    lending_pool_id_bytes = increase_bytes_to_32(b'LENDING_POOL')
    tx = addresses_provider.setAddress(lending_pool_id_bytes, lending_pool.address)

    # Check update was successful
    assert addresses_provider.getLendingPool() == lending_pool.address, "invalid address"

    # Attempt to lending pool to proxy proxy again (which fails)
    addresses_provider.setLendingPoolImpl(lending_pool.address)
