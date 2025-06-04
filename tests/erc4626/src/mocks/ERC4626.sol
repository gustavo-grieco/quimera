pragma solidity ^0.8.0;

// SPDX-License-Identifier: UNLICENSED
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {ERC4626} from "@openzeppelin/contracts/token/ERC20/extensions/ERC4626.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract ERC4626Mock is ERC4626 {
    constructor(address underlying) ERC20("ERC4626Mock", "E4626M") ERC4626(IERC20(underlying)) {}

    function mint(address account, uint256 amount) external {
        _mint(account, amount);
    }
}
