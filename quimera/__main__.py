#!/usr/bin/python3
# -*- coding: utf-8 -*-

import asyncio
from argparse import ArgumentParser, Namespace
from datetime import datetime
from logging import basicConfig, getLogger, INFO, WARNING, ERROR
from signal import SIGINT, SIGTERM
from os import getenv
from re import compile
from sys import exit
from pathlib import Path
from shutil import rmtree
from subprocess import run
from requests import get
from string import Template
from random import randint
from time import sleep
from shutil import which
from sys import platform
from os import system

from llm import get_async_model
from llm.errors import ModelError
from eth_utils import to_checksum_address

from slither import Slither
from slither.tools.read_storage import read_storage
from slither.tools.read_storage.read_storage import SlitherReadStorage, RpcInfo
from slither.utils.code_generation import generate_interface
from slither.core.solidity_types.elementary_type import ElementaryType

basicConfig()
logger = getLogger("Quimera")
logger.setLevel(INFO)

# EIP-1967 implementation slot (minus 1 and hashed)
IMPLEMENTATION_SLOT = (
    "0x360894A13BA1A3210667C828492DB98DCA3E2076CC3735A920A3CA505D382BBC"
)

initial_during_flashloan_function = """
    function duringFlashLoan(uint256 amount) internal {}
"""

initial_during_reenter_function = """
    function duringReenter() internal {}
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

interface ERC20 {
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

    function getAmountsIn(address factory, uint amountOut, address[] memory path) external view returns (uint[] memory amounts);
    function getAmountsOut(uint amountIn, address[] memory path) external view returns (uint[] memory amounts);

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

contract TestFlaw {
    address internal target = $targetAddress;
    address internal token0;
    address internal token1;
    address internal token;
    IUniswapV2Router internal uniswapRouter = IUniswapV2Router($uniswapRouterAddress);
    IUniswapV2Pair internal uniswapPair;
    IWETH private constant WETH = IWETH($wethAddress);
    IBalancerVault private constant balancerVault = IBalancerVault(0xBA12222222228d8Ba445958a75a0704d566BF2C8);

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
        ERC20(token).approve(address(uniswapRouter), type(uint256).max);

        WETH.approve(target, type(uint256).max);
        ERC20(token).approve(target, type(uint256).max);

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
        amounts[0] = 1000 ether;

        uint256 finalWethBalance = WETH.balanceOf(address(this));
        console.log("Initial balance %s", finalWethBalance);
        balancerVault.flashLoan(address(this), tokens, amounts, "");
        console.log("Final balance %s", WETH.balanceOf(address(this)));
    }

    function receiveFlashLoan(
        ERC20[] memory,
        uint256[] memory amounts,
        uint256[] memory,
        bytes memory
    ) external {
        duringFlashLoan(amounts[0]);

        console.log("Current WETH balance: %s WETH", WETH.balanceOf(address(this)));
        WETH.transfer(address(balancerVault), amounts[0]);
        uint256 surplusInETH = WETH.balanceOf(address(this));
        console.log("Surplus: %s WETH", surplusInETH);
        assert(surplusInETH > 0);
    }

    $exploitCode

    receive() external payable {
        duringReenter();
    }
}
"""

constraints = """
# Constraints

* Do NOT use SafeMath
* Do NOT use third-parties during exploit (e.g. the owner doing something for you)
* Do NOT use any cheat code (e.g prank)
* Do NOT try to exploit underflows or overflow conditions unless the contract is using Solidity < 0.8.0 or unchecked block. It will not work.
* Do NOT explain the reasoning, only answer with the `duringFlashloan` and `duringReenter` internal functions. Do NOT repeat or modify the rest of the code.
* Use an empty `duringReenter` definition if reentrancy is not needed.

# Recommendations

* Carefully review how tokens flows from this contract, to the Uniswap pair (and maybe passing through others), and back to this contract to repay the flash loan.
* You have initially 1000 WETH available, but you don't have to use it all if you need it (depends on the liquidity available). Do not change this value, only use the part of the 1000 WETH that you need.
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


def get_async_response(conversation, prompt):
    """
    Get the response from the model asynchronously.
    :param model: The model to use for the response.
    :param prompt: The prompt to send to the model.
    :return: The response from the model.
    """

    async def fetch_response():
        response = ""
        async for chunk in conversation.prompt(prompt):
            print(chunk, end="", flush=True)
            response += chunk
        return response

    loop = asyncio.get_event_loop()
    main_task = asyncio.ensure_future(fetch_response())

    for signal in [SIGINT, SIGTERM]:
        loop.add_signal_handler(signal, main_task.cancel)
    try:
        answer = loop.run_until_complete(main_task)
    except asyncio.CancelledError:
        print("Execution interrupted by user.")
        exit(1)

    return answer


def resolve_prompt(prompt):
    # Write prompt to tmp.txt
    with open("/tmp/quimera.prompt.txt", "w") as file:
        file.write(prompt)

    # Open nano to edit the prompt
    if platform == "darwin":
        # In general, shell=True is not recommended, but here only we use it to pipe the content to pbcopy (there is no other way)
        run("cat /tmp/quimera.prompt.txt | pbcopy", shell=True)
    elif platform == "linux":
        run(["xclip", "-selection", "clipboard", "-in", "/tmp/quimera.prompt.txt"], check=True)
    else:
        raise ValueError("Unsupported platform.")
    # overwrite the prompt with instructions
    with open("/tmp/quimera.answer.txt", "w") as file:
        file.write(
            "Your current prompt was copied to the clipboard. Delete everything (alt + t), paste the response here, save (ctrl + o) and exit (ctrl + x)"
        )
    run(["nano", "/tmp/quimera.answer.txt"], check=True)

    # Read the modified prompt
    with open("/tmp/quimera.answer.txt", "r") as file:
        return file.read()


def get_response(conversation, prompt):
    if conversation is None:
        return resolve_prompt(prompt)
    else:
        return get_async_response(conversation, prompt)


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


def get_weth_address(chain):
    if chain == "mainnet":
        return "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
    elif chain == "bsc":
        return "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
    else:
        raise ValueError("Unsupported chain")


def get_uniswap_router_address(chain):
    if chain == "mainnet":
        return "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
    elif chain == "bsc":
        return "0x05fF7c8D4dF7E9C8F6eB2cA3E1D3dF6C4eD1d7e5"
    else:
        raise ValueError("Unsupported chain")


def check_commands_installed(commands):
    return {cmd: which(cmd) is not None for cmd in commands}


def main() -> None:
    args = parse_args()

    installed = check_commands_installed(["forge", "nano"])
    for cmd, installed in installed.items():
        if not installed:
            logger.log(ERROR, f"Error: {cmd} is not installed. Please install it to continue.")
            exit(1)

    target = args.contract_source
    target = to_checksum_address(target)

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

    rpc_url = getenv("FOUNDRY_ETH_RPC_URL")
    if rpc_url is None:
        raise ValueError("Please set the FOUNDRY_ETH_RPC_URL environment variable.")

    block_timestamp = get_block_timestamp(block_number, api_key)
    if block_timestamp is None:
        raise ValueError("Failed to get block timestamp.")

    rpc_info = RpcInfo(rpc_url, int(block_number))
    impl_raw = rpc_info.web3.eth.get_storage_at(target, IMPLEMENTATION_SLOT)
    implementation = "0x" + impl_raw[-20:].hex()
    if implementation != "0x0000000000000000000000000000000000000000":
        target = implementation
        target = to_checksum_address(target)
        logger.log(INFO, f"Proxy detected, using target address {target}")

    slither = Slither(target, **vars(args))

    # get all the contracts names
    contracts = slither.contracts
    contract = None

    if args.contract:
        contract_name = args.contract
        contract = slither.get_contract_from_name(contract_name)[0]
    else:
        max_functions = 0
        for contract in contracts:
            if contract.is_abstract:
                continue

            number_entry_points = len(contract.functions_entry_points)
            if number_entry_points > max_functions:
                max_functions = number_entry_points
                contract_name = contract.name

    contracts_names = [contract.name for contract in contracts]
    logger.info(f"Contracts found: {contracts_names}, selected {contract_name}")
    _contract = slither.get_contract_from_name(contract_name)[0]

    src_mapping = _contract.source_mapping
    target_code = _contract.compilation_unit.core.source_code[
        src_mapping.filename.absolute
    ]
    # if _contract.is_erc4626:
    #    token_address = f"I{_contract.name}({target}).asset()"
    if _contract.is_erc20:
        token_address = f"{target}"
    else:
        logger.log(
            WARNING, f"Contract {contract_name} is not an ERC20 or ERC4626 token."
        )
        token_address = f"{target}"

    interface = generate_interface(
        contract=_contract,
        unroll_structs=False,
        include_events=False,
        include_errors=False,
        include_enums=False,
        include_structs=True,
    )

    srs = SlitherReadStorage([_contract], max_depth=20, rpc_info=rpc_info)
    srs.storage_address = target

    private_vars = []
    for var in _contract.state_variables:
        #if var.is_internal:
        if not (isinstance(var.type, ElementaryType) and var.type.name in ["uint256", "bool"]):
            continue

        if var.visibility == "public":
            continue
        private_vars.append(var.name)

    read_storage.logger.disabled = True
    srs.get_all_storage_variables(lambda x: x.name in private_vars)
    srs.get_target_variables()
    srs.walk_slot_info(srs.get_slot_values)

    private_variables_values = ""
    for var in srs.slot_info.values():
        private_variables_values += f"{var.name} = {var.value}\n"

    args = {}
    args["interface"] = interface
    args["targetCode"] = target_code
    args["targetAddress"] = target
    args["tokenAddress"] = token_address
    args["constraints"] = constraints
    args["privateVariablesValues"] = private_variables_values
    args["wethAddress"] = get_weth_address("mainnet")
    args["uniswapRouterAddress"] = get_uniswap_router_address("mainnet")
    args["exploitCode"] = initial_during_flashloan_function + initial_during_reenter_function

    test_code = Template(test_contract_template).substitute(args)
    args["testCode"] = test_code

    temp_dir = Path("/tmp", "quimera_foundry_sessions", target, "0")
    args["trace"] = install_and_run_foundry(temp_dir, test_code)
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
            args["exploitCode"] = args["exploitCode"].replace(
                "solidity", ""
            )
            # Remove the code block markers
            args["exploitCode"] = args["exploitCode"].split(
                "```"
            )[1]

        test_code = Template(test_contract_template).substitute(args)
        args["testCode"] = test_code
        temp_dir = Path("/tmp", "quimera_foundry_sessions", target, str(iteration))
        args["trace"] = install_and_run_foundry(temp_dir, test_code)
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

def save_prompt_response(prompt, response, temp_dir):
    """Saves the prompt and response to a file in the temporary directory."""
    if not temp_dir.exists():
        temp_dir.mkdir(parents=True, exist_ok=True)

    if prompt is not None:
        with open(temp_dir / "prompt.txt", "w", encoding="utf-8") as prompt_file:
            prompt_file.write(prompt)

    if response is not None:
        with open(temp_dir / "response.txt", "w", encoding="utf-8") as response_file:
            response_file.write(response)

    # save date and time in a timestamp.txt file
    with open(temp_dir / "timestamp.txt", "w", encoding="utf-8") as timestamp_file:
        timestamp_file.write(datetime.now().isoformat())

def escape_ansi(line):
    ansi_escape = compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', line)

def install_and_run_foundry(temp_dir, test_code) -> None:
    """Sets up a temporary directory for the tests"""
    # Create a temporary directory valid for the session
    if temp_dir.exists():
        rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    logger.log(INFO, "Installing Forge...")
    # Install forget, supressing output
    run(["forge", "init", "--no-git"], check=True, cwd=temp_dir, capture_output=True)

    # Create foundry config
    foundry_config = temp_dir / "foundry.toml"
    out_str: str = """
    [profile.default]
    solc-version = "0.8.20"
    optimizer = true
    optimizer_runs = 100000000
    via_ir = true
    """
    with open(foundry_config, "w", encoding="utf-8") as outfile:
        outfile.write(out_str)

    # Delete unnecessary files
    counter_path = temp_dir / "src" / "Counter.sol"
    counter_path.unlink()
    assert not counter_path.exists()

    counter_test_path = temp_dir / "test" / "Counter.t.sol"
    counter_test_path.unlink()
    assert not counter_test_path.exists()

    scripts_dir = temp_dir / "script"
    rmtree(scripts_dir)
    assert not scripts_dir.exists()

    with open(temp_dir / "test" / "Test.t.sol", "w", encoding="utf-8") as outfile:
        outfile.write(test_code)

    logger.log(INFO, "Running Forge test...")
    out = run(["forge", "test", "-vvv"], cwd=temp_dir, capture_output=True)

    stdout = out.stdout.decode().strip()
    stdout = escape_ansi(stdout)

    stderr = out.stderr.decode().strip()
    stderr = escape_ansi(stderr)

    return stderr + "\n" + stdout


if __name__ == "__main__":
    main()
