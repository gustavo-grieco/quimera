from setuptools import setup

lint_deps = ["ruff"]

extra_require = {
    "lint": lint_deps,
}

setup(
    name="quimera",
    version="0.1",
    description="Data-driven exploit generation for Ethereum smart contracts using LLMs and Foundry",
    long_description_content_type="text/markdown",
    long_description=open("README.md").read(),
    packages=["quimera"],
    license="AGPL3",
    entry_points="""
    [console_scripts]
    quimera = quimera.__main__:main
    """,
    install_requires=[
        "slither_analyzer",
        "llm",
    ],
    extras_require=extra_require,
    url="https://github.com/gustavo-grieco/quimera",
)
