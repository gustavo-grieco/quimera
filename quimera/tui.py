#!/usr/bin/env python3
"""
Text Editor that runs in main process while main task executes in background using multiprocessing
"""

import multiprocessing
import queue
from pathlib import Path
from datetime import datetime
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import TextArea, Header, Static, DirectoryTree, Footer
from textual.binding import Binding

class BackgroundTextEditor(App):
    """Text editor that runs in main process."""

    CSS = """
    DirectoryTree {
        dock: left;
        width: 30;
        border-right: solid $primary;
        scrollbar-size: 0 0;
    }

    TextArea {
        border: solid $primary;
    }

    .top-status-bar {
        dock: top;
        height: 3;
        background: $surface;
        border-bottom: solid $primary;
        padding: 0;
    }

    .status-widget {
        width: 1fr;
        height: 100%;
        border-right: solid $primary;
        padding: 0 1;
        content-align: center middle;
        text-align: center;
    }

    .status-widget:last-child {
        border-right: none;
    }

    .bottom-status-bar {
        dock: bottom;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("ctrl+s", "save_file", "Save and confirm"),
        Binding("ctrl+c", "clear_file", "Clear editor"),
    ]

    def __init__(self, message_queue=None, directory_tree_path="."):
        super().__init__()
        self.message_queue = message_queue or multiprocessing.Queue()
        self.current_file_path = None
        self.file_saved = True
        self.original_content = ""
        self.directory_tree_path = directory_tree_path

        # Status bar values
        self.current_status = "Starting.."
        self.current_blocker = "None"
        self.main_task_status = "Waiting"
        self.network_information = "No network info"
        self.start_time = datetime.now()

        self.waiting_for_user_input = False  # Flag to check if waiting for user input
        self.user_confirmed_answer = False  # Flag to check if user confirmed answer

    def compose(self) -> ComposeResult:
        yield Header()

        # Top status bar
        with Horizontal(classes="top-status-bar"):
            yield Static(
                f"[bold]BLOCKER[/bold]: {self.current_blocker}",
                classes="status-widget",
                id="status-widget",
            )
            yield Static(
                f"[bold]STATUS[/bold]: {self.main_task_status}",
                classes="status-widget",
                id="task-widget",
            )

        with Horizontal():
            yield DirectoryTree(str(self.directory_tree_path), id="tree")
            with Vertical():
                yield TextArea("", language="solidity", id="editor")
                yield Footer()

        yield Static("", classes="bottom-status-bar", id="bottom-status")

    def on_mount(self) -> None:
        self.theme = "textual-dark"
        editor = self.query_one("#editor", TextArea)
        editor.cursor_blink = False
        editor.compact = True
        editor.read_only = True
        editor.focus()
        # self._update_bottom_status()

        # Check for messages from background process
        self.set_interval(0.1, self._check_message_queue)
        self.set_interval(1.0, self._update_time_display)

    def _check_message_queue(self) -> None:
        """Check for messages from background process"""
        try:
            while True:
                message = self.message_queue.get_nowait()
                self._handle_main_process_message(message)
        except queue.Empty:
            pass

    def _handle_main_process_message(self, message: dict) -> None:
        """Handle messages from background process"""
        msg_type = message.get("type", "")

        if msg_type == "status":
            self.main_task_status = message.get("data", "Unknown")
        elif msg_type == "blocker":
            self.current_blocker = message.get("data", "None")
        elif msg_type == "editor_status":
            self.current_status = message.get("data", "Ready")
        elif msg_type == "network_info":
            self.network_information = message.get("data", "")
        elif msg_type == "change_directory":
            # Change directory in the DirectoryTree
            new_path = message.get("data", str(Path.cwd()))
            self.directory_tree_path = new_path
            self._update_directory_tree()
        elif msg_type == "file_update":
            # Update a file with content from background process
            file_path = message.get("file_path")
            content = message.get("content", "")
            if file_path:
                self._update_file_from_main(file_path, content)
            else:
                editor = self.query_one("#editor", TextArea)
                editor.text = content
        elif msg_type == "shutdown":
            # Graceful shutdown request
            self.exit()

        self._update_status_display()

    def _update_file_from_main(self, file_path: str, content: str) -> None:
        """Update editor with file from background process"""
        try:
            path = Path(file_path)
            content = None
            with open(path, "r") as f:
                content = f.read(content)

            editor = self.query_one("#editor", TextArea)
            editor.text = content
            editor.read_only = False
            self.original_content = content
            self.file_saved = True
            self.current_file_path = path
            editor.focus()
            self._update_status_display()

        except Exception as e:
            self.current_blocker = f"File update error: {str(e)}"

    def _update_directory_tree(self) -> None:
        """Update the DirectoryTree widget"""
        try:
            dir_path = str(
                Path(self.directory_tree_path).resolve()
            )  # Ensure path is valid and absolute
            directory_tree = self.query_one("#tree", DirectoryTree)
            directory_tree.path = dir_path  # Update the DirectoryTree path
            directory_tree.reload()  # Force reload of the directory tree
            directory_tree.show_horizontal_scrollbar = False
            directory_tree.show_vertical_scrollbar = False
        except Exception as e:
            self.current_blocker = f"Directory reload error: {str(e)}"
        self._update_status_display()

    def _get_elapsed_time(self) -> str:
        elapsed = datetime.now() - self.start_time
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _update_time_display(self) -> None:
        time_widget = self.query_one("#bottom-status", Static)
        time_widget.update(
            f"[bold]TARGET[/bold]: {self.network_information}"
        )  # , [bold]TIME[/bold]: {self._get_elapsed_time()}")

    def _update_status_display(self) -> None:
        status_widget = self.query_one("#status-widget", Static)
        task_widget = self.query_one("#task-widget", Static)

        status_widget.update(f"[bold]BLOCKER[/bold]: {self.current_blocker}")
        task_widget.update(f"[bold]STATUS[/bold]: {self.main_task_status}")

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        """Handle file selection from directory tree."""
        if event.path.is_file:
            file_path = event.path
            with open(str(file_path), "r", encoding="utf-8") as f:
                content = f.read()

            # Update the editor
            editor = self.query_one("#editor", TextArea)
            editor.text = content
            editor.cursor_location = (0, 0)
            editor.focus()

    def action_save_file(self) -> None:
        editor = self.query_one("#editor", TextArea)

        if self.current_file_path:
            try:
                with open(self.current_file_path, "w", encoding="utf-8") as f:
                    f.write(editor.text)
                self.original_content = editor.text
                self.file_saved = True
                self.current_status = "Saved"
                editor.text = ""
                self._update_status_display()
            except Exception as e:
                self.current_blocker = f"Save error: {str(e)}"

    def action_clear_file(self) -> None:
        editor = self.query_one("#editor", TextArea)
        editor.text = ""
        editor.cursor_location = (0, 0)
        self.original_content = ""
        self.file_saved = False
        editor.focus()
        self._update_status_display()
        # self._update_bottom_status()
