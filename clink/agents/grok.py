"""Grok Build CLI agent hooks."""

from __future__ import annotations

from clink.models import ResolvedCLIRole

from .claude import ClaudeAgent


class GrokAgent(ClaudeAgent):
    """Grok Build CLI agent.

    Reuses the Claude agent's run loop (prompt as final argument, no stdin)
    but adapts the flags: role prompts are appended to the system prompt via
    ``--rules`` and the trailing ``--single`` flag turns the final positional
    prompt into a headless single-turn request instead of launching the TUI.
    """

    def _build_command(self, *, role: ResolvedCLIRole, system_prompt: str | None) -> list[str]:
        command = list(self.client.executable)
        command.extend(self.client.internal_args)
        command.extend(self.client.config_args)

        if system_prompt and "--rules" not in self.client.config_args:
            command.extend(["--rules", system_prompt])

        command.extend(role.role_args)
        # ClaudeAgent.run() appends the prompt as the final argument; --single
        # makes it the headless prompt value rather than an interactive TUI arg.
        command.append("--single")
        return command
