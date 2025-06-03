from logging import getLogger, INFO, WARNING

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

def get_contract_info(target, rpc_url, block_number, chain, args):
    target = to_checksum_address(target)

    rpc_info = RpcInfo(rpc_url, int(block_number))
    impl_raw = rpc_info.web3.eth.get_storage_at(target, IMPLEMENTATION_SLOT)
    implementation = "0x" + impl_raw[-20:].hex()
    if implementation != "0x0000000000000000000000000000000000000000":
        target = implementation
        target = to_checksum_address(target)
        logger.log(INFO, f"Proxy detected, using target address {target}")

    slither = Slither(chain + ":" + target, **vars(args))

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

    src_mapping = _contract.source_mapping
    target_code = _contract.compilation_unit.core.source_code[
        src_mapping.filename.absolute
    ]

    target_code = beautify(target_code, opts={"indent_size": 2, "preserve_newlines": False})

    if len(_contract.compilation_unit.core.source_code) > 1:
        for c in _contract.inheritance:
            if c.is_abstract:
                continue
            if c.is_interface:
                continue
            print(
                f"Contract {c.name} has {len(c.functions_entry_points)} entry points."
            )
            src_mapping = c.source_mapping
            target_code += (
                "\n"
                + c.compilation_unit.core.source_code[src_mapping.filename.absolute]
            )

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
        # if var.is_internal:
        if not (
            isinstance(var.type, ElementaryType)
            and var.type.name in ["uint256", "bool"]
        ):
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

    return {
        "target_address": target,
        "implementation": implementation,
        "interface": interface,
        "target_code": target_code,
        "token_address": token_address,
        "private_variables_values": private_variables_values,
        "contract_name": contract.name,
    }

def get_contract_info_as_text(target, rpc_url, block_number, chain, args):
    contract_info = get_contract_info(target, rpc_url, block_number, chain, args)
    text = f"""
    Contract Name: {contract_info['contract_name']}
    Target Address: {contract_info['target_address']}
    Implementation Address: {contract_info['implementation']}
    Token Address: {contract_info['token_address']}
    Interface:
    {contract_info['interface']}
    Target Code:
    {contract_info['target_code']}
    Private Variables Values:
    {contract_info['private_variables_values']}
    """
    return text.strip()