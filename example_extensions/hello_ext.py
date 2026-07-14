"""Example Tau extension — greet tool and /hello command."""

from tau_coding.extensions import Extension, command, on, tool


class HelloExtension(Extension):
    @tool("greet", "Greet someone by name")
    def greet(self, name: str = "world") -> str:
        """Return a friendly greeting."""
        return f"Hello, {name}!"

    @command("hello", description="Say hello")
    def hello_cmd(self, args: str) -> str | None:
        return f"Hello {args or 'world'}!"

    @on("session_start")
    def on_session_start(self, event: dict) -> None:
        print("  [HelloExtension] Session started!")

    @on("tool_call")
    def on_tool_call(self, event: dict) -> dict | None:
        if event.get("tool_name") == "bash":
            cmd = event.get("input", {}).get("command", "")
            if "rm -rf" in cmd or "sudo" in cmd:
                return {"block": True, "reason": "Blocked by HelloExtension"}
        return None
