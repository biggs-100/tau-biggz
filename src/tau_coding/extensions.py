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
            if event.get("tool_name") == "bash" \
               and "rm -rf" in event.get("input", {}).get("command", ""):
                return {"block": True, "reason": "Blocked by safety check"}
"""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

# ── public API ──────────────────────────────────────────────────────────


class Extension:
    """Base class for Tau extensions.

    Subclass this and use the ``@tool``, ``@command``, and ``@on``
    decorators to register capabilities.
    """

    def on_load(self) -> None:
        """Called after the extension is loaded. Override for init logic."""

    def on_unload(self) -> None:
        """Called when the extension is being unloaded."""


# ── helpers that real users see ─────────────────────────────────────────


def tool(name: str, description: str = "") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that marks a method as a custom tool."""

    def decorator(func: Any) -> Callable[..., Any]:
        sig = inspect.signature(func)
        params = [
            {
                "name": p.name,
                "kind": str(p.annotation) if p.annotation != inspect.Parameter.empty else "string",
            }
            for p in sig.parameters.values()
            if p.name != "self"
        ]
        func.__tau_tool__ = {
            "name": name,
            "description": description or func.__doc__ or "",
            "parameters": params,
            "func": func,
        }
        return cast(Callable[..., Any], func)

    return decorator


def command(
    name: str, *, description: str = ""
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that marks a method as a slash command."""

    def decorator(func: Any) -> Callable[..., Any]:
        func.__tau_command__ = {
            "name": name,
            "description": description or func.__doc__ or "",
            "func": func,
        }
        return cast(Callable[..., Any], func)

    return decorator


def on(event: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that marks a method as an event handler."""

    def decorator(func: Any) -> Callable[..., Any]:
        func.__tau_handler__ = event
        return cast(Callable[..., Any], func)

    return decorator


def ui_widget(zone: str = "status-bar") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that marks a method as a UI widget provider."""

    def decorator(func: Any) -> Callable[..., Any]:
        func.__tau_ui_widget__ = zone
        return cast(Callable[..., Any], func)

    return decorator


# ── runtime ─────────────────────────────────────────────────────────────


class ExtensionError(RuntimeError):
    """Raised when an extension fails to load or run."""


@dataclass
class UIWidget:
    """A UI widget registered by an extension."""

    zone: str
    name: str
    text_fn: Callable[[], str]


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
    enabled: bool = True
    tools: list[ToolRegistration] = field(default_factory=list)
    commands: list[CommandRegistration] = field(default_factory=list)
    handlers: dict[str, list[Callable[..., Any]]] = field(default_factory=dict)
    ui_widgets: tuple[UIWidget, ...] = ()


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
                if (entry.suffix == ".py" and not entry.name.startswith("_")) or (
                    entry.is_dir() and (entry / "__init__.py").exists()
                ):
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
                raise ExtensionError(
                    f"Failed to instantiate {obj.__name__} from {path}: {exc}"
                ) from exc

            tools = self._collect_tools(ext)
            commands = self._collect_commands(ext)
            handlers = self._collect_handlers(ext)
            ui_widgets = self._collect_ui_widgets(ext)

            try:
                ext.on_load()
            except Exception as exc:
                raise ExtensionError(f"{obj.__name__}.on_load() failed: {exc}") from exc

            instances.append(
                ExtensionInstance(
                    name=obj.__name__,
                    path=str(path),
                    instance=ext,
                    enabled=True,
                    tools=tools,
                    commands=commands,
                    handlers=handlers,
                    ui_widgets=ui_widgets,
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

    def _collect_ui_widgets(self, ext: Extension) -> tuple[UIWidget, ...]:
        """Collect UI widgets from an extension instance."""
        widgets: list[UIWidget] = []
        for _name, method in inspect.getmembers(ext, predicate=inspect.ismethod):
            zone = getattr(method, "__tau_ui_widget__", None)
            if zone is None:
                continue
            widgets.append(
                UIWidget(
                    zone=zone,
                    name=method.__name__,
                    text_fn=method,
                )
            )
        return tuple(widgets)

    def _collect_handlers(self, ext: Extension) -> dict[str, list[Callable[..., Any]]]:
        handlers: dict[str, list[Callable[..., Any]]] = {}
        for _name, method in inspect.getmembers(ext, predicate=inspect.ismethod):
            event_name = getattr(method, "__tau_handler__", None)
            if event_name is None:
                continue
            func = method.__func__
            handlers.setdefault(event_name, []).append(func)
        return handlers

    def get_tools(self) -> list[ToolRegistration]:
        """Return all registered tools from all loaded extensions."""
        result: list[ToolRegistration] = []
        for ext in self._extensions.values():
            if ext.enabled:
                result.extend(ext.tools)
        return result

    def get_commands(self) -> list[CommandRegistration]:
        """Return all registered commands from all loaded extensions."""
        result: list[CommandRegistration] = []
        for ext in self._extensions.values():
            if ext.enabled:
                result.extend(ext.commands)
        return result

    def get_ui_widgets(self, zone: str = "status-bar") -> list[UIWidget]:
        """Return all registered UI widgets for a given zone."""
        result: list[UIWidget] = []
        for ext in self._extensions.values():
            if ext.enabled:
                for w in ext.ui_widgets:
                    if w.zone == zone:
                        result.append(w)
        return result

    def dispatch_event(self, event_name: str, event_data: dict[str, Any]) -> list[Any]:
        """Dispatch an event to all enabled extension handlers and return results.

        Handlers are stored as unbound functions, so they are called with
        the extension instance as self and the event data as the argument.
        """
        results: list[Any] = []
        for ext in self._extensions.values():
            if not ext.enabled:
                continue
            handlers = ext.handlers.get(event_name, [])
            for handler in handlers:
                try:
                    result = handler(ext.instance, event_data)
                    results.append(result)
                except Exception:
                    import traceback

                    traceback.print_exc()
        return results

    def enable_extension(self, name: str) -> None:
        """Enable a loaded extension by name.

        Raises KeyError if the extension is not loaded.
        """
        if name not in self._extensions:
            raise KeyError(f"Extension {name!r} not found")
        self._extensions[name].enabled = True

    def disable_extension(self, name: str) -> None:
        """Disable a loaded extension by name.

        Raises KeyError if the extension is not loaded.
        """
        if name not in self._extensions:
            raise KeyError(f"Extension {name!r} not found")
        self._extensions[name].enabled = False

    def is_extension_enabled(self, name: str) -> bool:
        """Return whether a loaded extension is enabled.

        Raises KeyError if the extension is not loaded.
        """
        if name not in self._extensions:
            raise KeyError(f"Extension {name!r} not found")
        return self._extensions[name].enabled

    def unload_all(self) -> None:
        """Unload all extensions."""
        for ext in self._extensions.values():
            try:
                ext.instance.on_unload()
            except Exception:
                import traceback

                traceback.print_exc()
        self._extensions.clear()

    def install_extension(self, path: str) -> ExtensionInstance:
        """Copy a .py file or package dir into the global extension directory and load it.

        Steps:
        1. Resolve the source path.
        2. Determine destination name (filename or dirname).
        3. Copy to the first global search directory, auto-configuring the
           default global path if none is set.
        4. Load the new extension.
        5. Return the loaded ExtensionInstance.

        Raises ExtensionError if the source is not found or the extension
        is already installed.
        """
        src = Path(path).resolve()
        if not src.exists():
            raise ExtensionError(f"Extension source not found: {src}")

        # Auto-configure default global path when none is set
        if not self._global_dirs:
            global_path, _ = default_extension_paths()
            self.add_search_path(global_path)
        ext_dir = self._global_dirs[0]
        ext_dir.mkdir(parents=True, exist_ok=True)

        dest = ext_dir / src.name
        if dest.exists():
            raise ExtensionError(f"Extension already installed at {dest}")

        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=False)
        else:
            shutil.copy2(src, dest)

        try:
            inst = self._load_one(dest)
        except ExtensionError:
            # Clean up the copied file on load failure
            if dest.is_dir():
                shutil.rmtree(dest, ignore_errors=True)
            else:
                dest.unlink(missing_ok=True)
            raise

        self._extensions[inst.name] = inst
        return inst

    def uninstall_extension(self, name: str) -> None:
        """Remove an extension by name and delete its files from disk.

        Steps:
        1. Look up the extension by class name.
        2. Call on_unload().
        3. Remove from the internal registry.
        4. Delete the extension files from the global directory.
        5. Clean up sys.modules cache entries.

        Raises KeyError if the extension is not loaded.
        """
        if name not in self._extensions:
            raise KeyError(f"Extension {name!r} not found")

        ext = self._extensions.pop(name)

        try:
            ext.instance.on_unload()
        except Exception:
            import traceback

            traceback.print_exc()

        path = Path(ext.path)
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

        self._clean_sys_modules(path)

    def reload_extension(self, name: str) -> ExtensionInstance:
        """Hot-reload a single extension without touching its files on disk.

        Steps:
        1. Save the enabled state.
        2. Call on_unload() on the old instance.
        3. Remove from the internal registry.
        4. Clean sys.modules cache.
        5. Re-import and re-register from the same path.
        6. Restore the enabled state.
        7. Return the new ExtensionInstance.

        Raises KeyError if the extension is not loaded.
        """
        if name not in self._extensions:
            raise KeyError(f"Extension {name!r} not found")

        old_ext = self._extensions[name]
        enabled = old_ext.enabled
        path_str = old_ext.path

        try:
            old_ext.instance.on_unload()
        except Exception:
            import traceback

            traceback.print_exc()

        del self._extensions[name]

        path = Path(path_str)
        self._clean_sys_modules(path)

        inst = self._load_one(path)
        inst.enabled = enabled
        self._extensions[name] = inst
        return inst

    @staticmethod
    def _clean_sys_modules(path: Path) -> None:
        """Remove extension-related entries from sys.modules and clear bytecode cache."""
        file_stem = path.stem if path.suffix == ".py" else path.name
        spec_name = f"tau_ext_{file_stem}"
        sys.modules.pop(spec_name, None)
        # Remove any sub-modules if it was a package
        keys_to_remove = [k for k in sys.modules if k.startswith(f"{spec_name}.")]
        for k in keys_to_remove:
            sys.modules.pop(k, None)
        # Clear bytecode cache so reload picks up changes
        importlib.invalidate_caches()
        pycache = path.parent / "__pycache__"
        if pycache.is_dir():
            for cache_file in pycache.iterdir():
                if cache_file.stem.startswith(file_stem):
                    with contextlib.suppress(OSError):
                        cache_file.unlink()


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
