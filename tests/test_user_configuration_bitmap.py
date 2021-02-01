from brownie import (
    accounts, reverts, UserConfigurationTest
)

import pytest
import time
import random


# Sanity test for the `setBorrowing()` function
def test_borrow_basic():
    # Deploy a UserConfiguration
    config = accounts[0].deploy(UserConfigurationTest)

    # Create an empty bitmap
    bitmap = 0

    # Set each index for borrowing
    for index in range(0,127):

        # Set the borrowing flag
        bitmap = config.setBorrowing(bitmap, index, True)

        assert config.isBorrowing(bitmap, index)

        # Select a random set and check the other flags are as expected
        for x in range(0,10):
            rand_index = random.randint(0,127)
            assert config.isBorrowing(bitmap,rand_index) == (rand_index <= index)
            assert config.isUsingAsCollateralOrBorrowing(bitmap,rand_index) == (rand_index <= index)

# Sanity test for the `setUsingAsCollateral()` function
def test_collateral_basic():
    # Deploy a UserConfiguration
    config = accounts[0].deploy(UserConfigurationTest)

    # Create an empty bitmap
    bitmap = 0

    # Set each index for borrowing
    for index in range(0,127):

        # Set the collateral flag
        bitmap = config.setUsingAsCollateral(bitmap, index, True)

        assert config.isUsingAsCollateral(bitmap, index)

        # Select a random set and check the other flags are as expected
        for x in range(0,10):
            rand_index = random.randint(0,127)
            assert config.isUsingAsCollateral(bitmap,rand_index) == (rand_index <= index)
            assert config.isUsingAsCollateralOrBorrowing(bitmap,rand_index) == (rand_index <= index)

# Randomly test a number of indexes and collateral/borrowing combination
def test_config_fuzz():

    # Deploy a UserConfiguration
    config = accounts[0].deploy(UserConfigurationTest)

    # Create an empty bitmap
    bitmap = 0

    # Test intensity the higher the number the longer the test runs but more permutations
    intensity_runs = 1000

    borrow_indicies = {}
    collateral_indicies = {}

    for x in range(0, intensity_runs):
        if x%(intensity_runs/10) == 0:
            print(str(x*100/intensity_runs) + "% testing")

        rand_index = random.randint(0,127)

        # 1 - Borrow
        # 2 - Remove Borrow
        # 3 - Use as collateral
        # 4 - Remove use as collateral
        operation = random.randint(0,4)


        if operation == 1:
            bitmap = config.setBorrowing(bitmap, rand_index, True)
            borrow_indicies[rand_index] = True
            print("Borrowing index:", rand_index)
        elif operation == 2:
            bitmap = config.setBorrowing(bitmap, rand_index, False)
            borrow_indicies[rand_index] = False
            print("Removing Borrowing index:", rand_index)
        elif operation == 3:
            bitmap = config.setUsingAsCollateral(bitmap, rand_index, True)
            collateral_indicies[rand_index] = True
            print("Collateral index:", rand_index)
        elif operation == 4:
            bitmap = config.setUsingAsCollateral(bitmap, rand_index, False)
            collateral_indicies[rand_index] = False
            print("Removing collateral index:", rand_index)
        print(bitmap, bin(bitmap))


    # Ensure the bitmap is as we expect

    print("Checking results")
    for index in range (0,127):

        borrow = borrow_indicies.get(index)
        print("Testing index: ", index)
        if borrow == True:
            assert config.isBorrowing(bitmap,index) == True
            assert config.isUsingAsCollateralOrBorrowing(bitmap,index) == True
        else:
            assert config.isBorrowing(bitmap,index) == False
        collateral = collateral_indicies.get(index)
        if collateral == True:
            assert config.isUsingAsCollateral(bitmap,index) == True
            assert config.isUsingAsCollateralOrBorrowing(bitmap,index) == True
        else:
            assert config.isUsingAsCollateral(bitmap,index) == False

