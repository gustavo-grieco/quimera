// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;
import {Test, console} from "forge-std/Test.sol";
import {ERC4626Mock} from "../../src/mocks/ERC4626.sol";

interface IWETH {
    function deposit() external payable;
    function transfer(address to, uint256 value) external returns (bool);
    function approve(address guy, uint256 wad) external returns (bool);
    function withdraw(uint256 wad) external;
    function balanceOf(address) external view returns (uint256);
}

interface IBalancerVault {
    function flashLoan(
        address recipient,
        address[] memory tokens,
        uint256[] memory amounts,
        bytes memory userData
    ) external;
}

interface IDODO {
    function flashLoan(
        uint256 loanAmount,
        uint256 feeAmount,
        address receiver,
        bytes calldata data
    ) external;
}


interface IERC20 {
    function approve(address guy, uint256 wad) external returns (bool);
    function balanceOf(address) external view returns (uint256);
    function transfer(address to, uint256 value) external returns (bool);
}

contract QuimeraBaseTest is Test {
    address public target;
    IWETH public WETH = IWETH(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
    address internal flashloanProvider;
    address internal user1 = address(0x123);
    address internal user2 = address(0x456);

    function setUp() public {
        // Remove any previous WETH/ETH from the balance
        WETH.transfer(address(0x0), WETH.balanceOf(address(this)));
        payable(address(0)).transfer(address(this).balance);

        //$assignFlashLoanAddress
        target = address(new ERC4626Mock(address(WETH)));
        vm.deal(user1, 1000 ether); // Give user1 some ether
        vm.deal(user2, 1000 ether); // Give user2 some ether

        vm.startPrank(user1);
        WETH.deposit{value: 1000 ether}(); // User1 deposits ether to WETH
        WETH.approve(address(target), 1000 ether); // User1 approves the vault to spend WETH
        ERC4626Mock(target).deposit(1000 ether, user1); // User1 deposits WETH into the vault
        vm.stopPrank();

        vm.startPrank(user2);
        WETH.deposit{value: 100 ether}(); // User2 deposits ether to WETH
        WETH.approve(address(target), 1000 ether); // User2 approves the vault to spend WETH
        ERC4626Mock(target).deposit(100 ether, user2); // User2 deposits WETH into the vault
        vm.stopPrank();
    }

    function testFlaw() external {
         // flashloan WETH from Balancer
        address[] memory tokens = new address[](1);
        tokens[0] = address(WETH);

        uint256[] memory amounts = new uint256[](1);
        amounts[0] = WETH.balanceOf(flashloanProvider);

        console.log("%s available for the flashloan in wei", amounts[0]);

        uint256 finalWethBalance = WETH.balanceOf(address(this));
        console.log("Initial balance %s", finalWethBalance);
        //$flashloanCall
        console.log("Final balance %s", WETH.balanceOf(address(this)));
    }

    // Used by Balancer
    function receiveFlashLoan(
        IERC20[] memory,
        uint256[] memory amounts,
        uint256[] memory,
        bytes memory
    ) external {
        uint256 amount = amounts[0];
        flashLoanInternal(amount);
    }

    // Used by DODO
    function DPPFlashLoanCall(address, uint256 amount, uint256, bytes memory) external {
        flashLoanInternal(amount);
    }

    function flashLoanInternal(uint256 amount) internal {
        //$executeExploitCall

        console.log("Current WETH balance: %s WETH", WETH.balanceOf(address(this)));
        WETH.transfer(flashloanProvider, amount);
        uint256 surplusInETH = WETH.balanceOf(address(this));
        console.log("Surplus: %s WETH", surplusInETH);
        assert(surplusInETH > 0);
    }

    //$executeExploitCode
}