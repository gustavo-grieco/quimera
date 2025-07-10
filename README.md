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
| [XAI]  | Low    | A small number of steps needed, as you can see in the demo |
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
pip3 install git+https://github.com/gustavo-grieco/quimera
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

# Related Work

[AI Agent Smart Contract Exploit Generation](https://arxiv.org/abs/2507.05558): an approach very close to Quimera, even sharing some of the exploits rediscovered here.
