"""Example Tau extension — greeting tool and /hi command.

Provides a ``@tool("hello")`` that greets the user and a
``@command("hi")`` slash command.
"""

from tau_coding.extensions import Extension, tool, command


class GreetingExtension(Extension):
    @tool("hello", "Greet the user")
    def hello(self, name: str = "world") -> str:
        """Return a friendly greeting."""
        return f"Hello, {name}!"

    @command("hi", description="Say hi")
    def hi_cmd(self, args: str) -> str | None:
        return f"Hi {args or 'there'}!"
