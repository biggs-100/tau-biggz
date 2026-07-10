"""Tests for extension UI widget registration."""

from __future__ import annotations

from tau_coding.extensions import Extension, UIWidget, ui_widget


def test_ui_widget_decorator_sets_zone() -> None:
    """The @ui_widget decorator should set __tau_ui_widget__ on the method."""

    class TestExt(Extension):
        @ui_widget("status-bar")
        def my_widget(self) -> str:
            return "hello"

    inst = TestExt()
    assert hasattr(inst.my_widget, "__tau_ui_widget__")
    assert getattr(inst.my_widget, "__tau_ui_widget__") == "status-bar"


def test_ui_widget_default_zone() -> None:
    """@ui_widget with no args should default to 'status-bar'."""

    class TestExt(Extension):
        @ui_widget()
        def my_widget(self) -> str:
            return "hello"

    inst = TestExt()
    assert getattr(inst.my_widget, "__tau_ui_widget__") == "status-bar"


def test_ui_widget_multiple_widgets() -> None:
    """An extension can register multiple UI widgets."""

    class TestExt(Extension):
        @ui_widget("status-bar")
        def widget_a(self) -> str:
            return "A"

        @ui_widget("status-bar")
        def widget_b(self) -> str:
            return "B"

    inst = TestExt()
    assert getattr(inst.widget_a, "__tau_ui_widget__") == "status-bar"
    assert getattr(inst.widget_b, "__tau_ui_widget__") == "status-bar"


def test_ui_widget_different_zones() -> None:
    """Widgets can be registered for different zones."""

    class TestExt(Extension):
        @ui_widget("status-bar")
        def widget_a(self) -> str:
            return "A"

        @ui_widget("sidebar")
        def widget_b(self) -> str:
            return "B"

    inst = TestExt()
    assert getattr(inst.widget_a, "__tau_ui_widget__") == "status-bar"
    assert getattr(inst.widget_b, "__tau_ui_widget__") == "sidebar"


def test_ui_widget_method_returns_string() -> None:
    """The decorated method should return a string when called."""

    class TestExt(Extension):
        @ui_widget("status-bar")
        def my_widget(self) -> str:
            return "⚡ Active"

    inst = TestExt()
    assert inst.my_widget() == "⚡ Active"


def test_ui_widget_callable_is_used_in_uiwidget_dataclass() -> None:
    """The UIWidget dataclass should store and invoke the callable."""

    def my_text_fn() -> str:
        return "test value"

    widget = UIWidget(zone="status-bar", name="test.widget", text_fn=my_text_fn)
    assert widget.zone == "status-bar"
    assert widget.name == "test.widget"
    assert widget.text_fn() == "test value"


def test_ui_widget_empty_returns_empty_str() -> None:
    """A widget can return an empty string."""

    class TestExt(Extension):
        @ui_widget("status-bar")
        def empty(self) -> str:
            return ""

    inst = TestExt()
    assert inst.empty() == ""
