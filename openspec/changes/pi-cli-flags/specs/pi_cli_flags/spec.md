# Pi-CLI Flags Specification

## Purpose

Migrate tau-biggz CLI flags to match Pi's flag naming conventions while providing clear migration hints for deprecated flags.

## Requirements

### Requirement: Flag mapping

The system MUST replace the following old flags with new Pi-compatible flags:

| Old | New | Migration |
|---|---|---|
| `-p "text"` / `--prompt "text"` | `--print` (bool) + positional prompt | `--prompt` hidden → error con hint |
| `--resume <id>` | `--session <id>` | `--resume` hidden → error con hint |
| `-o json` / `--output json` | `--mode json` | `--output`/`-o` hidden → error con hint |
| (new) | `--export <id>` | Additive |
| (new) | `-v` for `--version` | Additive |
| (new) | piped stdin merge | Additive |

#### Scenario: `--print` replaces `--prompt`/`-p` for print mode

- GIVEN the user runs `tau --prompt "hello"`
- THEN the system MUST print an error: `"--prompt was renamed to --print. Use --print <prompt> instead."`
- AND exit with a non-zero code

- GIVEN the user runs `tau --print hello`
- WHEN the model provider responds
- THEN the system MUST run in print mode with prompt `"hello"`

#### Scenario: `--session` replaces `--resume`

- GIVEN the user runs `tau --resume session-1`
- THEN the system MUST print an error: `"--resume was renamed to --session. Use --session <id> instead."`
- AND exit with a non-zero code

- GIVEN the user runs `tau --session session-1`
- THEN the system MUST resume session `session-1` in TUI mode

#### Scenario: `--mode` replaces `--output`/`-o`

- GIVEN the user runs `tau --output json`
- THEN the system MUST print an error with a hint to use `--mode` instead

- GIVEN the user runs `tau --print hello --mode json`
- THEN the system MUST run in print mode with JSON output

#### Scenario: `--mode` alone triggers print mode

- GIVEN the user runs `tau --mode json hello`
- THEN the system MUST run in print mode with prompt `"hello"` and JSON output
- WITHOUT requiring the `--print` flag

#### Scenario: `--export` flag exports a session

- GIVEN the user runs `tau --export session-1`
- THEN the system MUST export session `session-1` to the default output path

#### Scenario: `-v` short flag for version

- GIVEN the user runs `tau -v`
- THEN the system MUST print the version and exit
- Identical behavior to `tau --version`

### Requirement: Piped stdin merge

The system MUST read piped input from stdin when stdin is not a TTY, and merge it with positional prompt arguments for print mode.

#### Scenario: Piped input becomes the print-mode prompt

- GIVEN the user pipes text into `tau --print` with no positional arguments
- WHEN stdin is not a TTY
- THEN the system MUST read stdin and use it as the print-mode prompt

#### Scenario: Piped input merges with positional prompt

- GIVEN the user pipes text into `tau --print` with additional positional arguments
- WHEN stdin is not a TTY
- THEN the system MUST concatenate stdin with the positional arguments, separated by a newline

### Files

| File | Action |
|---|---|
| `src/tau_coding/cli.py` | MODIFY — flag migration, new flags, extracted functions |
| `tests/test_cli.py` | MODIFY — update old flag usage, add migration tests |
