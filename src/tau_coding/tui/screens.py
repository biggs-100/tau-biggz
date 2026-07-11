"""Modal screens and pickers for Tau TUI."""

from __future__ import annotations

from textual.binding import Binding

from tau_coding.tui._screens_login import (
    CustomProviderLoginResult,
    CustomProviderLoginScreen,
    LoginMethodListView,
    LoginMethodPickerScreen,
    LoginProviderPickerScreen,
    LoginScreen,
    OAuthLoginScreen,
    _login_provider_label,
)
from tau_coding.tui._screens_output import CommandOutputScreen, CommandOutputScroll

# Import everything from the focused screen modules.
# Each module is self-contained with no circular import to screens.py.
from tau_coding.tui._screens_session import (
    BranchSummaryInstructionsScreen,
    SessionPickerScreen,
    TreePickerResult,
    TreePickerScreen,
    _active_tree_choice_index,
    _named_session_title,
    _session_picker_label,
    _session_updated_at_label,
    _tree_choice_index,
    _tree_picker_label,
)
from tau_coding.tui._screens_settings import (
    ModelPickerScreen,
    ModelPickerSearchInput,
    ThemePickerScreen,
    _filter_model_choices,
    _model_picker_label,
    _theme_picker_label,
)

__all__ = [
    "BindingEntry",
    "BranchSummaryInstructionsScreen",
    "CommandOutputScreen",
    "CommandOutputScroll",
    "CustomProviderLoginResult",
    "CustomProviderLoginScreen",
    "LoginMethodListView",
    "LoginMethodPickerScreen",
    "LoginProviderPickerScreen",
    "LoginScreen",
    "ModelPickerScreen",
    "ModelPickerSearchInput",
    "OAuthLoginScreen",
    "SessionPickerScreen",
    "ThemePickerScreen",
    "TreePickerResult",
    "TreePickerScreen",
    "_active_tree_choice_index",
    "_filter_model_choices",
    "_login_provider_label",
    "_model_picker_label",
    "_named_session_title",
    "_session_picker_label",
    "_session_updated_at_label",
    "_theme_picker_label",
    "_tree_choice_index",
    "_tree_picker_label",
]

type BindingEntry = Binding | tuple[str, str] | tuple[str, str, str]


# ── Re-exported symbols ──────────────────────────────────────────────────────
# All public and private symbols previously exported from this module remain
# accessible under the same import paths.
#
# Classes:
#   BranchSummaryInstructionsScreen  (from _screens_session)
#   CommandOutputScreen              (from _screens_output)
#   CommandOutputScroll              (from _screens_output)
#   CustomProviderLoginResult        (from _screens_login)
#   CustomProviderLoginScreen        (from _screens_login)
#   LoginMethodListView              (from _screens_login)
#   LoginMethodPickerScreen          (from _screens_login)
#   LoginProviderPickerScreen        (from _screens_login)
#   LoginScreen                      (from _screens_login)
#   ModelPickerScreen                (from _screens_settings)
#   ModelPickerSearchInput           (from _screens_settings)
#   OAuthLoginScreen                 (from _screens_login)
#   SessionPickerScreen              (from _screens_session)
#   ThemePickerScreen                (from _screens_settings)
#   TreePickerResult                 (from _screens_session)
#   TreePickerScreen                 (from _screens_session)
#
# Helpers:
#   _active_tree_choice_index        (from _screens_session)
#   _filter_model_choices            (from _screens_settings)
#   _login_provider_label            (from _screens_login)
#   _model_picker_label              (from _screens_settings)
#   _named_session_title             (from _screens_session)
#   _session_picker_label            (from _screens_session)
#   _session_updated_at_label        (from _screens_session)
#   _theme_picker_label              (from _screens_settings)
#   _tree_choice_index               (from _screens_session)
#   _tree_picker_label               (from _screens_session)
