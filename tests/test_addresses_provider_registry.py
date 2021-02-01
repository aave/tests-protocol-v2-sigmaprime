from brownie import (
    accounts, AToken, AaveOracle, DelegationAwareAToken,
    DefaultReserveInterestRateStrategy, GenericLogic,
    LendingPool, LendingPool2, LendingPoolAddressesProvider, LendingPoolConfigurator,
    LendingPoolAddressesProviderRegistry, LendingPoolCollateralManager,
    ReserveLogic, reverts, StableDebtToken, ValidationLogic, VariableDebtToken,
    WETH9, ZERO_ADDRESS,
)

from Crypto.Hash import keccak
import pytest


# Test `registerAddressesProvider()`
def test_registry_register_addresses_provider():
    # Dependent contracts
    addresses_provider = accounts[0].deploy(LendingPoolAddressesProvider)
    addresses_provider_2 = accounts[0].deploy(LendingPoolAddressesProvider)

    ### LendingPoolAddressProviderRegistry ###
    registry = accounts[0].deploy(LendingPoolAddressesProviderRegistry)

    # Pre-checks
    assert registry.getAddressesProvidersList() == []

    # registerAddressesProvider()
    id = 1
    tx = registry.registerAddressesProvider(addresses_provider.address, id)

    # Verify logs
    tx.events['AddressesProviderRegistered']['newAddress'] == addresses_provider.address

    # Check the list has been updated
    assert registry.getAddressesProvidersList() == [addresses_provider.address]
    assert registry.getAddressesProviderIdByAddress(addresses_provider.address) == id

    # Add a second provider
    id = 2
    tx = registry.registerAddressesProvider(addresses_provider_2.address, id)

    # Verify logs
    tx.events['AddressesProviderRegistered']['newAddress'] == addresses_provider_2.address

    # Check the list has been updated
    assert registry.getAddressesProvidersList() == [addresses_provider.address, addresses_provider_2.address]
    assert registry.getAddressesProviderIdByAddress(addresses_provider_2.address) == id


# Test `unregisterAddressesProvider()`
def test_registry_unregister_addresses_provider():
    # Dependent contracts
    addresses_provider = accounts[0].deploy(LendingPoolAddressesProvider)
    addresses_provider_2 = accounts[0].deploy(LendingPoolAddressesProvider)

    ### LendingPoolAddressProviderRegistry ###
    registry = accounts[0].deploy(LendingPoolAddressesProviderRegistry)

    # Pre-checks
    assert registry.getAddressesProvidersList() == []

    # registerAddressesProvider()
    id = 1
    tx = registry.registerAddressesProvider(addresses_provider.address, id)

    # Check the list has been updated
    assert registry.getAddressesProviderIdByAddress(addresses_provider.address) == id

    # unregisterAddressesProvider()
    tx = registry.unregisterAddressesProvider(addresses_provider.address)

    # Verify logs
    tx.events['AddressesProviderUnregistered']['newAddress'] == addresses_provider.address

    # Check the list has been updated
    assert registry.getAddressesProvidersList() == [ZERO_ADDRESS]
    assert registry.getAddressesProviderIdByAddress(addresses_provider.address) == 0


# Test numerous registers and unregisters
def test_registry_multiple():
    ### LendingPoolAddressProviderRegistry ###
    registry = accounts[0].deploy(LendingPoolAddressesProviderRegistry)

    # Pre-checks
    assert registry.getAddressesProvidersList() == []

    # registerAddressesProvider()
    id = 1
    tx = registry.registerAddressesProvider(accounts[1], id)

    # Check the list has been updated
    assert registry.getAddressesProviderIdByAddress(accounts[1]) == id
    assert registry.getAddressesProvidersList() == [accounts[1]]

    # registerAddressesProvider()
    id = 2
    tx = registry.registerAddressesProvider(accounts[2], id)

    # Check the list has been updated
    assert registry.getAddressesProviderIdByAddress(accounts[2]) == id
    assert registry.getAddressesProvidersList() == [accounts[1], accounts[2]]

    # registerAddressesProvider()
    id = 3
    tx = registry.registerAddressesProvider(accounts[3], id)

    # Check the list has been updated
    assert registry.getAddressesProviderIdByAddress(accounts[3]) == id
    assert registry.getAddressesProvidersList() == [accounts[1], accounts[2], accounts[3]]

    # unregisterAddressesProvider()
    tx = registry.unregisterAddressesProvider(accounts[2])

    # Check the list has been updated
    assert registry.getAddressesProviderIdByAddress(accounts[2]) == 0
    assert registry.getAddressesProvidersList() == [accounts[1], ZERO_ADDRESS, accounts[3]]

    # unregisterAddressesProvider()
    tx = registry.unregisterAddressesProvider(accounts[1])

    # Check the list has been updated
    assert registry.getAddressesProviderIdByAddress(accounts[1]) == 0
    assert registry.getAddressesProvidersList() == [ZERO_ADDRESS, ZERO_ADDRESS, accounts[3]]

    # registerAddressesProvider()
    id = 1
    tx = registry.registerAddressesProvider(accounts[2], id)

    # Check the list has been updated
    assert registry.getAddressesProviderIdByAddress(accounts[2]) == id
    assert registry.getAddressesProvidersList() == [ZERO_ADDRESS, accounts[2], accounts[3]]


# Test register the same ID twice
@pytest.mark.xfail(reason='Allows teh same id to be used multiple times')
def test_registry_id_twice():
    # Dependent contracts
    addresses_provider = accounts[0].deploy(LendingPoolAddressesProvider)
    addresses_provider_2 = accounts[0].deploy(LendingPoolAddressesProvider)

    ### LendingPoolAddressProviderRegistry ###
    registry = accounts[0].deploy(LendingPoolAddressesProviderRegistry)

    # Pre-checks
    assert registry.getAddressesProvidersList() == []

    # registerAddressesProvider()
    id = 1
    tx = registry.registerAddressesProvider(addresses_provider.address, id)

    # Add a second provider with the same id
    with reverts():
        registry.registerAddressesProvider(addresses_provider_2.address, id)


# Test register the same address twice
def test_registry_register_address_twice():
    # Dependent contracts
    addresses_provider = accounts[0].deploy(LendingPoolAddressesProvider)

    ### LendingPoolAddressProviderRegistry ###
    registry = accounts[0].deploy(LendingPoolAddressesProviderRegistry)

    # registerAddressesProvider()
    id = 1
    tx = registry.registerAddressesProvider(addresses_provider.address, id)

    # Verify logs
    tx.events['AddressesProviderRegistered']['newAddress'] == addresses_provider.address

    # Check the list has been updated
    assert registry.getAddressesProvidersList() == [addresses_provider.address]
    assert registry.getAddressesProviderIdByAddress(addresses_provider.address) == id

    # Add a second provider, with same address
    id = 2
    registry.registerAddressesProvider(addresses_provider.address, id)

    # Verify logs
    tx.events['AddressesProviderRegistered']['newAddress'] == addresses_provider.address

    # Check the list has been updated
    assert registry.getAddressesProvidersList() == [addresses_provider.address]
    assert registry.getAddressesProviderIdByAddress(addresses_provider.address) == id


# Test register the same address twice and same id
def test_registry_register_address_and_id_twice():
    # Dependent contracts
    addresses_provider = accounts[0].deploy(LendingPoolAddressesProvider)

    ### LendingPoolAddressProviderRegistry ###
    registry = accounts[0].deploy(LendingPoolAddressesProviderRegistry)

    # registerAddressesProvider()
    id = 1
    tx = registry.registerAddressesProvider(addresses_provider.address, id)

    # Verify logs
    tx.events['AddressesProviderRegistered']['newAddress'] == addresses_provider.address

    # Check the list has been updated
    assert registry.getAddressesProvidersList() == [addresses_provider.address]
    assert registry.getAddressesProviderIdByAddress(addresses_provider.address) == id

    # Add a second provider, with same address and id
    registry.registerAddressesProvider(addresses_provider.address, id)

    # Verify logs
    tx.events['AddressesProviderRegistered']['newAddress'] == addresses_provider.address

    # Check the list has been updated
    assert registry.getAddressesProvidersList() == [addresses_provider.address]
    assert registry.getAddressesProviderIdByAddress(addresses_provider.address) == id


# Test unregister the same address twice
def test_registry_unregister_address_twice():
    # Dependent contracts
    addresses_provider = accounts[0].deploy(LendingPoolAddressesProvider)

    ### LendingPoolAddressProviderRegistry ###
    registry = accounts[0].deploy(LendingPoolAddressesProviderRegistry)

    # registerAddressesProvider()
    id = 1
    tx = registry.registerAddressesProvider(addresses_provider.address, id)

    # Unregister the address twice
    registry.unregisterAddressesProvider(addresses_provider.address)
    with reverts('41'):
        registry.unregisterAddressesProvider(addresses_provider.address)


# Test register id 0
def test_registry_register_id_zero():
    # Dependent contracts
    addresses_provider = accounts[0].deploy(LendingPoolAddressesProvider)

    ### LendingPoolAddressProviderRegistry ###
    registry = accounts[0].deploy(LendingPoolAddressesProviderRegistry)

    # registerAddressesProvider() with id 0
    id = 0
    with reverts('72'):
        registry.registerAddressesProvider(addresses_provider.address, id)


# Test register multiple addresses
# Note: to run this test increase the number of ganache accounts to 1,000
# the test will run for a few minutes
@pytest.mark.skip()
def test_registry_register_max():
    ### LendingPoolAddressProviderRegistry ###
    registry = accounts[0].deploy(LendingPoolAddressesProviderRegistry)

    # registerAddressesProvider()
    for i in range(1, 1000):
        tx = registry.registerAddressesProvider(accounts[i], i)
        # gas limit of 1_000_000 is reached at 455 addresses
        # So 12_000_000 would be about 5000 addresses
        registry.getAddressesProvidersList({'from': accounts[1], 'gas': 1_000_000})

        print(i)
