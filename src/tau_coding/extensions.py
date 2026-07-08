"""Tau Extension System — register custom tools, commands, and event handlers.

Extensions are Python files placed in ``~/.tau/extensions/`` or
``.tau/extensions/``. Each file exports a subclass of ``Extension``::

    from tau_coding.extensions import Extension, tool, command, on


    class MyExt(Extension):
        @tool("greet", "Greet someone by name")
        def greet(self, name: str) -> str:
            return f"Hello, {name}!"

        @command("hello", description="Say hello")
        def hello(self, args: str) -> str | None:
            return f"Hello {args or 'world'}!"

        @on("tool_call")
        def block_rm(self, event) -> dict | None:
            if event.get("tool_name") == "bash" \\
               and "rm -rf" in event.get("input", {}).get("command", ""):
                return {"block": True, "reason": "Blocked by safety check"}
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


# ── public API ──────────────────────────────────────────────────────────


class Extension:
    """Base class for Tau extensions.

    Subclass this and use the ``@tool``, ``@command``, and ``@on``
    decorators to register capabilities.
    """

    # Populated by the decorators at class definition time.
    _tools: list[dict[str, Any]] = []
    _commands: list[dict[str, Any]] = []
    _handlers: dict[str, list[Callable[..., Any]]] = {}

    def on_load(self) -> None:
        """Called after the extension is loaded. Override for init logic."""

    def on_unload(self) -> None:
        """Called when the extension is being unloaded."""


# ── helpers that real users see ─────────────────────────────────────────


def tool(name: str, description: str = "") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that marks a method as a custom tool."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(func)
        params = [
            {"name": p.name, "kind": str(p.annotation) if p.annotation != inspect.Parameter.empty else "string"}
            for p in sig.parameters.values()
            if p.name != "self"
        ]
        func.__tau_tool__ = {
            "name": name,
            "description": description or func.__doc__ or "",
            "parameters": params,
            "func": func,
        }
        return func

    return decorator


def command(name: str, *, description: str = "") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that marks a method as a slash command."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func.__tau_command__ = {
            "name": name,
            "description": description or func.__doc__ or "",
            "func": func,
        }
        return func

    return decorator


def on(event: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that marks a method as an event handler."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func.__tau_handler__ = event
        return func

    return decorator


# ── runtime ─────────────────────────────────────────────────────────────


class ExtensionError(RuntimeError):
    """Raised when an extension fails to load or run."""


@dataclass
class ToolRegistration:
    """A tool registered by an extension."""

    name: str
    description: str
    parameters: list[dict[str, str]]
    executor: Callable[..., Any]


@dataclass
class CommandRegistration:
    """A slash command registered by an extension."""

    name: str
    description: str
    handler: Callable[..., Any]


# Global singleton registry
_default_registry: ExtensionRegistry | None = None


def get_default_registry() -> ExtensionRegistry:
    """Return or create the global extension registry singleton."""
    global _default_registry
    if _default_registry is None:
        _default_registry = create_default_registry()
        _default_registry.load_all()
    return _default_registry


@dataclass
class ExtensionInstance:
    """A loaded extension instance with its registrations."""

    name: str
    path: str
    instance: Extension
    tools: list[ToolRegistration] = field(default_factory=list)
    commands: list[CommandRegistration] = field(default_factory=list)
    handlers: dict[str, list[Callable[..., Any]]] = field(default_factory=dict)


class ExtensionRegistry:
    """Manages loading, listing, and unloading extensions."""

    def __init__(self) -> None:
        self._extensions: dict[str, ExtensionInstance] = {}
        self._global_dirs: list[Path] = []
        self._project_dirs: list[Path] = []

    def add_search_path(self, path: str | Path, *, project_local: bool = False) -> None:
        """Add a directory to scan for extensions."""
        p = Path(path).resolve()
        if project_local:
            self._project_dirs.append(p)
        else:
            self._global_dirs.append(p)

    def discover(self) -> list[Path]:
        """Return all candidate extension file paths from search directories."""
        candidates: list[Path] = []
        for d in (*self._global_dirs, *self._project_dirs):
            if not d.is_dir():
                continue
            for entry in sorted(d.iterdir()):
                if entry.suffix == ".py" and not entry.name.startswith("_"):
                    candidates.append(entry)
                elif entry.is_dir() and (entry / "__init__.py").exists():
                    candidates.append(entry)
        return candidates

    def load_all(self) -> list[ExtensionInstance]:
        """Discover and load all extensions from search paths."""
        instances: list[ExtensionInstance] = []
        for path in self.discover():
            try:
                inst = self._load_one(path)
                instances.append(inst)
                self._extensions[inst.name] = inst
            except ExtensionError:
                import traceback
                traceback.print_exc()
        return instances

    def _load_one(self, path: Path) -> ExtensionInstance:
        """Load a single extension file and return its registrations."""
        name = path.stem if path.suffix == ".py" else path.name
        spec_name = f"tau_ext_{name}"

        if path.is_dir():
            spec = importlib.util.spec_from_file_location(spec_name, path / "__init__.py")
        else:
            spec = importlib.util.spec_from_file_location(spec_name, path)
        if spec is None or spec.loader is None:
            raise ExtensionError(f"Cannot load extension: {path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            raise ExtensionError(f"Failed to execute extension {path}: {exc}") from exc

        # Find Extension subclasses
        instances = []
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if obj is Extension or not issubclass(obj, Extension):
                continue
            try:
                ext = obj()
            except Exception as exc:
                raise ExtensionError(f"Failed to instantiate {obj.__name__} from {path}: {exc}") from exc

            tools = self._collect_tools(ext)
            commands = self._collect_commands(ext)
            handlers = self._collect_handlers(ext)

            try:
                ext.on_load()
            except Exception as exc:
                raise ExtensionError(f"{obj.__name__}.on_load() failed: {exc}") from exc

            instances.append(
                ExtensionInstance(
                    name=obj.__name__,
                    path=str(path),
                    instance=ext,
                    tools=tools,
                    commands=commands,
                    handlers=handlers,
                )
            )

        if not instances:
            raise ExtensionError(f"No Extension subclass found in {path}")

        return instances[0]

    def _collect_tools(self, ext: Extension) -> list[ToolRegistration]:
        tools: list[ToolRegistration] = []
        for _name, method in inspect.getmembers(ext, predicate=inspect.ismethod):
            meta = getattr(method, "__tau_tool__", None)
            if meta is None:
                continue
            tools.append(
                ToolRegistration(
                    name=meta["name"],
                    description=meta["description"],
                    parameters=meta["parameters"],
                    executor=meta["func"],
                )
            )
        return tools

    def _collect_commands(self, ext: Extension) -> list[CommandRegistration]:
        cmds: list[CommandRegistration] = []
        for _name, method in inspect.getmembers(ext, predicate=inspect.ismethod):
            meta = getattr(method, "__tau_command__", None)
            if meta is None:
                continue
            cmds.append(
                CommandRegistration(
                    name=meta["name"],
                    description=meta["description"],
                    handler=meta["func"],
                )
            )
        return cmds

    def _collect_handlers(self, ext: Extension) -> dict[str, list[Callable[..., Any]]]:
        handlers: dict[str, list[Callable[..., Any]]] = {}
        for _name, method in inspect.getmembers(ext, predicate=inspect.ismethod):
            event_name = getattr(method, "__tau_handler__", None)
            if event_name is None:
                continue
            handlers.setdefault(event_name, []).append(method)
        return handlers

    def get_tools(self) -> list[ToolRegistration]:
        """Return all registered tools from all loaded extensions."""
        result: list[ToolRegistration] = []
        for ext in self._extensions.values():
            result.extend(ext.tools)
        return result

    def get_commands(self) -> list[CommandRegistration]:
        """Return all registered commands from all loaded extensions."""
        result: list[CommandRegistration] = []
        for ext in self._extensions.values():
            result.extend(ext.commands)
        return result

    def dispatch_event(self, event_name: str, event_data: dict[str, Any]) -> list[Any]:
        """Dispatch an event to all extension handlers and return results."""
        results: list[Any] = []
        for ext in self._extensions.values():
            handlers = ext.handlers.get(event_name, [])
            for handler in handlers:
                try:
                    result = handler(ext.instance, event_data)
                    results.append(result)
                except Exception:
                    import traceback
                    traceback.print_exc()
        return results

    def unload_all(self) -> None:
        """Unload all extensions."""
        for ext in self._extensions.values():
            try:
                ext.instance.on_unload()
            except Exception:
                import traceback
                traceback.print_exc()
        self._extensions.clear()


# ── default paths ───────────────────────────────────────────────────────


def default_extension_paths() -> tuple[Path, Path]:
    """Return (global_path, project_path) for extension discovery."""
    home_ext = Path.home() / ".tau" / "extensions"
    project_ext = Path.cwd() / ".tau" / "extensions"
    return home_ext, project_ext


def create_default_registry() -> ExtensionRegistry:
    """Create an ExtensionRegistry with default search paths."""
    registry = ExtensionRegistry()
    global_path, project_path = default_extension_paths()
    registry.add_search_path(global_path)
    registry.add_search_path(project_path, project_local=True)
    return registry
