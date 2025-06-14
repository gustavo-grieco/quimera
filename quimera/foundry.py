from shutil import rmtree
from subprocess import run
from re import compile
from logging import getLogger, INFO

logger = getLogger(__name__)


def escape_ansi(line):
    ansi_escape = compile(r"(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", line)


def extract_info_from_trace(trace: str) -> str:
    """
    Extracts the reason for the failure from the trace output.
    It can be a reverted transaction or a compilation failure.
    :param trace: The trace output as a string.
    :return: The extracted information as a string.
    """
    # Split the trace into lines
    lines = trace.split("\n")
    # Initialize an empty list to store the extracted information
    extracted_info = []

    # Iterate through each line in the trace
    for line in lines:
        # Check if the line contains a failure message
        if "[FAIL:" in line:
            line = line.split("[FAIL:")[1]
            line = line.split("]")[0]
            extracted_info.append(line.strip())
            break

        if "Compilation failed" in line:
            extracted_info.append("Compilation failed.")
            break

    # Join the extracted information into a single string
    return (
        "\n".join(extracted_info) if extracted_info else "No failure information found."
    )


foundry_toml = """
[profile.default]
solc-version = "0.8.20"
optimizer = true
optimizer_runs = 100000000
via_ir = true
evm_version = "cancun"
"""


def install_and_run_foundry(temp_dir, test_code, rpc_url) -> None:
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
    out_str: str = foundry_toml
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
    out = run(
        ["forge", "test", "-vvv", "--fork-url", rpc_url],
        cwd=temp_dir,
        capture_output=True,
    )

    stdout = out.stdout.decode().strip()
    stdout = escape_ansi(stdout)

    stderr = out.stderr.decode().strip()
    stderr = escape_ansi(stderr)

    return stderr + "\n" + stdout


def copy_and_run_foundry(temp_dir, test_code, rpc_url, test_name) -> None:
    """Copies the target contract to a temporary directory and runs the tests"""
    # Create a temporary directory valid for the session
    temp_dir.mkdir(parents=True, exist_ok=True)

    logger.log(INFO, "Copying target contract to temporary directory...")
    with open(temp_dir / f"{test_name}.t.sol", "w", encoding="utf-8") as outfile:
        outfile.write(test_code)

    logger.log(INFO, "Running Forge test...")
    out = run(
        ["forge", "test", "-vvv", "--fork-url", rpc_url, "--match-contract", test_name],
        cwd=temp_dir,
        capture_output=True,
    )

    stdout = out.stdout.decode().strip()
    stdout = escape_ansi(stdout)

    stderr = out.stderr.decode().strip()
    stderr = escape_ansi(stderr)

    return stderr + "\n" + stdout
