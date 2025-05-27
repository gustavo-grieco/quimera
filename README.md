# quimera

A simple tool to use LLMs to slowly approximate smart contract exploits using the following procedure:

1. Show the source code and the instructions (e.g. balance should be increased .
2. Ask the LLM to create or improve the current Foundry test case.
3. Run the potential exploit and record the trace if it fails.
4. Go back to 2.
