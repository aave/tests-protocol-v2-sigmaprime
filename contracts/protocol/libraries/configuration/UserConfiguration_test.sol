// SPDX-License-Identifier: agpl-3.0
pragma solidity 0.6.12;

import {Errors} from '../helpers/Errors.sol';

/**
 * @title UserConfiguration library
 * @author Aave
 * @notice Implements the bitmap logic to handle the user configuration
 */
// This is a testing library. The visibility modifiers have been set to
// public. And the map is set as a standard uint256 to pass to parameters.
library UserConfigurationTest {
  uint256 internal constant BORROWING_MASK =
    0x5555555555555555555555555555555555555555555555555555555555555555;

  struct Map {
    uint256 data;
  }

  /**
   * @dev sets if the user is borrowing the reserve identified by reserveIndex
   * @param data the configuration object
   * @param reserveIndex the index of the reserve in the bitmap
   * @param borrowing true if the user is borrowing the reserve, false otherwise
   **/
  function setBorrowing(
    uint256 data,
    uint256 reserveIndex,
    bool borrowing
  ) public pure returns (uint256) {
    require(reserveIndex < 128, Errors.UL_INVALID_INDEX);
    return (data & ~(1 << (reserveIndex * 2))) |
      (uint256(borrowing ? 1 : 0) << (reserveIndex * 2));
  }

  /**
   * @dev sets if the user is using as collateral the reserve identified by reserveIndex
   * @param data the configuration object
   * @param reserveIndex the index of the reserve in the bitmap
   * @param _usingAsCollateral true if the user is usin the reserve as collateral, false otherwise
   **/
  function setUsingAsCollateral(
    uint256 data,
    uint256 reserveIndex,
    bool _usingAsCollateral
  ) public pure returns (uint256) {
    require(reserveIndex < 128, Errors.UL_INVALID_INDEX);
    return
      (data & ~(1 << (reserveIndex * 2 + 1))) |
      (uint256(_usingAsCollateral ? 1 : 0) << (reserveIndex * 2 + 1));
  }

  /**
   * @dev used to validate if a user has been using the reserve for borrowing or as collateral
   * @param data the configuration object
   * @param reserveIndex the index of the reserve in the bitmap
   * @return true if the user has been using a reserve for borrowing or as collateral, false otherwise
   **/
  function isUsingAsCollateralOrBorrowing(uint256 data, uint256 reserveIndex)
   public
    pure
    returns (bool)
  {
    require(reserveIndex < 128, Errors.UL_INVALID_INDEX);
    return (data >> (reserveIndex * 2)) & 3 != 0;
  }

  /**
   * @dev used to validate if a user has been using the reserve for borrowing
   * @param data the configuration object
   * @param reserveIndex the index of the reserve in the bitmap
   * @return true if the user has been using a reserve for borrowing, false otherwise
   **/
  function isBorrowing(uint256 data, uint256 reserveIndex)
   public
    pure
    returns (bool)
  {
    require(reserveIndex < 128, Errors.UL_INVALID_INDEX);
    return (data >> (reserveIndex * 2)) & 1 != 0;
  }

  /**
   * @dev used to validate if a user has been using the reserve as collateral
   * @param data the configuration object
   * @param reserveIndex the index of the reserve in the bitmap
   * @return true if the user has been using a reserve as collateral, false otherwise
   **/
  function isUsingAsCollateral(uint256 data, uint256 reserveIndex)
   public
    pure
    returns (bool)
  {
    require(reserveIndex < 128, Errors.UL_INVALID_INDEX);
    return (data >> (reserveIndex * 2 + 1)) & 1 != 0;
  }

  /**
   * @dev used to validate if a user has been borrowing from any reserve
   * @param data the configuration object
   * @return true if the user has been borrowing any reserve, false otherwise
   **/
  function isBorrowingAny(uint256 data) public pure returns (bool) {
    return data & BORROWING_MASK != 0;
  }

  /**
   * @dev used to validate if a user has not been using any reserve
   * @param data the configuration object
   * @return true if the user has been borrowing any reserve, false otherwise
   **/
  function isEmpty(uint256 data) public pure returns (bool) {
    return data == 0;
  }
}
