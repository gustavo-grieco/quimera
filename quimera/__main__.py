#!/usr/bin/python3
# -*- coding: utf-8 -*-

from multiprocessing import set_start_method, Event, Queue, Process
from signal import signal, SIGINT, SIGTERM

from argparse import ArgumentParser, Namespace
from logging import basicConfig, getLogger, INFO, ERROR
from os import getenv
from sys import exit
from pathlib import Path
from random import randint
from time import sleep
from shutil import which

from llm import get_model
from llm.errors import ModelError
from llm import Tool

from quimera.tui import BackgroundTextEditor
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

from quimera.foundry import (
    install_and_run_foundry,
    copy_and_run_foundry,
    extract_info_from_trace,
)
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

    parser.add_argument(
        "--working-directory",
        help="The working directory to use for the project",
        type=str,
        default="/tmp",
    )
    return parser.parse_args()


def check_commands_installed(commands):
    return {cmd: which(cmd) is not None for cmd in commands}


def run_main_task(message_queue, shutdown_flag):
    """Run the main task in a separate process."""
    try:
        controller = MainTaskController(
            message_queue=message_queue, shutdown_flag=shutdown_flag
        )
        controller.run_main_task()
    except Exception as e:
        print(f"Main task process error: {e}")


class MainTaskController:
    """Controller for running main tasks in background process while UI runs in main process"""

    def __init__(self, message_queue=None, shutdown_flag=None):
        self.message_queue = message_queue or Queue()
        self.task_process = None
        self.editor_app = None
        self.working_directory = None
        self.shutdown_flag = shutdown_flag or Event()

    def start_background_task(self):
        """Start the main task in a background process"""
        self.task_process = Process(
            target=run_main_task,
            args=(self.message_queue, self.shutdown_flag),
            daemon=True,
        )
        self.task_process.start()
        sleep(1)  # Give task time to start

    def run_ui(self):
        """Run the UI in the main process"""
        self.editor_app = BackgroundTextEditor(self.message_queue, "./wd")
        self.editor_app.run()

    def send_message(self, msg_type: str, data: str):
        """Send a message to the UI"""
        self.message_queue.put({"type": msg_type, "data": data})

    def update_main_task_status(self, status: str):
        """Update main task status in UI"""
        self.send_message("status", status)

    def set_blocker(self, blocker: str):
        """Set a blocker message in UI"""
        self.send_message("blocker", blocker)

    def update_editor_status(self, status: str):
        """Update editor status in UI"""
        self.send_message("editor_status", status)

    def update_network_info(self, info: str):
        """Update network information in UI"""
        self.send_message("network_info", info)

    def change_directory(self, path: str):
        """Change the current directory in the UI"""
        self.send_message("change_directory", path)

    def open_modal(self, content: str):
        self.send_message("open_modal", content)

    def create_file_from_main(self, file_path: str, content: str):
        """Create/update a file from main task"""
        self.message_queue.put(
            {"type": "file_update", "file_path": file_path, "content": content}
        )

    def shutdown_task(self):
        """Signal the background task to shutdown gracefully"""
        self.send_message("shutdown", "shutdown")
        if self.task_process:
            self.task_process.join(timeout=2)
            if self.task_process.is_alive():
                print(
                    "Task process did not terminate gracefully, forcing termination..."
                )
                self.task_process.terminate()
                self.task_process.join()

        self.exit(0)

    def setup_signal_handlers(self):
        """Setup signal handlers in main process"""

        def signal_handler(signum, frame):
            print("\nShutting down...")
            self.shutdown_flag.set()
            self.shutdown_task()
            if self.editor_app:
                self.editor_app.exit()
            exit(0)

        signal(SIGINT, signal_handler)
        signal(SIGTERM, signal_handler)

    def log(self, level: int, message: str):
        pass  # log(level, message)

    def run_main_task(self):
        try:
            self.main()
        except Exception as e:
            logger.log(ERROR, f"An error occurred in the main task: {e}")
            self.shutdown_task()

    def main(self):
        args = parse_args()
        self.update_main_task_status("Starting Quimera... 🔱")

        self.working_directory = args.working_directory
        installed = check_commands_installed(["forge"])
        for cmd, installed in installed.items():
            if not installed:
                logger.log(
                    ERROR,
                    f"Error: {cmd} is not installed. Please install it to continue.",
                )
                exit(1)

        self.set_blocker("Waiting for network")
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
                raise ValueError(
                    "Please set the ETHERSCAN_API_KEY environment variable."
                )

            if api_key == "TODO":
                raise ValueError(
                    "Please set the ETHERSCAN_API_KEY environment variable to a valid API key."
                )
        else:
            self.working_directory = target
            logger.log(
                INFO,
                "Assuming local contract source file or directory with mainnet chain",
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
                self.log(
                    INFO,
                    f"Using block number {block_number} from environment variable.",
                )
        else:
            logger.log(
                INFO, f"Using block number {block_number} from command line argument."
            )

        rpc_url = getenv("FOUNDRY_RPC_URL")
        if rpc_url is None:
            raise ValueError("Please set the FOUNDRY_RPC_URL environment variable.")

        self.update_main_task_status("Fetching contract information 📡")
        self.update_network_info(f"{target} @ {chain} ({block_number})")
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

        args["constraints"] = constraints.replace(
            "$valuableTokenName", valuable_token.upper()
        )
        args["valuableTokenName"] = valuable_token.upper()
        args["assignFlashLoanAddress"] = (
            f"flashloanProvider = {get_flashloan_provider(chain)};"
        )
        args["assignValuableTokenAddress"] = (
            f"valuableToken = IERC20({get_valuable_token_address(valuable_token, chain)});"
        )
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
            args["variablesValues"] = f"{contract_info['variables_values']}"
        else:
            args["variablesValues"] = ""

        args["executeExploitCode"] = initial_execute_exploit_function
        self.create_file_from_main("", args["executeExploitCode"])
        if "0x" not in target:
            exploit_template = get_base_contract(target)
        else:
            exploit_template = test_contract_template

        test_code = SolidityTemplate(exploit_template).substitute(args)
        args["testCode"] = test_code.strip()

        self.update_main_task_status("Installing and running Foundry 🛠️")
        if "0x" in target:
            temp_dir = Path(
                self.working_directory, "quimera_foundry_sessions", target, "0"
            )
            self.change_directory(
                Path(self.working_directory, "quimera_foundry_sessions", target)
            )
            args["trace"] = install_and_run_foundry(temp_dir, test_code, rpc_url)
        else:
            test_code = test_code.replace("QuimeraBaseTest", "QuimeraTest")
            temp_dir = Path(target, "test", "quimera")
            args["trace"] = copy_and_run_foundry(
                temp_dir, test_code, rpc_url, "QuimeraTest"
            )
            self.change_directory(temp_dir)
            temp_dir = Path(target, "test", "quimera", "log", "0")

        self.set_blocker(extract_info_from_trace(args["trace"]))
        prompt = SolidityTemplate(initial_prompt_template).substitute(args)
        save_prompt_response(prompt, None, temp_dir)
        # assert False

        model = None
        tools = []
        conversation = None
        if model_name != "manual":
            model = get_model(model_name)  # get_async_model(name=model_name)
            tools = [
                Tool.function(
                    lambda address: get_contract_info_as_text(
                        address, rpc_url, block_number, chain, args
                    ),
                    name="get_contract_info_as_text",
                ),
                Tool.function(lambda x, y: x * y, name="multiply_big_numbers"),
                Tool.function(lambda x, y: x + y, name="add_big_numbers"),
                Tool.function(lambda x, y: x - y, name="subtract_big_numbers"),
            ]
            # start the llm converation
            conversation = model.conversation(tools=tools)

        profit_found = False
        for iteration in range(1, max_iterations + 1):
            # logger.log(INFO, f"Iteration {iteration}")
            # logger.log(INFO, f"Prompt: {prompt}")
            # logger.log(INFO, "Getting response from model...")
            response = None

            while response is None:
                try:
                    if model == "manual":
                        self.update_main_task_status(
                            f"Waiting for user input... ☎️ ({iteration}/{max_iterations})"
                        )
                        self.create_file_from_main(
                            "/tmp/quimera.prompt.txt",
                            "Your current prompt was copied to the clipboard. Delete everything (alt + t), paste the response here, save (ctrl + o) and exit (ctrl + x)",
                        )
                    else:
                        self.update_main_task_status(
                            f"Waiting response from LLM 🧠 ({iteration}/{max_iterations})"
                        )
                    response = get_response(conversation, prompt, tools)
                except ModelError as e:
                    self.update_main_task_status(
                        f"Error getting response from model: {e} ❌ ({iteration}/{max_iterations})"
                    )

                if response is not None:
                    sleep(randint(1, 2))
                    break

                for _ in range(10 + randint(0, 10)):
                    try:
                        sleep(1)
                    except KeyboardInterrupt:
                        self.shutdown_task()

            args["executeExploitCode"] = response.strip()
            if "```" in args["executeExploitCode"]:
                args["executeExploitCode"] = args["executeExploitCode"].replace(
                    "solidity", ""
                )
                # Remove the code block markers
                args["executeExploitCode"] = args["executeExploitCode"].split("```")[1]

            self.create_file_from_main("", args["executeExploitCode"])
            test_code = SolidityTemplate(exploit_template).substitute(args)
            args["testCode"] = test_code

            self.update_main_task_status(
                f"Installing and running Foundry 🛠️ ({iteration}/{max_iterations})"
            )
            if "0x" in target:
                temp_dir = Path(
                    self.working_directory,
                    "quimera_foundry_sessions",
                    target,
                    str(iteration),
                )
                self.change_directory(
                    Path(self.working_directory, "quimera_foundry_sessions", target)
                )
                args["trace"] = install_and_run_foundry(temp_dir, test_code, rpc_url)
            else:
                test_code = test_code.replace("QuimeraBaseTest", "QuimeraTest")
                temp_dir = Path(target, "test", "quimera")
                args["trace"] = copy_and_run_foundry(
                    temp_dir, test_code, rpc_url, "QuimeraTest"
                )
                self.change_directory(temp_dir)
                temp_dir = Path(target, "test", "quimera", "log", str(iteration))

            self.set_blocker(extract_info_from_trace(args["trace"]))
            save_prompt_response(prompt, response, temp_dir)
            # logger.log(INFO, f"Trace/output: {args['trace']}")
            if (
                "Suite result: FAILED" in args["trace"]
                or "Compiler run failed" in args["trace"]
            ):
                pass
                # logger.log(INFO, "Test failed, continuing to next iteration...")
            elif "[PASS] testFlaw()" in args["trace"]:
                profit_found = True
                self.update_main_task_status(
                    f"Test passed, profit was found! 🎉 ({iteration}/{max_iterations})"
                )
                logger.log(INFO, "Test passed, profit was found! 🎉")
                self.create_file_from_main("", args["trace"])
                break
            else:
                assert False, "Test result is not clear, please check the output."

            prompt = SolidityTemplate(next_prompt_template).substitute(args)

        if not profit_found:
            self.shutdown_task()


def main():
    # Ensure multiprocessing works correctly on macOS
    set_start_method("spawn", force=True)

    # Run with UI in main process and main task in background
    controller = MainTaskController()

    # Setup signal handlers in main process
    controller.setup_signal_handlers()

    # Start main task in background
    try:
        controller.start_background_task()
    except Exception as e:
        assert False, f"Failed to start main task: {e}"

    # Run UI in main process
    controller.run_ui()


if __name__ == "__main__":
    main()
