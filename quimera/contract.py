from logging import getLogger, INFO, ERROR

from eth_utils import to_checksum_address
from jsbeautifier import beautify
from requests.exceptions import HTTPError

from slither import Slither
from slither.tools.read_storage import read_storage
from slither.tools.read_storage.read_storage import SlitherReadStorage, RpcInfo
from slither.utils.code_generation import generate_interface
from slither.core.solidity_types.elementary_type import ElementaryType
from slither.core.declarations.contract import Contract

logger = getLogger("Quimera")

# EIP-1967 implementation slot (minus 1 and hashed)
IMPLEMENTATION_SLOT = (
    "0x360894A13BA1A3210667C828492DB98DCA3E2076CC3735A920A3CA505D382BBC"
)


def extract_contract_code_recursively(contract, visited):
    """
    Extracts the source code of a contract and its base contracts recursively.
    """
    logger.log(INFO, f"Processing contract: {contract.name}")
    code = contract.compilation_unit.core.source_code[
        contract.source_mapping.filename.absolute
    ]
    code = beautify(code, opts={"indent_size": 2, "preserve_newlines": False})

    for base in contract.inheritance:
        logger.log(INFO, f"Processing base contract: {base.name}")

        if base.name in ["Context", "Ownable", "Pausable", "AccessControl", "ReentrancyGuard", "EIP712", "ERC20Permit"]:
            logger.log(INFO, f"Skipping {base.name} base contract.")
            visited.add(base.name)
            continue

        if base.name in visited:
            logger.log(INFO, f"Skipping already visited base contract: {base.name}")
            continue

        if base.is_interface:
            logger.log(INFO, f"Skipping interface base contract: {base.name}")
            continue

        visited.add(base.name)

        base_code = extract_contract_code_recursively(base, visited)
        code += "\n\n" + base_code

    for library in contract.all_library_calls:
        logger.log(INFO, f"Processing library: {library.destination}")
        if library.destination.name in visited:
            logger.log(INFO, f"Skipping already visited library: {library.destination}")
            continue

        if library.destination.name in ["Strings", "Address", "SafeMath", "SafeERC20", "ShortStrings", "ECDSA"]:
            logger.log(INFO, f"Skipping library: {library.destination.name}")
            visited.add(library.destination.name)
            continue

        visited.add(library.destination.name)

        library_code = extract_contract_code_recursively(library.destination, visited)
        code += "\n\n" + library_code

    return code


def get_base_contract(target):
    Slither.logger.disabled = True
    slither = Slither(target, foundry_compile_all=True)
    base_contract = slither.get_contract_from_name("QuimeraBaseTest")
    if base_contract == []:
        logger.log(
            ERROR, "QuimeraBaseTest contract not found in the provided source code."
        )
        assert False

    base_contract = base_contract[0]

    src_mapping = base_contract.source_mapping
    base_code = base_contract.compilation_unit.core.source_code[
        src_mapping.filename.absolute
    ]
    return base_code

source_code_cache = {}

def get_contract_info(target, rpc_url, block_number, chain, args):
    if "0x" in target:
        target = to_checksum_address(target)
        rpc_info = RpcInfo(rpc_url, int(block_number))
        impl_raw = rpc_info.web3.eth.get_storage_at(target, IMPLEMENTATION_SLOT)
        implementation = "0x" + impl_raw[-20:].hex()
        if implementation != "0x0000000000000000000000000000000000000000":
            implementation = to_checksum_address(implementation)
            logger.log(INFO, f"Proxy detected, using target address {implementation}")
        else:
            implementation = target

        try:
            slither = Slither(chain + ":" + implementation, **vars(args))
            logger.log(INFO, slither)
        except HTTPError as e:
            logger.log(
                ERROR,
                f"Error fetching source code for {target} at block {block_number}: {e}",
            )
            return {}
        except ValueError:
            logger.log(
                ERROR,
                f"Error fetching source code for {target} at block {block_number}",
            )
            return {}
        global source_code_cache
        source_code_cache[target] = "Already part of the original instructions, not requesting again."
    else:
        slither = Slither(target, foundry_compile_all=True)
        base_contract = slither.get_contract_from_name("QuimeraBaseTest")
        if base_contract == []:
            logger.log(
                ERROR, "QuimeraBaseTest contract not found in the provided source code."
            )
            assert False

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

            if contract.is_interface:
                continue

            number_entry_points = len(contract.functions_entry_points)
            if number_entry_points > max_functions:
                max_functions = number_entry_points
                contract_name = contract.name

    contracts_names = [contract.name for contract in contracts]
    logger.info(f"Contracts found: {contracts_names}, selected {contract_name}")
    _contract = slither.get_contract_from_name(contract_name)[0]

    internal_contracts = set([_contract.name])
    if len(_contract.compilation_unit.core.source_code) > 1:
        target_code = extract_contract_code_recursively(
            _contract, internal_contracts
        )
    else:
        src_mapping = _contract.source_mapping
        target_code = _contract.compilation_unit.core.source_code[
            src_mapping.filename.absolute
        ]
        target_code = beautify(
            target_code, opts={"indent_size": 2, "preserve_newlines": False}
        )

    interface = generate_interface(
        contract=_contract,
        unroll_structs=False,
        include_events=False,
        include_errors=False,
        include_enums=True,
        include_structs=True,
    )

    history = """struct History {
        Checkpoint[] checkpoints;
    }"""

    interface = interface.replace(history, "")
    interface = interface.replace("function collateralConfig() external returns (CollateralConfig memory);", "")

    variables_values = ""
    if "0x" in target:
        srs = SlitherReadStorage([_contract], max_depth=20, rpc_info=rpc_info)
        srs.storage_address = target

        contract_vars = set()
        logger.log(INFO, internal_contracts)
        for contract_name in internal_contracts:
            contract = slither.get_contract_from_name(contract_name)[0]
            for var in contract.state_variables:
                keep = False
                if "mapping" in str(var.type):
                    continue

                if isinstance(var.type, ElementaryType) and (
                    "uint" in var.type.name
                    or var.type.name == "bool"
                    or var.type.name == "address"
                ):
                    keep = True

                if type(var.type.type) == Contract:
                    keep = True

                if keep:
                    contract_vars.add(var.name)

        logger.log(INFO, contract_vars)
        read_storage.logger.disabled = True
        srs.get_all_storage_variables(lambda x: x.name in contract_vars)
        srs.get_target_variables()
        srs.walk_slot_info(srs.get_slot_values)

        for var in srs.slot_info.values():
            if var.size == 160: # A dirty trick to detect addresses
                variables_values += f"{var.name} = 0x{var.value}\n".replace("0x0x", "0x")
            else:
                variables_values += f"{var.name} = {var.value}\n"

    return {
        "target_address": target,
        "interface": interface,
        "target_code": target_code,
        "variables_values": variables_values,
        "contract_name": _contract.name,
        "is_erc20": _contract.is_erc20,
    }

def get_contract_info_as_text(target, rpc_url, block_number, chain, args):
    logger.log(INFO, f"Executing get_contract_info_as_text for address {target}")
    global source_code_cache
    if target in source_code_cache:
        logger.log(INFO, "Using cached contract info.")
        return source_code_cache[target]

    source_code_cache[target] = "Already requested, not requesting again."
    contract_info = get_contract_info(target, rpc_url, block_number, chain, args)
    if contract_info == {}:
        source_code_cache[target] = (
            "No source code available for the provided address. This address contains either an EOA or a contract without source code available"
        )
        return source_code_cache[target]
    text = f"""The contract with address {contract_info["target_address"]} contains a {contract_info["contract_name"]} contract with the following interface:

{contract_info["interface"]}

Its source code is:

```solidity
{contract_info["target_code"]}
```

The contract has a number of public/private variables, these are their current values:
{contract_info["variables_values"]}"""
    logger.log(INFO, "Contract info text generated successfully.")
    return text.strip()
