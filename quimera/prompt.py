initial_execute_exploit_function = (
    """function executeExploit(uint256 amount) internal {}"""
)

test_contract_template = """// SPDX-License-Identifier: UNLICENSED
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

//$additionalInterfaces

contract TestFlaw is Test {
    address internal target;
    address internal token0;
    address internal token1;
    address internal token;
    IUniswapV2Router internal uniswapRouter;
    IUniswapV2Pair internal uniswapPair;
    IERC20 private valuableToken;
    address private flashloanProvider;

    function setUniswapPair(address addr) public {
        IUniswapV2Factory uniswapFactory = IUniswapV2Factory(uniswapRouter.factory());
        uniswapPair = IUniswapV2Pair(uniswapFactory.getPair(address(valuableToken), addr));

        if (address(uniswapPair) == address(0)) {
            console.log("Uniswap pair not found.");
            return;
        }

        token0 = uniswapPair.token0();
        token1 = uniswapPair.token1();

        valuableToken.approve(address(uniswapRouter), type(uint256).max);
        IERC20(addr).approve(address(uniswapRouter), type(uint256).max);

        uint112 reserve0;
        uint112 reserve1;
        (reserve0, reserve1, ) = uniswapPair.getReserves();
        console.log("Uniswap reserves for %s:", addr);
        console.log("%d for %s", reserve0, token0);
        console.log("%d for %s", reserve1, token1);
    }

    function setUp() public {

        //$assignTargetAddress
        //$assignUniswapRouterAddress
        //$assignValuableTokenAddress
        //$assignFlashLoanAddress
        //$assignTokenAddress

        // Remove any previous valuableToken/ETH from the balance
        valuableToken.transfer(address(0xdead), valuableToken.balanceOf(address(this)));
        IERC20(uniswapRouter.WETH()).transfer(address(0xdead), IERC20(uniswapRouter.WETH()).balanceOf(address(this)));
        payable(address(0xdead)).transfer(address(this).balance);

        // Handle approvals
        valuableToken.approve(target, type(uint256).max);
        //if (token != address(0))
        //    IERC20(token).approve(target, type(uint256).max);
        setUniswapPair(token);
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
        flashLoanInternal(amounts[0]);
    }

    // Used by DODO
    function DPPFlashLoanCall(address, uint256 amount, uint256, bytes memory) external {
        flashLoanInternal(amount);
    }

    function flashLoanInternal(uint256 amount) internal {
        //$executeExploitCall

        uint256 currentValuableBalance = valuableToken.balanceOf(address(this));
        if (amount >= currentValuableBalance) {
            console.log("Current valuable balance: %s", valuableToken.balanceOf(address(this)));
            console.log("Current profit: %s", int256(currentValuableBalance) - int256(amount));
            revert("Not enough valuableToken balance to produce profit");
        }
        valuableToken.transfer(flashloanProvider, amount);
        uint256 surplusInValuable = valuableToken.balanceOf(address(this));
        console.log("Surplus: %s", surplusInValuable);
        assert(surplusInValuable > 0);
    }

    //$executeExploitCode
}

//$additionalContracts
"""

constraints = """
# Constraints

* VERY IMPORTANT: If you do not have the source code already available, start fetching the source code of the contracts involved, using their addresses. You should do this at any time when you discover a new address or token that you need to interact to.
* VERY IMPORTANT: Only use addresses fetched from the target contracts state, new deployment or `address(this)`. Never use hardcoded addresses or invent new ones.
* VERY IMPORTANT: do NOT use any cheat code (e.g prank). You will disqualified if you do so.
* Do NOT guess the internal behavior of the contract, instead use the information provided by the trace, which is always accurate.
* Do NOT predict the trace output, you need to run the test and check the output.
* Do NOT use SafeMath
* Do NOT try a reentrancy attack if a function is using `nonReentrant` modifier, it will not work. You can still call other functions without this modifier or any other functions from any related contracts.
* Do NOT use low-level calls
* Do NOT define additional contracts to deploy but you can use imported ones (e.g. ERC20Mock)
* Do NOT use third-parties during exploit (e.g. the owner doing something for you). You can still pass other contracts or EOA addresses as parameters to the exploit if needed.
* Do NOT use any private key operations (e.g. signing messages, etc.)
* Do NOT try to re-initialize the contract, it will not work.
* Do NOT try to exploit underflows or overflow conditions unless the contract is using Solidity < 0.8.0 or unchecked block. It will not work. However, unsafe casting is an issue for all versions.
* If you want to simulate a EOA, use `vm.startPrank(address(this), address(this));` and `vm.stopPrank();` functions. These are the ONLY allowed cheatcodes.

# Output Format

You should output different sections using the following tags:
- `<executeExploitCode>`: the code of the `executeExploit` function, which is the main function to exploit the flaw as well as any additional function needed (e.g. for callbacks or reentrancy).
- `<additionalInterfaces>`: any additional interface you need to use, if not provided.
- `<additionalContracts>`: any additional contract you need to use, if not provided.

* These tags should be used, at most, a single time. The `executeExploitCode` section is mandatory, while the others are optional.
* Do NOT forget to close the tags with `</executeExploitCode>`, `</additionalInterfaces>` and `</additionalContracts>`.
* Only use `additionalInterfaces` and `additionalContracts` if you absolutely need to define new interfaces or contracts, otherwise do not use them.
* Do NOT output the rest of the code, only answer with the format requested.

# Recommendations

* Carefully review how tokens flows from this contract, to the Uniswap pair (and maybe passing through others), and back to this contract to repay the flash loan.
* You have initially a large amount of $valuableTokenName available, but you don't have to use it all if you need it (depends on the liquidity available). Do not change this value, only use the part of the flashloan that you need.
* You start with no tokens, except $valuableTokenName, so you must find a way to obtain the right tokens in order to trigger the flaw.
* Near the end, you need to swap all your tokens to $valuableTokenName. Be careful with transfer fees and other constraints. The exploit should be "capital efficient", in order to be detectable when repaying the flashloan.
* Use `console.log` to query the state of the contracts, if needed.
* Keep the control flow of the exploit simple: do not use if conditions, only sequences of calls.
* Try using different functions of the target contracts and evaluate the effects to see if they are useful for the exploit.
* If the uniswap pair is not initially available and you need it, try to find a suitable token and query the Uniswap factory to get the pair address. Do NOT forget to call approve on the token for the router before using it.
* If `transferFrom` reverts, try to use the `approve` function first.
* If the target contract requires to use an address as paramter, try to see if you can use the address of the contract itself (e.g. address(this)), or the address of the test contract you deploy. If it is not validated, you can probably exploit it.
"""

initial_prompt_template = """# Instructions

We are going to reproduce a Solidity smart contract issue step by step related with //$targetAddress and/or one of the "linked" contracts (e.g tokens, staking, etc) in the //$chain chain which contains a deployment of the //$targetContractName contract.
Before starting, please read the provided code, fetch related contracts using addresses (use the Foundry traces to get the values) and request their source code to understand how they work and where the issue is.
The goal is to incrementally modifying a Foundry test according to the information produced during its execution (e.g. a trace) until we can reproduce the issue.
This issue allows a user to start with a certain amount of //$valuableTokenName, perform some operations using the contract (or other related ones), and then obtain more //$valuableTokenName than the initial one.

//$constraints

# Code to review
```
//$targetCode
```

The contract has a number of public/private variables, these are their current values:
//$variablesValues

If these addresses above are relevant for the exploit, you must ask for their source code and understand how they work.

# Test code to execute the exploit

```
//$testCode
```

And the first Foundry trace is this one:
```
//$trace
```"""

next_prompt_template = """The result of the last execution is:
```
//$trace
```
Please improve the `executeExploit` function to fix the issue and make it work (or change your approach).

//$constraints
"""


def parse_response(response: str) -> dict:
    """
    Parses the LLM response to extract the sections descripted in the prompt as HTML-like tags (e.g. <X>...</X>).
    This should carefully handle tags which can be in any part of the line.
    """
    sections = {
        "executeExploitCode": "",
        "additionalInterfaces": "",
        "additionalContracts": "",
    }

    # Only parse the sections in `sections`
    for section in sections.keys():
        start_tag = f"<{section}>"
        end_tag = f"</{section}>"
        start_index = response.find(start_tag)
        end_index = response.find(end_tag)

        if start_index != -1 and end_index != -1:
            content = response[start_index + len(start_tag) : end_index].strip()
            sections[section] = content
    # Remove the tags from the content
    for section in sections:
        sections[section] = (
            sections[section]
            .replace(f"<{section}>", "")
            .replace(f"</{section}>", "")
            .strip()
        )

    # Remove ``` and ```solidity from the content
    for section in sections:
        sections[section] = (
            sections[section].replace("```solidity", "").replace("```", "").strip()
        )

    return sections
