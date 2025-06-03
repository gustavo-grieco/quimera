#!/usr/bin/python3
# -*- coding: utf-8 -*-


from argparse import ArgumentParser, Namespace
from logging import basicConfig, getLogger, INFO, ERROR
from os import getenv
from sys import exit
from pathlib import Path
from requests import get
from string import Template
from random import randint
from time import sleep
from shutil import which

from llm import get_async_model
from llm.errors import ModelError

from quimera.chains import (
    get_weth_address,
    get_uniswap_router_address,
    get_flashloan_provider,
    get_flashloan_call,
    get_flashloan_receiver,
)

from quimera.prompt import (
    initial_prompt_template,
    next_prompt_template,
    initial_during_flashloan_function,
    test_contract_template,
    constraints,
)

from quimera.foundry import install_and_run_foundry
from quimera.model import get_response, save_prompt_response
from quimera.contract import get_contract_info

basicConfig()
logger = getLogger("Quimera")
logger.setLevel(INFO)


def parse_args() -> Namespace:
    """
    Parse the underlying arguments for the program.
    :return: Returns the arguments for the program.
    """
    parser = ArgumentParser(
        description="Generates an exploit proof of concept for a given smart contract flaw using an LLM and Foundry",
        usage=("quimera <deployment address>"),
    )

    parser.add_argument(
        "contract_source",
        help="The name of the contract (case sensitive) followed by the deployed contract address if verified on etherscan or project directory/filename for local contracts.",
    )

    parser.add_argument("--block-number", help="The block number")

    parser.add_argument("--contract", help="The contract name to use")

    parser.add_argument(
        "--model",
        help="The model to use for code generation",
        default="manual",
    )

    parser.add_argument(
        "--iterations",
        help="The number of iterations to run",
        type=int,
        default=1,
    )
    return parser.parse_args()


def get_block_timestamp(block_number, api_key):
    url = "https://api.etherscan.io/api"
    params = {
        "module": "block",
        "action": "getblockreward",
        "blockno": block_number,
        "apikey": api_key,
    }

    response = get(url, params=params)
    data = response.json()

    if data["status"] != "1":
        print("Error:", data["result"])
        return None

    timestamp = int(data["result"]["timeStamp"])
    return timestamp


def check_commands_installed(commands):
    return {cmd: which(cmd) is not None for cmd in commands}


def main() -> None:
    args = parse_args()

    installed = check_commands_installed(["forge", "nano"])
    for cmd, installed in installed.items():
        if not installed:
            logger.log(
                ERROR, f"Error: {cmd} is not installed. Please install it to continue."
            )
            exit(1)

    target = args.contract_source
    chain = "mainnet"
    if ":" in target:
        chain = target.split(":")[0]
        target = target.split(":")[1]

    model_name = args.model
    max_iterations = args.iterations

    api_key = getenv("ETHERSCAN_API_KEY")
    if api_key is None:
        raise ValueError("Please set the ETHERSCAN_API_KEY environment variable.")

    if api_key == "TODO":
        raise ValueError(
            "Please set the ETHERSCAN_API_KEY environment variable to a valid API key."
        )

    # get the block timestamp
    block_number = args.block_number
    if block_number is None:
        block_number = getenv("FOUNDRY_FORK_BLOCK_NUMBER")

        if block_number is None:
            raise ValueError(
                "Please set the FOUNDRY_FORK_BLOCK_NUMBER or specify it with --block-number argument."
            )
        else:
            logger.log(
                INFO, f"Using block number {block_number} from environment variable."
            )
    else:
        logger.log(
            INFO, f"Using block number {block_number} from command line argument."
        )

    rpc_url = getenv("FOUNDRY_RPC_URL")
    if rpc_url is None:
        raise ValueError("Please set the FOUNDRY_RPC_URL environment variable.")

    # block_timestamp = get_block_timestamp(block_number, api_key)
    # if block_timestamp is None:
    #    raise ValueError("Failed to get block timestamp.")

    contract_info = get_contract_info(
        target,
        rpc_url,
        block_number,
        chain,
        args,
    )
    args = {}
    args["interface"] = contract_info["interface"]
    args["targetCode"] = contract_info["target_code"]
    args["targetAddress"] = contract_info["target_address"]
    args["tokenAddress"] = contract_info["token_address"]
    args["constraints"] = constraints

    args["flashloanAddress"] = get_flashloan_provider(chain)
    args["flashloanCall"] = get_flashloan_call(chain)
    args["flashloanReceiver"] = get_flashloan_receiver(chain)

    args["privateVariablesValues"] = contract_info["private_variables_values"]
    args["wethAddress"] = get_weth_address(chain)
    args["uniswapRouterAddress"] = get_uniswap_router_address(chain)
    args["exploitCode"] = initial_during_flashloan_function

    test_code = Template(test_contract_template).substitute(args)
    args["testCode"] = test_code

    temp_dir = Path("/tmp", "quimera_foundry_sessions", target, "0")
    args["trace"] = install_and_run_foundry(temp_dir, test_code, rpc_url)
    prompt = Template(initial_prompt_template).substitute(args)

    save_prompt_response(prompt, None, temp_dir)

    model = None
    conversation = None
    if model_name != "manual":
        model = get_async_model(name=model_name)
        # start the llm converation
        conversation = model.conversation()

    for iteration in range(1, max_iterations + 1):
        logger.log(INFO, f"Iteration {iteration}")
        logger.log(INFO, f"Prompt: {prompt}")
        logger.log(INFO, "Getting response from model...")
        response = None

        while response is None:
            try:
                response = get_response(conversation, prompt)
            except ModelError as e:
                print(f"Error getting response from model: {e}")

            if response is not None:
                sleep(randint(1, 2))
                break

            for _ in range(10 + randint(0, 10)):
                print(".", end="", flush=True)
                try:
                    sleep(1)
                except KeyboardInterrupt:
                    print("Execution interrupted by user.")
                    exit(1)

        args["exploitCode"] = response.strip()
        if "```" in args["exploitCode"]:
            args["exploitCode"] = args["exploitCode"].replace("solidity", "")
            # Remove the code block markers
            args["exploitCode"] = args["exploitCode"].split("```")[1]

        test_code = Template(test_contract_template).substitute(args)
        args["testCode"] = test_code
        temp_dir = Path("/tmp", "quimera_foundry_sessions", target, str(iteration))
        args["trace"] = install_and_run_foundry(temp_dir, test_code, rpc_url)
        save_prompt_response(prompt, response, temp_dir)
        logger.log(INFO, f"Trace/output: {args['trace']}")
        if (
            "Suite result: FAILED" in args["trace"]
            or "Compiler run failed" in args["trace"]
        ):
            logger.log(INFO, "Test failed, continuing to next iteration...")
        elif "[PASS] testFlaw()" in args["trace"]:
            logger.log(INFO, "Test passed, profit was found! 🎉")
            exit(0)
        else:
            assert False, "Test result is not clear, please check the output."

        prompt = Template(next_prompt_template).substitute(args)


if __name__ == "__main__":
    main()
