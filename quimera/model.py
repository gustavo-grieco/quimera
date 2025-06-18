import asyncio

from datetime import datetime
from signal import SIGINT, SIGTERM
from subprocess import run
from sys import platform
from pathlib import Path
from shutil import copyfile
from logging import getLogger, INFO

logger = getLogger("Quimera")
logger.setLevel(INFO)

def get_async_response(conversation, prompt, tools):
    """
    Get the response from the model asynchronously.
    :param model: The model to use for the response.
    :param prompt: The prompt to send to the model.
    :return: The response from the model.
    """

    async def fetch_response():
        response = ""
        response_obj = conversation.chain(prompt, tools=tools)
        async for chunk in response_obj:
            # print(chunk, end="", flush=True)
            response += chunk
        return response

    loop = asyncio.get_event_loop()
    main_task = asyncio.ensure_future(fetch_response())

    for signal in [SIGINT, SIGTERM]:
        loop.add_signal_handler(signal, main_task.cancel)
    try:
        answer = loop.run_until_complete(main_task)
    except asyncio.CancelledError:
        logger.log(INFO, "Execution interrupted by user.")
        exit(1)

    return answer


def get_sync_response(conversation, prompt, tools):
    """
    Get the response from the model synchronously.
    :param conversation: The conversation object to use for the response.
    :param prompt: The prompt to send to the model.
    :return: The response from the model.
    """
    response = ""
    chain = conversation.chain(prompt, tools=tools)
    for response_obj in chain.responses():
        logger.log(INFO, response_obj.tool_calls())
        for chunk in response_obj:
            response += chunk
    return response


def resolve_prompt(prompt, working_dir):
    # Write prompt to tmp.txt
    with open(Path(working_dir, "quimera.prompt.txt"), "w") as file:
        file.write(prompt)

    # Open nano to edit the prompt
    if platform == "darwin":
        if working_dir != "/tmp":
            copyfile(Path(working_dir, "quimera.prompt.txt"), "/tmp/quimera.prompt.txt")
        # In general, shell=True is not recommended, but here only we use it to pipe the content to pbcopy (there is no other way)
        run("cat /tmp/quimera.prompt.txt | pbcopy", shell=True)
    elif platform == "linux":
        run(
            [
                "xclip",
                "-selection",
                "clipboard",
                "-in",
                Path(working_dir, "quimera.prompt.txt"),
            ],
            check=True,
        )
    else:
        raise ValueError("Unsupported platform.")

    instructions = "Your current prompt was copied to the clipboard. Delete everything (ctrl + x), paste the response here and confirm (ctrl + c)"
    # overwrite the prompt with instructions
    with open(Path(working_dir, "quimera.answer.txt"), "w") as file:
        file.write(instructions)

    return instructions


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
