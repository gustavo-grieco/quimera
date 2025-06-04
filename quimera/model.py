import asyncio

from datetime import datetime
from signal import SIGINT, SIGTERM
from subprocess import run
from sys import platform


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
        run(
            ["xclip", "-selection", "clipboard", "-in", "/tmp/quimera.prompt.txt"],
            check=True,
        )
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


def get_response(conversation, prompt):
    if conversation is None:
        return resolve_prompt(prompt)
    else:
        return get_async_response(conversation, prompt)
