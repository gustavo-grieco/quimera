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
        return "0x10ED43C718714eb63d5aA57B78B54704E256024E"
    else:
        raise ValueError("Unsupported chain")


def get_flashloan_provider(chain):
    if chain == "mainnet":
        return "0xBA12222222228d8Ba445958a75a0704d566BF2C8"
    elif chain == "bsc":
        return "0x6098A5638d8D7e9Ed2f952d35B2b67c34EC6B476"
    else:
        raise ValueError("Unsupported chain")


def get_flashloan_call(chain):
    if chain == "mainnet":
        return 'IBalancerVault(flashloanProvider).flashLoan(address(this), tokens, amounts, "");'
    elif chain == "bsc":
        return (
            'IDODO(flashloanProvider).flashLoan(amounts[0], 0, address(this), "0x0");'
        )
    else:
        raise ValueError("Unsupported chain")


def get_flashloan_receiver(chain):
    if chain == "mainnet":
        return """
    function receiveFlashLoan(
        IERC20[] memory,
        uint256[] memory amounts,
        uint256[] memory,
        bytes memory
    ) external {
        uint256 amount = amounts[0];
    """
    elif chain == "bsc":
        return """
    function DPPFlashLoanCall(address, uint256 amount, uint256, bytes memory) external {
    """
    else:
        raise ValueError("Unsupported chain")
