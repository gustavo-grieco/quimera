def get_valuable_token_address(name, chain):
    if name == "weth":
        return get_weth_address(chain)
    elif name == "usdc":
        if chain == "arbi":
            return "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
        else:
            return "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    elif name == "arb":
        if chain == "arbi":
            return "0x912CE59144191C1204E64559FE8253a0e49E6548"
        else:
            raise ValueError("ARB token is only available on Arbitrum")

def get_weth_address(chain):
    if chain == "mainnet":
        return "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
    elif chain == "bsc":
        return "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
    elif chain == "arbi":
        return "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1"
    else:
        raise ValueError("Unsupported chain")


def get_uniswap_router_address(chain):
    if chain == "mainnet":
        return "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
    elif chain == "arbi":
        return "0x8cFe327CEc66d1C090Dd72bd0FF11d690C33a2Eb"
    elif chain == "bsc":
        return "0x10ED43C718714eb63d5aA57B78B54704E256024E"
    else:
        raise ValueError("Unsupported chain")


def get_flashloan_provider(chain):
    if chain == "mainnet" or chain == "arbi":
        return "0xBA12222222228d8Ba445958a75a0704d566BF2C8"
    elif chain == "bsc":
        return "0x6098A5638d8D7e9Ed2f952d35B2b67c34EC6B476"
    else:
        raise ValueError("Unsupported chain")


def get_flashloan_call(chain):
    if chain == "mainnet" or chain == "arbi":
        return 'IBalancerVault(flashloanProvider).flashLoan(address(this), tokens, amounts, "");'
    elif chain == "bsc":
        return (
            'IDODO(flashloanProvider).flashLoan(amounts[0], 0, address(this), "0x0");'
        )
    else:
        raise ValueError("Unsupported chain")


def get_flashloan_receiver(chain):
    if chain == "mainnet" or chain == "arbi":
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
