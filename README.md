# Quimera

A simple tool to use LLMs to slowly approximate smart contract exploits in Foundry using the following procedure:

1. Fetch the source code and craft a prompt with the exploit instructions (e.g. balance should be increased after the a flashloan).
2. Ask the LLM to create or improve the current Foundry test case.
3. Run the potential exploit, record the trace and check if it produces profit or not. 
4. Stop if profit is produced. Otherwise, go back to step (2) providing the trace of the failed exploit attempt. 

# Requirements

* You will need an RPC provider (e.g. alchemy) and an Etherscan API key. Both have free options.
* An LLM service, either a local (e.g. ollama) or remote LLM service (e.g gemini). ** You do not need to pay for an API access**
* Foundry

# Installation

To install, just clone and run `pip3 install .`

If you want to use [different LLM providers](https://llm.datasette.io/en/stable/plugins/directory.html#plugin-directory), you will need to install them as plugins. For instance, to install gemini and ollama support:

```
llm install llm-gemini
llm install llm-ollama
```

Note that in "manual mode", there is no need to install any plugin as the user will be copying and pasting the code manually and there is no need for an API plugin for that.


# Getting started

1. Modify the mainnet.sh file to add the RPC and etherscan keys.
2. Select a block number B and then execute `source mainnet.sh B"
3. Invoke quimera:

```
quimera TARGET --iterations 5 --model manual
```


# Example sessions with Gemini 2.5

```
./keys.sh X

```

```

```