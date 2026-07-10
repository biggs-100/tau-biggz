"""Welcome modal shown on first TUI run when login is required."""

from __future__ import annotations

from typing import ClassVar, Literal

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

type BindingEntry = Binding | tuple[str, str] | tuple[str, str, str]


class WelcomeScreen(ModalScreen[Literal["configure"] | None]):
    """Welcome modal shown on first-run when login is required."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "dismiss_later", "Later"),
    ]

    DEFAULT_CSS = """
    WelcomeScreen {
        align: center middle;
    }
    WelcomeScreen > #welcome-dialog {
        width: 50;
        height: auto;
        padding: 2 3;
        border: thick $border;
        background: $surface;
    }
    WelcomeScreen > #welcome-dialog > #welcome-title {
        text-style: bold;
        content-align: center top;
        padding: 0 0 1 0;
    }
    WelcomeScreen > #welcome-dialog > #welcome-body {
        padding: 0 0 1 0;
    }
    WelcomeScreen > #welcome-dialog > #welcome-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }
    WelcomeScreen > #welcome-dialog > #welcome-buttons Button {
        margin: 1 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="welcome-dialog"):
            yield Static("Welcome to Tau", id="welcome-title")
            yield Static(
                "You need to configure a provider to start working.\n"
                "Choose a provider and enter your credentials to begin.",
                id="welcome-body",
            )
            with Vertical(id="welcome-buttons"):
                yield Button("Configure now", id="welcome-configure", variant="primary")
                yield Button("Later", id="welcome-later", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        if event.button.id == "welcome-configure":
            self.dismiss("configure")
        else:
            self.dismiss(None)

    def action_dismiss_later(self) -> None:
        """Escape key: dismiss as 'Later'."""
        self.dismiss(None)
