initial_during_flashloan_function = """
    function duringFlashLoan(uint256 amount) internal {}
"""

test_contract_template = """
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.17;

import "forge-std/Test.sol";

$interface

interface IWETH {
    function deposit() external payable;
    function transfer(address to, uint256 value) external returns (bool);
    function approve(address guy, uint256 wad) external returns (bool);
    function withdraw(uint256 wad) external;
    function balanceOf(address) external view returns (uint256);
}

interface IERC20 {
    function approve(address guy, uint256 wad) external returns (bool);
    function balanceOf(address) external view returns (uint256);
    function transfer(address to, uint256 value) external returns (bool);
}

interface IUniswapV2Factory {
    function getPair(address tokenA, address tokenB) external view returns (address pair);
}

interface IUniswapV2Pair {
    function balanceOf(address) external view returns (uint256);
    function skim(address to) external;
    function sync() external;
    function swap(uint256 amount0Out, uint256 amount1Out, address to, bytes memory data) external;
    function token0() external view returns (address);
    function token1() external view returns (address);
    function getReserves() external view returns (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast);
}

interface IUniswapV2Router {
    function factory() external view returns (address);
    function swapExactTokensForTokensSupportingFeeOnTransferTokens(
        uint256 amountIn,
        uint256 amountOutMin,
        address[] calldata path,
        address to,
        uint256 deadline
    ) external;

    function swapExactETHForTokensSupportingFeeOnTransferTokens(
        uint amountOutMin,
        address[] calldata path,
        address to,
        uint deadline
    ) external payable;

    function swapExactTokensForETHSupportingFeeOnTransferTokens(
        uint amountIn,
        uint amountOutMin,
        address[] calldata path,
        address to,
        uint deadline
    ) external;
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

contract TestFlaw {
    address internal target = $targetAddress;
    address internal token0;
    address internal token1;
    address internal token;
    IUniswapV2Router internal uniswapRouter = IUniswapV2Router($uniswapRouterAddress);
    IUniswapV2Pair internal uniswapPair;
    IWETH private constant WETH = IWETH($wethAddress);
    address private flashloanProvider = $flashloanAddress;

    function setUp() public {
        // Remove any previous WETH/ETH from the balance
        WETH.transfer(address(0x0), WETH.balanceOf(address(this)));
        payable(address(0)).transfer(address(this).balance);

        token = $tokenAddress;
        if (token == address(0))
            revert("Token address is zero");

        IUniswapV2Factory uniswapFactory = IUniswapV2Factory(uniswapRouter.factory());
        uniswapPair = IUniswapV2Pair(uniswapFactory.getPair(address(WETH), token));

        if (address(uniswapPair) == address(0))
            return;

        //if (WETH.balanceOf(address(uniswapPair)) < 1 ether)
        //    revert("Not enough WETH in pair");

        token0 = uniswapPair.token0();
        token1 = uniswapPair.token1();

        WETH.approve(address(uniswapRouter), type(uint256).max);
        IERC20(token).approve(address(uniswapRouter), type(uint256).max);

        WETH.approve(target, type(uint256).max);
        IERC20(token).approve(target, type(uint256).max);

        uint112 reserve0;
        uint112 reserve1;
        (reserve0, reserve1, ) = uniswapPair.getReserves();
        console.log("Uniswap reserves: %d %d", reserve0, reserve1);
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
        $flashloanCall
        console.log("Final balance %s", WETH.balanceOf(address(this)));
    }

    $flashloanReceiver
        duringFlashLoan(amount);

        console.log("Current WETH balance: %s WETH", WETH.balanceOf(address(this)));
        WETH.transfer(flashloanProvider, amount);
        uint256 surplusInETH = WETH.balanceOf(address(this));
        console.log("Surplus: %s WETH", surplusInETH);
        assert(surplusInETH > 0);
    }

    $exploitCode
}
"""

constraints = """
# Constraints

* Do NOT guess the internal behavior of the contract, instead use the information provided by the trace, which is always accurate.
* Do NOT predict the trace output, you need to run the test and check the output.
* Do NOT use SafeMath
* Do NOT use third-parties during exploit (e.g. the owner doing something for you)
* Do NOT use any cheat code (e.g prank)
* Do NOT try to exploit underflows or overflow conditions unless the contract is using Solidity < 0.8.0 or unchecked block. It will not work.
* Do NOT explain the reasoning, only answer with the `duringFlashloan` and optionally the `receive` function (if needed) or any external function for callbacks/reentrancy.
* Do NOT repeat or modify the rest of the code.

# Recommendations

* Carefully review how tokens flows from this contract, to the Uniswap pair (and maybe passing through others), and back to this contract to repay the flash loan.
* You have initially a large amount of WETH available, but you don't have to use it all if you need it (depends on the liquidity available). Do not change this value, only use the part of the 1000 WETH that you need.
* You start with no tokens, except WETH, so you must find a way to obtain the right tokens in order to trigger the flaw.
* If you need ETH, unwrap WETH to ETH using the `WETH.withdraw` function.
* Near the end, you need to swap all your tokens to WETH. Be careful with transfer fees and other constraints. The exploit should be "capital efficient", in order to be detectable when repaying the flashloan.
* Use `console.log` to query the state of the contracts, if needed.
* Keep the control flow of the exploit simple: do not use if conditions, only sequences of calls.
* Try using different functions of the target contracts and evaluate the effects to see if they are useful for the exploit.
"""

initial_prompt_template = """
# Instructions

We are going to reproduce a Solidity smart contract issue step by step, incrementally modifying a Foundry test according to the information produced during its execution (e.g. a trace). This issue allows a user to start with a certain amount of WETH, perform some operations using the contract, and then obtain more WETH than the initial one.

$constraints

# Code to review
```
$targetCode
```

The contract has a number of private variables that are not accessible, these are their current values:
$privateVariablesValues

And the first Foundry trace is this one:

```
$testCode
```
And the first foundry trace is this one:
```
$trace
```"""

next_prompt_template = """
The result of the last execution is:
```
$trace
```
Please improve the receiveFlashLoan function to fix the issue and make it work.

$constraints
"""
