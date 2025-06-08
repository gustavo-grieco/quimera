#!/usr/bin/python3
# -*- coding: utf-8 -*-


from argparse import ArgumentParser, Namespace
from logging import basicConfig, getLogger, INFO, ERROR
from os import getenv
from sys import exit
from pathlib import Path
from requests import get
from random import randint
from time import sleep
from shutil import which

from llm import get_async_model
from llm.errors import ModelError
from llm import Tool

from quimera.template import SolidityTemplate
from quimera.chains import (
    get_valuable_token_address,
    get_uniswap_router_address,
    get_flashloan_provider,
    get_flashloan_call,
    get_flashloan_receiver,
)

from quimera.prompt import (
    initial_prompt_template,
    next_prompt_template,
    initial_execute_exploit_function,
    test_contract_template,
    constraints,
)

from quimera.foundry import install_and_run_foundry, copy_and_run_foundry
from quimera.model import get_response, save_prompt_response
from quimera.contract import (
    get_contract_info,
    get_contract_info_as_text,
    get_base_contract,
)

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
        "--valuable-token",
        help="The valuable token to use for the exploit (e.g. weth, usdc)",
        default="weth",
    )

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
    parser.add_argument(
        "--thinking-budget",
        help="The maximum time in seconds the model can take to generate a response",
        type=int,
        default=0,
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
    valuable_token = args.valuable_token.lower()
    model_name = args.model
    max_iterations = args.iterations

    chain = "mainnet"
    if "0x" in target:
        if ":" in target:
            chain = target.split(":")[0]
            target = target.split(":")[1]

        api_key = getenv("ETHERSCAN_API_KEY")
        if api_key is None:
            raise ValueError("Please set the ETHERSCAN_API_KEY environment variable.")

        if api_key == "TODO":
            raise ValueError(
                "Please set the ETHERSCAN_API_KEY environment variable to a valid API key."
            )
    else:
        logger.log(
            INFO, "Assuming local contract source file or directory with mainnet chain"
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

    target = contract_info["target_address"]
    args = {}
    args["interface"] = contract_info["interface"]
    args["targetCode"] = contract_info["target_code"]
    args["targetAddress"] = contract_info["target_address"]
    args["targetContractName"] = contract_info["contract_name"]

    args["constraints"] = constraints.replace("$valuableTokenName", valuable_token.upper())
    args["valuableTokenName"] = valuable_token.upper()
    args["assignFlashLoanAddress"] = (
        f"flashloanProvider = {get_flashloan_provider(chain)};"
    )
    args["assignValuableTokenAddress"] = f"valuableToken = IERC20({get_valuable_token_address(valuable_token, chain)});"
    args["assignUniswapRouterAddress"] = (
        f"uniswapRouter = IUniswapV2Router({get_uniswap_router_address(chain)});"
    )
    args["assignTargetAddress"] = f"target = {target};"
    if contract_info["is_erc20"]:
        args["assignTokenAddress"] = f"token = {target};"
    else:
        args["assignTokenAddress"] = ""

    args["executeExploitCall"] = "executeExploit(amount);"

    args["flashloanCall"] = get_flashloan_call(chain)
    args["flashloanReceiver"] = get_flashloan_receiver(chain)

    if "0x" in target:
        args["privateVariablesValues"] = f"{contract_info["private_variables_values"]}"
    else:
        args["privateVariablesValues"] = ""

    args["executeExploitCode"] = initial_execute_exploit_function

    if "0x" not in target:
        exploit_template = get_base_contract(target)
    else:
        exploit_template = test_contract_template

    test_code = SolidityTemplate(exploit_template).substitute(args)
    args["testCode"] = test_code

    if "0x" in target:
        temp_dir = Path("/tmp", "quimera_foundry_sessions", target, "0")
        args["trace"] = install_and_run_foundry(temp_dir, test_code, rpc_url)
    else:
        test_code = test_code.replace("QuimeraBaseTest", "QuimeraTest")
        temp_dir = Path(target, "test", "quimera")
        args["trace"] = copy_and_run_foundry(
            temp_dir, test_code, rpc_url, "QuimeraTest"
        )
        temp_dir = Path(target, "test", "quimera", "log", "0")

    prompt = SolidityTemplate(initial_prompt_template).substitute(args)
    save_prompt_response(prompt, None, temp_dir)

    model = None
    conversation = None
    if model_name != "manual":
        model = get_async_model(name=model_name)
        tools = [
            Tool.function(lambda address: get_contract_info_as_text(address, rpc_url, block_number, chain, args), name="get_contract_info_as_text"),
            Tool.function(lambda x, y: x * y, name="multiply_big_numbers"),
            Tool.function(lambda x, y: x + y, name="add_big_numbers"),
            Tool.function(lambda x, y: x - y, name="subtract_big_numbers")
        ]
        # start the llm converation
        conversation = model.conversation(tools=tools)

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

        args["executeExploitCode"] = response.strip()
        if "```" in args["executeExploitCode"]:
            args["executeExploitCode"] = args["executeExploitCode"].replace(
                "solidity", ""
            )
            # Remove the code block markers
            args["executeExploitCode"] = args["executeExploitCode"].split("```")[1]

        test_code = SolidityTemplate(exploit_template).substitute(args)
        args["testCode"] = test_code

        if "0x" in target:
            temp_dir = Path("/tmp", "quimera_foundry_sessions", target, str(iteration))
            args["trace"] = install_and_run_foundry(temp_dir, test_code, rpc_url)
        else:
            test_code = test_code.replace("QuimeraBaseTest", "QuimeraTest")
            temp_dir = Path(target, "test", "quimera")
            args["trace"] = copy_and_run_foundry(
                temp_dir, test_code, rpc_url, "QuimeraTest"
            )
            temp_dir = Path(target, "test", "quimera", "log", str(iteration))

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

        prompt = SolidityTemplate(next_prompt_template).substitute(args)


if __name__ == "__main__":
    main()
