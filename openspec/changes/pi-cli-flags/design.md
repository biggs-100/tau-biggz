# Design: Pi-CLI Flags Migration

**Change**: `pi-cli-flags`
**Phase**: design
**Date**: 2026-07-23
**Status**: Draft

---

## 1. Approach

### Deprecated flag pattern

Each deprecated old flag is added as a hidden Typer option with a `None` default and guarded at the top of `main()`:

```python
old_flag: Annotated[
    str | None,
    typer.Option("--old-flag", hidden=True),
] = None,

# Guard
if old_flag is not None:
    raise typer.BadParameter(
        "--old-flag was renamed to --new-flag. Use --new-flag <value> instead."
    )
```

### Print mode trigger

`print_requested = print_mode or mode is not None` — `--mode` alone triggers print mode without requiring `--print`. All existing `prompt_option is None` guards become `not print_requested`.

### Prompt source

Print-mode prompt comes from `_merge_stdin_prompt(prompt_args)`, which reads piped stdin when available, otherwise uses positional args.

### Export extraction

`_run_export_cli(session_ref, extra_args)` handles both `tau export` (subcommand) and `tau --export <id>` (flag) paths.

---

## 2. Function Changes

### `main()` — callback signature and body

**Parameters to add:**
- `print_mode: bool` with `--print`/`-p` (new print-mode toggle)
- `session: str | None` with `--session` (replaces `--resume`)
- `mode: PrintOutputMode | None` with `--mode` (replaces `--output`/`-o`)
- `export: str | None` with `--export` (additive)

**Parameters to hide (old flags):**
- `prompt_option` → `--prompt`, hidden
- `resume` → `--resume`, hidden
- `output` → `--output`/`-o`, hidden

**Parameter to extend:**
- `version` → add `-v` alias

**Body logic:**
1. Guard old flags early → raise `typer.BadParameter` with migration hint
2. `print_requested = print_mode or mode is not None`
3. All `prompt_option is None` guards → `not print_requested`
4. Print-mode prompt: `_merge_stdin_prompt(prompt_args)`
5. Export check: `if export is not None → _run_export_cli(export, prompt_args or [])`

### `_merge_stdin_prompt()` — new function

```python
def _merge_stdin_prompt(prompt_args: list[str] | None) -> str | None:
    """Read stdin when piped, merge with positional args, return prompt or None."""
    if sys.stdin.isatty():
        if prompt_args:
            return " ".join(prompt_args)
        return None
    stdin_text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    if prompt_args:
        return stdin_text + "\n" + " ".join(prompt_args)
    return stdin_text or None
```

### `_run_export_cli()` — new extracted function

```python
def _run_export_cli(session_ref: str, extra_args: list[str]) -> None:
    """Run session export from a session ref + parsed extra args."""
    output_path, export_format = _parse_export_extra_args(extra_args)
    exported_path = anyio.run(export_session_command, session_ref, output_path, export_format)
    typer.echo(f"Exported session to {exported_path}")
    raise typer.Exit()
```

### `_parse_export_extra_args()` — extracted from `_parse_export_cli_args`

Parses `--format` and output path from args after the session ref.

---

## 3. File Changes

| File | Action |
|---|---|
| `src/tau_coding/cli.py` | Modify `main()` signature, add guard logic, add new functions |
| `tests/test_cli.py` | Update old flag tests, add migration and new flag tests |
