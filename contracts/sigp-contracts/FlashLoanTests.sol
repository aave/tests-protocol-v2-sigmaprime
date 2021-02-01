// SPDX-License-Identifier: agpl-3.0
pragma solidity 0.6.12;

import {ILendingPool} from '../interfaces/ILendingPool.sol';
import {IFlashLoanReceiver} from '../flashloan/interfaces/IFlashLoanReceiver.sol';
import {IERC20} from '../dependencies/openzeppelin/contracts/IERC20.sol';

contract FlashLoanTests is IFlashLoanReceiver {
  address public _lendingPool;

  constructor(address lendingPool) public {
    _lendingPool = lendingPool;
  }

  // Simplest execution
  function executeOperation(
    address[] calldata assets,
    uint256[] calldata amounts,
    uint256[] calldata premiums,
    address initiator,
    bytes calldata params
  ) override public returns (bool) {
    // `approve()` repay of flashloan
    for (uint256 i = 0; i < amounts.length; i++) {
      IERC20(assets[i]).approve(_lendingPool, amounts[i] + premiums[i]);
    }

    return true;
  }
}
