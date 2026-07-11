"""Login, OAuth, and authentication screens for Tau TUI."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

from tau_coding.credentials import OAuthCredential
from tau_coding.oauth import OAuthAuthInfo, OAuthPrompt
from tau_coding.provider_catalog import ProviderCatalogEntry
from tau_coding.tui.config import TuiTheme

type BindingEntry = Binding | tuple[str, str] | tuple[str, str, str]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _login_provider_label(provider: ProviderCatalogEntry) -> str:
    return f"{provider.display_name} — {provider.name}"


# ── Screen classes ───────────────────────────────────────────────────────────


class LoginProviderPickerScreen(ModalScreen[str | None]):
    """Provider picker for the TUI login flow."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "select_cursor", "Select", show=False),
    ]

    def __init__(
        self,
        providers: Sequence[ProviderCatalogEntry],
        *,
        theme: TuiTheme,
        title: str = "Login",
    ) -> None:
        super().__init__()
        self.providers = tuple(providers)
        self.theme = theme
        self.title_text = title

    def compose(self) -> ComposeResult:
        """Compose the provider picker."""
        with Vertical(id="login-provider-picker"):
            yield Static(self.title_text, id="login-provider-title")
            yield ListView(
                *[
                    ListItem(Label(_login_provider_label(provider), markup=False))
                    for provider in self.providers
                ],
                id="login-provider-list",
            )
            yield Static("Enter selects - Escape closes", id="login-provider-help")

    def on_mount(self) -> None:
        """Focus the provider list."""
        provider_list = self.query_one("#login-provider-list", ListView)
        provider_list.index = 0
        provider_list.focus()

    def on_key(self, event: Key) -> None:
        """Route provider picker keys to the list."""
        if event.key == "up":
            event.stop()
            self.action_cursor_up()
        elif event.key == "down":
            event.stop()
            self.action_cursor_down()
        elif event.key == "enter":
            event.stop()
            self.action_select_cursor()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Dismiss with the selected provider name."""
        self.dismiss(self.providers[event.index].name)

    def action_cursor_up(self) -> None:
        """Move to the previous provider."""
        self.query_one("#login-provider-list", ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move to the next provider."""
        self.query_one("#login-provider-list", ListView).action_cursor_down()

    def action_select_cursor(self) -> None:
        """Select the highlighted provider."""
        self.query_one("#login-provider-list", ListView).action_select_cursor()

    def action_cancel(self) -> None:
        """Close without selecting a provider."""
        self.dismiss(None)


@dataclass(frozen=True, slots=True)
class CustomProviderLoginResult:
    """Provider details collected by the custom-provider login flow."""

    provider_name: str
    display_name: str
    base_url: str
    api_key_env: str
    models: tuple[str, ...]
    default_model: str
    api_key: str
    kind: str = "openai-compatible"


class LoginMethodPickerScreen(ModalScreen[str | None]):
    """Login method picker for the TUI login flow."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("up", "cursor_up", "Up", show=False, priority=True),
        Binding("down", "cursor_down", "Down", show=False, priority=True),
        Binding("enter", "select_cursor", "Select", show=False, priority=True),
    ]

    def __init__(self, *, theme: TuiTheme) -> None:
        super().__init__()
        self.theme = theme

    def compose(self) -> ComposeResult:
        """Compose the login method picker."""
        with Vertical(id="login-method-picker"):
            yield Static("Login", id="login-method-title")
            yield Static("Choose how to authenticate.", id="login-method-intro")
            yield LoginMethodListView(
                ListItem(
                    Label("Subscription — OAuth account", markup=False),
                    id="login-method-subscription",
                ),
                ListItem(
                    Label("API key — built-in provider", markup=False),
                    id="login-method-api-key",
                ),
                ListItem(
                    Label("Custom provider — OpenAI-compatible", markup=False),
                    id="login-method-custom",
                ),
                id="login-method-list",
            )
            yield Static("Enter selects - Escape closes", id="login-method-help")

    def on_mount(self) -> None:
        """Focus the default subscription method."""
        method_list = self.query_one("#login-method-list", ListView)
        method_list.index = 0
        method_list.focus()

    def on_key(self, event: Key) -> None:
        """Route arrow keys between login method buttons."""
        if event.key == "up":
            event.stop()
            self.action_cursor_up()
        elif event.key == "down":
            event.stop()
            self.action_cursor_down()
        elif event.key == "enter":
            event.stop()
            self.action_select_cursor()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dismiss with the selected login method."""
        if event.button.id == "login-method-subscription":
            self.dismiss("subscription")
        elif event.button.id == "login-method-api-key":
            self.dismiss("api-key")
        elif event.button.id == "login-method-custom":
            self.dismiss("custom")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Dismiss with the selected login method."""
        if event.item.id == "login-method-subscription":
            self.dismiss("subscription")
        elif event.item.id == "login-method-api-key":
            self.dismiss("api-key")
        elif event.item.id == "login-method-custom":
            self.dismiss("custom")

    def action_cancel(self) -> None:
        """Close without selecting a login method."""
        self.dismiss(None)

    def action_cursor_up(self) -> None:
        """Focus the previous login method."""
        self._move_method_cursor(offset=-1)

    def action_cursor_down(self) -> None:
        """Focus the next login method."""
        self._move_method_cursor(offset=1)

    def action_select_cursor(self) -> None:
        """Select the currently focused login method."""
        self.query_one("#login-method-list", ListView).action_select_cursor()

    def _move_method_cursor(self, *, offset: int) -> None:
        method_list = self.query_one("#login-method-list", ListView)
        item_count = len(method_list.children)
        if item_count == 0:
            method_list.index = None
            return
        current_index = method_list.index if method_list.index is not None else 0
        method_list.index = (current_index + offset) % item_count


class LoginMethodListView(ListView):
    """List view with wrapping arrow navigation for the login method picker."""

    def action_cursor_up(self) -> None:
        """Move to the previous login method."""
        self._move_cursor(offset=-1)

    def action_cursor_down(self) -> None:
        """Move to the next login method."""
        self._move_cursor(offset=1)

    def _move_cursor(self, *, offset: int) -> None:
        item_count = len(self.children)
        if item_count == 0:
            self.index = None
            return
        current_index = self.index if self.index is not None else 0
        self.index = (current_index + offset) % item_count


class CustomProviderLoginScreen(ModalScreen[CustomProviderLoginResult | None]):
    """Prompt for adding an OpenAI-compatible custom provider."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    _INPUT_ORDER: ClassVar[tuple[str, ...]] = (
        "custom-provider-name",
        "custom-provider-display-name",
        "custom-provider-kind",
        "custom-provider-base-url",
        "custom-provider-api-key-env",
        "custom-provider-models",
        "custom-provider-default-model",
        "custom-provider-api-key",
    )

    def __init__(self, *, theme: TuiTheme) -> None:
        super().__init__()
        self.theme = theme

    def compose(self) -> ComposeResult:
        """Compose the custom provider prompt."""
        with Vertical(id="login-screen"):
            yield Static("Add custom provider", id="login-title")
            yield Static(
                "Short provider name is used in commands/config.",
                id="custom-provider-help",
            )
            yield Input(placeholder="Provider name/id, e.g. nebius", id="custom-provider-name")
            yield Input(
                placeholder="Display name shown in UI, e.g. Nebius AI Studio",
                id="custom-provider-display-name",
            )
            yield Input(
                placeholder="Provider kind (openai-compatible, anthropic, ...)",
                id="custom-provider-kind",
            )
            yield Input(
                placeholder="OpenAI-compatible base URL, e.g. https://api.studio.nebius.ai/v1",
                id="custom-provider-base-url",
            )
            yield Input(
                placeholder="API key environment variable fallback, e.g. NEBIUS_API_KEY",
                id="custom-provider-api-key-env",
            )
            yield Input(
                placeholder="Model ids, comma-separated, e.g. model-a, model-b",
                id="custom-provider-models",
            )
            yield Input(
                placeholder="Default model id, must be listed above",
                id="custom-provider-default-model",
            )
            yield Input(
                placeholder="Paste API key to save for this provider",
                password=True,
                id="custom-provider-api-key",
            )
            yield Static("Enter advances/saves - Escape closes", id="login-footer")

    def on_mount(self) -> None:
        """Focus the first provider-detail field."""
        self.query_one("#custom-provider-name", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Advance through fields, then dismiss with provider details."""
        input_id = event.input.id
        if input_id not in self._INPUT_ORDER:
            return
        event.stop()
        if input_id != self._INPUT_ORDER[-1]:
            self._focus_next(input_id)
            return
        result = self._collect_result()
        if result is not None:
            self.dismiss(result)

    def _focus_next(self, input_id: str) -> None:
        index = self._INPUT_ORDER.index(input_id)
        self.query_one(f"#{self._INPUT_ORDER[index + 1]}", Input).focus()

    def _collect_result(self) -> CustomProviderLoginResult | None:
        provider_name = self._field("custom-provider-name", "Provider name")
        if provider_name is None:
            return None
        base_url = self._field("custom-provider-base-url", "Base URL")
        if base_url is None:
            return None
        api_key_env = self._field("custom-provider-api-key-env", "API key environment variable")
        if api_key_env is None:
            return None
        models_text = self._field("custom-provider-models", "Model ids")
        if models_text is None:
            return None
        models = tuple(
            dict.fromkeys(item.strip() for item in models_text.split(",") if item.strip())
        )
        if not models:
            self.query_one("#custom-provider-help", Static).update(
                "At least one model id is required."
            )
            self.query_one("#custom-provider-models", Input).focus()
            return None
        default_model = self._field("custom-provider-default-model", "Default model")
        if default_model is None:
            return None
        if default_model not in models:
            self.query_one("#custom-provider-help", Static).update(
                "Default model must be included in the model list."
            )
            self.query_one("#custom-provider-default-model", Input).focus()
            return None
        api_key = self._field("custom-provider-api-key", "API key")
        if api_key is None:
            return None
        kind = self.query_one("#custom-provider-kind", Input).value.strip()
        kind = kind or "openai-compatible"
        display_name = self.query_one("#custom-provider-display-name", Input).value.strip()
        return CustomProviderLoginResult(
            provider_name=provider_name,
            display_name=display_name or provider_name,
            kind=kind,
            base_url=base_url,
            api_key_env=api_key_env,
            models=models,
            default_model=default_model,
            api_key=api_key,
        )

    def _field(self, input_id: str, label: str) -> str | None:
        value = self.query_one(f"#{input_id}", Input).value.strip()
        if value:
            return value
        self.query_one("#custom-provider-help", Static).update(f"{label} is required.")
        self.query_one(f"#{input_id}", Input).focus()
        return None

    def action_cancel(self) -> None:
        """Close without adding a provider."""
        self.dismiss(None)


class LoginScreen(ModalScreen[str | None]):
    """Password prompt for saving a provider API key."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, provider: ProviderCatalogEntry, *, theme: TuiTheme) -> None:
        super().__init__()
        self.provider = provider
        self.theme = theme

    def compose(self) -> ComposeResult:
        """Compose the provider login prompt."""
        with Vertical(id="login-screen"):
            yield Static(f"Login: {self.provider.display_name}", id="login-title")
            yield Static("Paste this provider's API key.", id="login-help")
            yield Input(placeholder="Paste API key", password=True, id="login-api-key")
            yield Static("Enter saves - Escape closes", id="login-footer")

    def on_mount(self) -> None:
        """Focus the API key field."""
        self.query_one("#login-api-key", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Dismiss with the submitted API key."""
        if event.input.id != "login-api-key":
            return
        event.stop()
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        """Close without saving."""
        self.dismiss(None)


class OAuthLoginScreen(ModalScreen[OAuthCredential | None]):
    """OAuth login flow for providers backed by subscription auth."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, provider: ProviderCatalogEntry, *, theme: TuiTheme) -> None:
        super().__init__()
        self.provider = provider
        self.theme = theme
        self._manual_code_future: asyncio.Future[str] | None = None
        self._manual_code_value: str | None = None

    def compose(self) -> ComposeResult:
        """Compose the OAuth login prompt."""
        with Vertical(id="login-screen"):
            yield Static(f"Login: {self.provider.display_name}", id="login-title")
            yield Static("Complete the browser login, or paste the redirect URL.", id="login-help")
            yield Static("", id="login-oauth-url")
            yield Input(
                placeholder="Paste redirect URL or authorization code",
                id="login-oauth-code",
            )
            yield Static("Enter submits - Escape closes", id="login-footer")

    def on_mount(self) -> None:
        """Focus the manual-code field and start OAuth."""
        self.query_one("#login-oauth-code", Input).focus()
        self.run_worker(self._run_login(), exclusive=True)

    async def _run_login(self) -> None:
        # Lazy import so tests can monkeypatch tau_coding.tui.app.login_openai_codex
        from tau_coding.tui.app import login_openai_codex as _login_openai_codex

        try:
            credential = await _login_openai_codex(
                on_auth=self._show_auth,
                on_prompt=self._prompt_for_code,
                on_manual_code_input=self._manual_code_input,
            )
        except Exception as exc:  # noqa: BLE001 - surface OAuth failures in the TUI
            self.query_one("#login-help", Static).update(f"OAuth failed: {exc}")
            return
        self.dismiss(credential)

    def _show_auth(self, info: OAuthAuthInfo) -> None:
        self.query_one("#login-oauth-url", Static).update(info.url)
        if info.instructions:
            self.query_one("#login-help", Static).update(info.instructions)

    async def _prompt_for_code(self, prompt: OAuthPrompt) -> str:
        self.query_one("#login-help", Static).update(prompt.message)
        return await self._manual_code_input()

    async def _manual_code_input(self) -> str:
        if self._manual_code_value is not None:
            return self._manual_code_value
        loop = asyncio.get_running_loop()
        self._manual_code_future = loop.create_future()
        try:
            return await self._manual_code_future
        finally:
            self._manual_code_future = None

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Resolve the manual OAuth code fallback."""
        if event.input.id != "login-oauth-code":
            return
        event.stop()
        value = event.value.strip()
        if not value:
            return
        self._manual_code_value = value
        if self._manual_code_future is not None and not self._manual_code_future.done():
            self._manual_code_future.set_result(value)

    def action_cancel(self) -> None:
        """Close without saving OAuth credentials."""
        if self._manual_code_future is not None and not self._manual_code_future.done():
            self._manual_code_future.cancel()
        self.dismiss(None)
