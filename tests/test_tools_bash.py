"""Tests for tau_coding.tools_bash — bash execution helpers.

Covers all 5 functions in the module with deterministic fakes and
platform-specific branches for ``_kill_process_tree``.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys

import pytest

from tau_coding.tools_bash import (
    _communicate_with_cancellation,
    _kill_process_tree,
    _prefixed_shell_command,
    _wait_for_cancel,
    _write_temp_output,
)

# ── Fakes ──────────────────────────────────────────────────────────────────


class FakeCancellationToken:
    """Minimal cancellation token for testing."""

    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def is_cancelled(self) -> bool:
        return self.cancelled


class ControllableProcess:
    """Fake ``asyncio.subprocess.Process`` that lets tests control
    when ``communicate()`` returns and whether ``kill()`` was called."""

    def __init__(self, pid: int = 12345) -> None:
        self.pid = pid
        self.killed = False
        self._can_proceed = asyncio.Event()
        self.communicate_result: tuple[bytes, bytes | None] = (
            b"stdout output\n",
            b"stderr output\n",
        )

    async def communicate(self) -> tuple[bytes, bytes | None]:
        await self._can_proceed.wait()
        return self.communicate_result

    def kill(self) -> None:
        self.killed = True
        self._can_proceed.set()


class CancellingProcess:
    """Fake process whose ``communicate()`` raises ``CancelledError``
    after ``kill()`` is called — exercises the inner except clause
    in ``_communicate_with_cancellation``."""

    def __init__(self, pid: int = 12345) -> None:
        self.pid = pid
        self.killed = False
        self._can_proceed = asyncio.Event()

    async def communicate(self) -> tuple[bytes, bytes | None]:
        await self._can_proceed.wait()
        raise asyncio.CancelledError()

    def kill(self) -> None:
        self.killed = True
        self._can_proceed.set()


# ── _prefixed_shell_command ───────────────────────────────────────────────


class TestPrefixedShellCommand:
    """``_prefixed_shell_command(command, prefix)`` — prepends prefix to
    the command string when prefix is not None."""

    def test_none_prefix_returns_command_unchanged(self) -> None:
        assert _prefixed_shell_command("echo hi", None) == "echo hi"

    def test_string_prefix_prepends_with_newline(self) -> None:
        result = _prefixed_shell_command("echo hi", "source ~/.zshrc")
        assert result == "source ~/.zshrc\necho hi"

    def test_empty_string_prefix_emits_leading_newline(self) -> None:
        result = _prefixed_shell_command("echo hi", "")
        assert result == "\necho hi"


# ── _write_temp_output ────────────────────────────────────────────────────


class TestWriteTempOutput:
    """``_write_temp_output(output)`` — writes to a temp file and returns
    its path."""

    def test_basic_write(self) -> None:
        content = "hello world\nline 2\n"
        path = _write_temp_output(content)
        try:
            assert os.path.exists(path), "Temp file should exist on disk"
            assert os.path.basename(path).startswith("tau-bash-")
            assert os.path.basename(path).endswith(".log")
            with open(path, encoding="utf-8") as f:
                assert f.read() == content
        finally:
            os.unlink(path)

    def test_empty_content(self) -> None:
        path = _write_temp_output("")
        try:
            assert os.path.exists(path)
            with open(path, encoding="utf-8") as f:
                assert f.read() == ""
        finally:
            os.unlink(path)


# ── _wait_for_cancel ──────────────────────────────────────────────────────


class TestWaitForCancel:
    """``_wait_for_cancel(signal)`` — polls a cancellation token and
    returns when the token signals cancellation."""

    @pytest.mark.anyio
    async def test_already_cancelled_returns_immediately(self) -> None:
        token = FakeCancellationToken()
        token.cancel()
        await _wait_for_cancel(token)  # Should return without blocking

    @pytest.mark.anyio
    async def test_eventually_cancelled(self) -> None:
        token = FakeCancellationToken()

        async def cancel_soon() -> None:
            await asyncio.sleep(0.01)
            token.cancel()

        cancel_task = asyncio.create_task(cancel_soon())
        await asyncio.wait_for(_wait_for_cancel(token), timeout=5)
        cancel_task.cancel()

    @pytest.mark.anyio
    async def test_never_fires_times_out(self) -> None:
        token = FakeCancellationToken()
        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            await asyncio.wait_for(_wait_for_cancel(token), timeout=0.05)


# ── _kill_process_tree ────────────────────────────────────────────────────


class TestKillProcessTree:
    """``_kill_process_tree(process)`` — platform-specific process group
    kill (POSIX uses ``os.killpg``, Windows uses ``process.kill``)."""

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-specific test")
    def test_posix_uses_killpg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(os, "name", "posix")
        calls: list[tuple[int, int]] = []

        def fake_killpg(pid: int, sig: int) -> None:
            calls.append((pid, sig))

        monkeypatch.setattr(os, "killpg", fake_killpg)
        process = ControllableProcess(pid=42)
        _kill_process_tree(process)
        assert calls == [(42, signal.SIGKILL)]

    def test_windows_uses_kill(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(os, "name", "nt")
        process = ControllableProcess(pid=42)
        _kill_process_tree(process)
        assert process.killed is True

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-specific test")
    def test_posix_process_lookup_error_handled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(os, "name", "posix")

        def raise_error(*args: object) -> None:
            raise ProcessLookupError()

        monkeypatch.setattr(os, "killpg", raise_error)
        process = ControllableProcess(pid=42)
        _kill_process_tree(process)  # Should not raise

    def test_windows_process_lookup_error_handled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(os, "name", "nt")
        process = ControllableProcess(pid=42)

        def raise_error() -> None:
            raise ProcessLookupError()

        monkeypatch.setattr(process, "kill", raise_error)
        _kill_process_tree(process)  # Should not raise


# ── _communicate_with_cancellation ────────────────────────────────────────


class TestCommunicateWithCancellation:
    """``_communicate_with_cancellation(process, *, timeout, signal)`` —
    communicates with a subprocess while supporting cancellation and
    timeout."""

    @pytest.mark.anyio
    async def test_normal_no_signal_no_timeout(self) -> None:
        process = ControllableProcess()
        process._can_proceed.set()

        out, err, timed_out, cancelled = await _communicate_with_cancellation(
            process,
            timeout=None,
            signal=None,
        )

        assert out == b"stdout output\n"
        assert err == b"stderr output\n"
        assert timed_out is False
        assert cancelled is False
        assert process.killed is False

    @pytest.mark.anyio
    async def test_signal_provided_but_communicate_wins(self) -> None:
        """When a signal token is supplied but communicate finishes first,
        the function returns a normal result without killing."""
        process = ControllableProcess()
        process._can_proceed.set()
        token = FakeCancellationToken()

        out, err, timed_out, cancelled = await _communicate_with_cancellation(
            process,
            timeout=None,
            signal=token,
        )

        assert out == b"stdout output\n"
        assert err == b"stderr output\n"
        assert timed_out is False
        assert cancelled is False
        assert process.killed is False

    @pytest.mark.anyio
    async def test_timeout_kills_process_and_returns_buffered(self) -> None:
        """When the timeout fires before communicate finishes, the process
        is killed and the remaining buffered output is returned."""
        process = ControllableProcess()

        out, err, timed_out, cancelled = await _communicate_with_cancellation(
            process,
            timeout=0.01,
            signal=None,
        )

        assert out == b"stdout output\n"
        assert err == b"stderr output\n"
        assert timed_out is True
        assert cancelled is False
        assert process.killed is True

    @pytest.mark.anyio
    async def test_timeout_with_signal_timeout_fires_first(
        self,
    ) -> None:
        """When both timeout and signal are provided and the timeout
        expires first, the result should reflect a timeout."""
        process = ControllableProcess()
        token = FakeCancellationToken()

        out, err, timed_out, cancelled = await _communicate_with_cancellation(
            process,
            timeout=0.01,
            signal=token,
        )

        assert timed_out is True
        assert cancelled is False
        assert process.killed is True
        # Output should still be available from the buffered communicate
        assert out == b"stdout output\n"
        assert err == b"stderr output\n"

    @pytest.mark.anyio
    async def test_signal_cancel_kills_process_and_returns_buffered(
        self,
    ) -> None:
        """When the cancellation token fires, the process is killed and
        buffered output is returned with cancelled=True."""
        process = ControllableProcess()
        token = FakeCancellationToken()

        async def cancel_soon() -> None:
            await asyncio.sleep(0.01)
            token.cancel()

        cancel_task = asyncio.create_task(cancel_soon())
        out, err, timed_out, cancelled = await _communicate_with_cancellation(
            process,
            timeout=None,
            signal=token,
        )

        assert out == b"stdout output\n"
        assert err == b"stderr output\n"
        assert timed_out is False
        assert cancelled is True
        assert process.killed is True
        cancel_task.cancel()

    @pytest.mark.anyio
    async def test_inner_communicate_raises_cancelled_error(self) -> None:
        """When ``await communicate`` raises ``CancelledError`` after the
        process is killed, the inner except handler returns empty bytes."""
        process = CancellingProcess()
        token = FakeCancellationToken()

        async def cancel_soon() -> None:
            await asyncio.sleep(0.01)
            token.cancel()

        cancel_task = asyncio.create_task(cancel_soon())
        out, err, timed_out, cancelled = await _communicate_with_cancellation(
            process,
            timeout=None,
            signal=token,
        )

        assert out == b""
        assert err is None
        assert timed_out is False
        assert cancelled is True
        assert process.killed is True
        cancel_task.cancel()

    @pytest.mark.anyio
    async def test_outer_cancelled_error_kills_process(self) -> None:
        """When the task running communicate gets externally cancelled,
        the process is still killed and CancelledError propagates."""
        process = ControllableProcess()

        task = asyncio.create_task(
            _communicate_with_cancellation(process, timeout=None, signal=None),
        )
        await asyncio.sleep(0.02)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert process.killed is True
