initial_execute_exploit_function = """
    function executeExploit(uint256 amount) internal {}
"""

test_contract_template = """
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.17;

import "forge-std/Test.sol";

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
  function decimals() external pure returns (uint8);
  function totalSupply() external view returns (uint);
  function balanceOf(address owner) external view returns (uint);
  function allowance(address owner, address spender) external view returns (uint);

  function approve(address spender, uint value) external returns (bool);
  function transfer(address to, uint value) external returns (bool);
  function transferFrom(address from, address to, uint value) external returns (bool);

  function MINIMUM_LIQUIDITY() external pure returns (uint);
  function factory() external view returns (address);
  function token0() external view returns (address);
  function token1() external view returns (address);
  function getReserves() external view returns (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast);
  function price0CumulativeLast() external view returns (uint);
  function price1CumulativeLast() external view returns (uint);
  function kLast() external view returns (uint);

  function mint(address to) external returns (uint liquidity);
  function burn(address to) external returns (uint amount0, uint amount1);
  function swap(uint amount0Out, uint amount1Out, address to, bytes calldata data) external;
  function skim(address to) external;
  function sync() external;
}

interface IUniswapV2Router {
    function factory() external view returns (address);
    function WETH() external pure returns (address);

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

    function addLiquidity(
        address tokenA,
        address tokenB,
        uint amountADesired,
        uint amountBDesired,
        uint amountAMin,
        uint amountBMin,
        address to,
        uint deadline
    ) external returns (uint amountA, uint amountB, uint liquidity);
    function addLiquidityETH(
        address token,
        uint amountTokenDesired,
        uint amountTokenMin,
        uint amountETHMin,
        address to,
        uint deadline
    ) external payable returns (uint amountToken, uint amountETH, uint liquidity);
    function removeLiquidity(
        address tokenA,
        address tokenB,
        uint liquidity,
        uint amountAMin,
        uint amountBMin,
        address to,
        uint deadline
    ) external returns (uint amountA, uint amountB);
    function removeLiquidityETH(
        address token,
        uint liquidity,
        uint amountTokenMin,
        uint amountETHMin,
        address to,
        uint deadline
    ) external returns (uint amountToken, uint amountETH);
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

//$interface

contract TestFlaw is Test {
    address internal target;
    address internal token0;
    address internal token1;
    address internal token;
    IUniswapV2Router internal uniswapRouter;
    IUniswapV2Pair internal uniswapPair;
    IERC20 private valuableToken;
    address private flashloanProvider;


    function setUp() public {

        //$assignTargetAddress
        //$assignUniswapRouterAddress
        //$assignValuableTokenAddress
        //$assignFlashLoanAddress
        //$assignTokenAddress

        // Remove any previous valuableToken/ETH from the balance
        valuableToken.transfer(address(0xdead), valuableToken.balanceOf(address(this)));
        payable(address(0xdead)).transfer(address(this).balance);

        // Handle approvals
        valuableToken.approve(target, type(uint256).max);
        //if (token != address(0))
        //    IERC20(token).approve(target, type(uint256).max);

        IUniswapV2Factory uniswapFactory = IUniswapV2Factory(uniswapRouter.factory());
        uniswapPair = IUniswapV2Pair(uniswapFactory.getPair(address(valuableToken), token));

        if (address(uniswapPair) == address(0)) {
            console.log("Uniswap pair not found.");
            return;
        }

        token0 = uniswapPair.token0();
        token1 = uniswapPair.token1();

        valuableToken.approve(address(uniswapRouter), type(uint256).max);
        IERC20(token).approve(address(uniswapRouter), type(uint256).max);

        uint112 reserve0;
        uint112 reserve1;
        (reserve0, reserve1, ) = uniswapPair.getReserves();
        console.log("Uniswap reserves:");
        console.log("%d for %s", reserve0, token0);
        console.log("%d for %s", reserve1, token1);
    }

    function testFlaw() external {
         // flashloan valuableToken from Balancer
        address[] memory tokens = new address[](1);
        tokens[0] = address(valuableToken);

        uint256[] memory amounts = new uint256[](1);
        amounts[0] = valuableToken.balanceOf(flashloanProvider) * 95 / 100;

        console.log("%s available for the flashloan of valuableToken", amounts[0]);

        uint256 finalValuableBalance = valuableToken.balanceOf(address(this));
        console.log("Initial balance %s", finalValuableBalance);
        //$flashloanCall
        console.log("Final balance %s", valuableToken.balanceOf(address(this)));
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

        console.log("Current valuable balance: %s", valuableToken.balanceOf(address(this)));
        valuableToken.transfer(flashloanProvider, amount);
        uint256 surplusInValuable = valuableToken.balanceOf(address(this));
        console.log("Surplus: %s", surplusInValuable);
        assert(surplusInValuable > 0);
    }

    //$executeExploitCode
}
"""

constraints = """
# Constraints

* Do NOT guess the internal behavior of the contract, instead use the information provided by the trace, which is always accurate.
* Do NOT predict the trace output, you need to run the test and check the output.
* Only use addresses provided in the contracts, never hardcoded from your memory.
* Do NOT use SafeMath
* Do NOT use low-level calls
* Do NOT define additional contracts to deploy but you can use imported ones (e.g. ERC20Mock)
* Do NOT use third-parties during exploit (e.g. the owner doing something for you). You can still pass other contracts or EOA addresses as parameters to the exploit if needed.
* Do NOT use any private key operations (e.g. signing messages, etc.)
* Do NOT try to re-initialize the contract, it will not work.
* Do NOT try to exploit underflows or overflow conditions unless the contract is using Solidity < 0.8.0 or unchecked block. It will not work. However, unsafe casting is an issue for all versions.
* If available, use the `get_contract_source_info` tool to get the source code of a contract as well as additional information.
* VERY IMPORTANT: only answer with the `executeExploit` function and optionally the `receive` function (if needed) or any external function for callbacks/reentrancy. Do NOT output the rest of the code.
* VERY IMPORTANT: do NOT use any cheat code (e.g prank). You will disqualified if you do so.
* If you want to simulate a EOA, use `vm.startPrank(address(this), address(this));` and `vm.stopPrank();` functions. These are the ONLY allowed cheatcodes.

# Recommendations

* Carefully review how tokens flows from this contract, to the Uniswap pair (and maybe passing through others), and back to this contract to repay the flash loan.
* You have initially a large amount of $valuableTokenName available, but you don't have to use it all if you need it (depends on the liquidity available). Do not change this value, only use the part of the flashloan that you need.
* You start with no tokens, except $valuableTokenName, so you must find a way to obtain the right tokens in order to trigger the flaw.
* Near the end, you need to swap all your tokens to $valuableTokenName. Be careful with transfer fees and other constraints. The exploit should be "capital efficient", in order to be detectable when repaying the flashloan.
* Use `console.log` to query the state of the contracts, if needed.
* Keep the control flow of the exploit simple: do not use if conditions, only sequences of calls.
* Try using different functions of the target contracts and evaluate the effects to see if they are useful for the exploit.
* If the uniswap pair is not initially available and you need it, try to find a suitable token and query the Uniswap factory to get the pair address.
"""

initial_prompt_template = """
# Instructions

We are going to reproduce a Solidity smart contract issue step by step targetting //$targetAddress which contains a //$targetContractName contract.
The goal is to incrementally modifying a Foundry test according to the information produced during its execution (e.g. a trace) until we can reproduce the issue.
This issue allows a user to start with a certain amount of //$valuableTokenName, perform some operations using the contract (or other related ones), and then obtain more //$valuableTokenName than the initial one.

//$constraints

# Code to review
```
//$targetCode
```

The contract has a number of private variables that are not accessible, these are their current values:
//$privateVariablesValues

# Test code to execute the exploit

```
//$testCode
```

And the first Foundry trace is this one:
```
//$trace
```"""

next_prompt_template = """
The result of the last execution is:
```
//$trace
```
Please improve the `executeExploit` function to fix the issue and make it work (or change your approach).

//$constraints
"""
