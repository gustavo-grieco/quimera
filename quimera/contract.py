from logging import getLogger, INFO, ERROR

from eth_utils import to_checksum_address
from jsbeautifier import beautify

from slither import Slither
from slither.tools.read_storage import read_storage
from slither.tools.read_storage.read_storage import SlitherReadStorage, RpcInfo
from slither.utils.code_generation import generate_interface
from slither.core.solidity_types.elementary_type import ElementaryType

logger = getLogger(__name__)

# EIP-1967 implementation slot (minus 1 and hashed)
IMPLEMENTATION_SLOT = (
    "0x360894A13BA1A3210667C828492DB98DCA3E2076CC3735A920A3CA505D382BBC"
)


def extract_contract_code_recursively(contract, visited):
    """
    Extracts the source code of a contract and its base contracts recursively.
    """
    print(f"Processing contract: {contract.name}")
    code = contract.compilation_unit.core.source_code[
        contract.source_mapping.filename.absolute
    ]
    code = beautify(code, opts={"indent_size": 2, "preserve_newlines": False})

    for base in contract.inheritance:
        print(f"Processing base contract: {base.name}")
        if base.name in visited:
            print(f"Skipping already visited base contract: {base.name}")
            continue

        if base.is_interface:
            print(f"Skipping interface base contract: {base.name}")
            continue

        visited.add(base.name)

        base_code = extract_contract_code_recursively(base, visited)
        code += "\n\n" + base_code

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

        slither = Slither(chain + ":" + implementation, **vars(args))
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

    if len(_contract.compilation_unit.core.source_code) > 1:
        target_code = extract_contract_code_recursively(
            _contract, set([_contract.name])
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
        include_enums=False,
        include_structs=True,
    )

    history = """struct History {
        Checkpoint[] checkpoints;
    }"""

    interface = interface.replace(history, "")

    variables_values = ""
    if "0x" in target:
        srs = SlitherReadStorage([_contract], max_depth=20, rpc_info=rpc_info)
        srs.storage_address = implementation

        contract_vars = []
        for var in _contract.state_variables:
            # if var.is_internal:
            if not (
                isinstance(var.type, ElementaryType)
                and (
                    "uint" in var.type.name
                    or var.type.name == "bool"
                    or var.type.name == "address"
                )
            ):
                continue

            contract_vars.append(var.name)

        read_storage.logger.disabled = True
        srs.get_all_storage_variables(lambda x: x.name in contract_vars)
        srs.get_target_variables()
        srs.walk_slot_info(srs.get_slot_values)

        for var in srs.slot_info.values():
            variables_values += f"{var.name} = {var.value}\n"

    return {
        "target_address": target,
        "interface": interface,
        "target_code": target_code,
        "variables_values": variables_values,
        "contract_name": contract.name,
        "is_erc20": _contract.is_erc20,
    }


def get_contract_info_as_text(target, rpc_url, block_number, chain, args):
    contract_info = get_contract_info(target, rpc_url, block_number, chain, args)
    text = f"""The contract with address {contract_info["target_address"]} contains a {contract_info["contract_name"]} contract with the following interface:

{contract_info["interface"]}

Its source code is:

```solidity
{contract_info["target_code"]}
```

The contract has a number of public/private variables, these are their current values:
{contract_info["variables_values"]}"""
    assert False
    return text.strip()
