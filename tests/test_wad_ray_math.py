from brownie import (
    accounts, reverts, WadRayMath,
)

from Crypto.Hash import keccak
from helpers import (WAD, RAY, ray_mul, ray_div)
import pytest

"""
Note: The functions in `WadRayMath` need their visibility changed to public for these tests.
This will break many other tests so turn these back to internal after and comment out the tests.
"""

#
# # Tests getters / constants
# def test_getters():
#     # Deploy `WadRayMath`
#     wad_ray_math = accounts[0].deploy(WadRayMath)
#
#     assert wad_ray_math.ray() == RAY
#     assert wad_ray_math.wad() == WAD
#     assert wad_ray_math.halfRay() == RAY // 2
#     assert wad_ray_math.halfWad() == WAD // 2
#
#
# # Test `wadMul()`
# def test_wad_mul():
#     # Deploy `WadRayMath`
#     wad_ray_math = accounts[0].deploy(WadRayMath)
#
#     # Multiply by zero
#     assert wad_ray_math.wadMul(0, 0) == 0
#     assert wad_ray_math.wadMul(0, WAD) == 0
#     assert wad_ray_math.wadMul(WAD, 0) == 0
#
#     # a * b = c // WAD
#     for (a, b, c) in [(1_000, 1_000, 0), (WAD, WAD, WAD), (3, WAD, 3), (WAD, 99, 99)]:
#         assert wad_ray_math.wadMul(a, b) == c
#
#     # Max values
#     for a in [1, 10, WAD, RAY]:
#         b = ((1 << 256) - 1 - WAD // 2) // a
#         assert wad_ray_math.wadMul(a, b) == (a * b + WAD // 2) // WAD
#         assert wad_ray_math.wadMul(b, a) == (a * b + WAD // 2) // WAD
#
#         with reverts('48'):
#             wad_ray_math.wadMul(b, a + 1)
#         with reverts('48'):
#             wad_ray_math.wadMul(b + 1, a)
#         with reverts('48'):
#             wad_ray_math.wadMul(a, b + 1)
#         with reverts('48'):
#             wad_ray_math.wadMul(a + 1, b)
#
#
# # Test `wadDiv()`
# def test_wad_div():
#     # Deploy `WadRayMath`
#     wad_ray_math = accounts[0].deploy(WadRayMath)
#
#     # a / b = c * WAD
#     for (a, b, c) in [(1_000 * WAD, 1_000 * WAD, WAD), (WAD, WAD, WAD), (1, WAD, 1), (WAD, 1, WAD**2)]:
#         assert wad_ray_math.wadDiv(a, b) == c
#
#     # Max values
#     for b in [1, 10, WAD, RAY]:
#         a = ((1 << 256) - 1 - b // 2) // WAD
#         assert wad_ray_math.wadDiv(a, b) == (a * WAD + b // 2) // b
#
#         with reverts('48'):
#             wad_ray_math.wadDiv(a + 1, b)
#
#     # Divide by zero
#     with reverts('50'):
#         wad_ray_math.wadDiv(0, 0)
#     with reverts('50'):
#         wad_ray_math.wadDiv(WAD, 0)
#
#
# # Test `rayMul()`
# def test_ray_mul():
#     # Deploy `WadRayMath`
#     wad_ray_math = accounts[0].deploy(WadRayMath)
#
#     # Multiply by zero
#     assert wad_ray_math.rayMul(0, 0) == 0
#     assert wad_ray_math.rayMul(0, RAY) == 0
#     assert wad_ray_math.rayMul(RAY, 0) == 0
#
#     # a * b = c // RAY
#     for (a, b, c) in [(1_000, 1_000, 0), (RAY, RAY, RAY), (3, RAY, 3), (RAY, 99, 99)]:
#         assert wad_ray_math.rayMul(a, b) == c
#
#     # Max values
#     for a in [1, 10, RAY, RAY]:
#         b = ((1 << 256) - 1 - RAY // 2) // a
#         assert wad_ray_math.rayMul(a, b) == (a * b + RAY // 2) // RAY
#         assert wad_ray_math.rayMul(b, a) == (a * b + RAY // 2) // RAY
#
#         with reverts('48'):
#             wad_ray_math.rayMul(b, a + 1)
#         with reverts('48'):
#             wad_ray_math.rayMul(b + 1, a)
#         with reverts('48'):
#             wad_ray_math.rayMul(a, b + 1)
#         with reverts('48'):
#             wad_ray_math.rayMul(a + 1, b)
#
#
# # Test `rayDiv()`
# def test_ray_div():
#     # Deploy `WadRayMath`
#     wad_ray_math = accounts[0].deploy(WadRayMath)
#
#     # a / b = c * RAY
#     for (a, b, c) in [(1_000 * RAY, 1_000 * RAY, RAY), (RAY, RAY, RAY), (1, RAY, 1), (RAY, 1, RAY**2)]:
#         assert wad_ray_math.rayDiv(a, b) == c
#
#     # Max values
#     for b in [1, 10, RAY, RAY]:
#         a = ((1 << 256) - 1 - b // 2) // RAY
#         assert wad_ray_math.rayDiv(a, b) == (a * RAY + b // 2) // b
#
#         with reverts('48'):
#             wad_ray_math.rayDiv(a + 1, b)
#
#     # Divide by zero
#     with reverts('50'):
#         wad_ray_math.rayDiv(0, 0)
#     with reverts('50'):
#         wad_ray_math.wadDiv(RAY, 0)
#
#
# # Test `rayToWad()`
# def test_ray_to_wad():
#     # Deploy `WadRayMath`
#     wad_ray_math = accounts[0].deploy(WadRayMath)
#
#     # Simple conversions
#     for i in [0, 1, 10, 10_000]:
#         assert wad_ray_math.rayToWad(i * RAY) == i * WAD
#
#     # Rounding
#     assert wad_ray_math.rayToWad(499_999_999) == 0
#     assert wad_ray_math.rayToWad(500_000_000) == 1
#     assert wad_ray_math.rayToWad(1_499_999_999) == 1
#
#     # Max Values
#     assert wad_ray_math.rayToWad((1 << 256) - 1 - (RAY // WAD // 2)) == ((1 << 256) - 1 + (RAY // WAD // 2)) // (RAY // WAD)
#     with reverts('49'):
#         wad_ray_math.rayToWad((1 << 256) - (RAY // WAD // 2))
#
#
# # Test `wadToRay()`
# def test_ray_to_wad():
#     # Deploy `WadRayMath`
#     wad_ray_math = accounts[0].deploy(WadRayMath)
#
#     ray_div_wad = RAY // WAD
#
#     # Simple conversions
#     for i in [0, 1, 10, 10_000]:
#         assert wad_ray_math.wadToRay(i) == i * ray_div_wad
#
#     # Max Values
#     assert wad_ray_math.wadToRay(((1 << 256) - 1) // ray_div_wad) == ((1 << 256) - 1) // ray_div_wad * ray_div_wad
#     with reverts('48'):
#         wad_ray_math.wadToRay(((1 << 256) - 1) // ray_div_wad + 1)
#
#
# # Test `rayMul()` then `rayDiv()` rounding
# # This is used when repaying a variable debt
# def test_ray_mul_div_rounding():
#     # Deploy `WadRayMath`
#     wad_ray_math = accounts[0].deploy(WadRayMath)
#
#     ray_div_wad = RAY // WAD
#
#     # Variable `repay` rounding
#     for (scaled, vi) in [(1, RAY), (2**32 - 1, RAY + RAY // 2), (2 * RAY - 1, int(RAY * 1.111)), ((1 << 90) - 1, (1 << 90) - 1), (RAY + 1, (1 << 90) - 1)]:
#          vd = ray_mul(scaled, vi)
#          scaled_round_trip = ray_div(vd, vi)
#          assert scaled == scaled_round_trip
