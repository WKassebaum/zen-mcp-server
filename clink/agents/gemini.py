"""Gemini-specific CLI agent hooks."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from clink.constants import DEFAULT_STREAM_LIMIT
from clink.models import ResolvedCLIClient, ResolvedCLIRole
from clink.parsers.base import ParsedCLIResponse, ParserError

from .base import AgentOutput, BaseCLIAgent, CLIAgentError


class GeminiAgent(BaseCLIAgent):
    """Gemini-specific behaviour."""

    def __init__(self, client: ResolvedCLIClient):
        super().__init__(client)

    def _build_command(self, *, role: ResolvedCLIRole, system_prompt: str | None) -> list[str]:
        """Build command for gemini CLI - prompt will be appended during execution."""
        command = list(self.client.executable)
        command.extend(self.client.internal_args)
        command.extend(self.client.config_args)
        command.extend(role.role_args)
        # Note: prompt is appended in run() method as positional argument
        return command

    async def run(
        self,
        *,
        role: ResolvedCLIRole,
        prompt: str,
        system_prompt: str | None = None,
        files: Sequence[str],
        images: Sequence[str],
    ) -> AgentOutput:
        """Run gemini CLI with prompt as positional argument (not stdin)."""
        _ = (files, images)  # Already embedded in prompt

        command = self._build_command(role=role, system_prompt=system_prompt)
        # Append prompt as positional argument for gemini
        command.append(prompt)
        env = self._build_environment()

        # Resolve executable
        executable_name = command[0]
        resolved_executable = shutil.which(executable_name)
        if resolved_executable is None:
            raise CLIAgentError(
                f"Executable '{executable_name}' not found in PATH for CLI '{self.client.name}'. "
                f"Ensure the command is installed and accessible."
            )
        command[0] = resolved_executable
        sanitized_command = list(command)

        cwd = str(self.client.working_dir) if self.client.working_dir else None
        limit = DEFAULT_STREAM_LIMIT

        self._logger.debug("Executing CLI command: %s", " ".join(shlex.quote(arg) for arg in sanitized_command))
        if cwd:
            self._logger.debug("Working directory: %s", cwd)

        start_time = time.monotonic()

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL,  # No stdin needed
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                limit=limit,
                env=env,
            )
        except FileNotFoundError as exc:
            raise CLIAgentError(f"Executable not found for CLI '{self.client.name}': {exc}") from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),  # No stdin input
                timeout=self.client.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise CLIAgentError(
                f"CLI '{self.client.name}' timed out after {self.client.timeout_seconds} seconds",
                returncode=None,
            ) from exc

        duration = time.monotonic() - start_time
        return_code = process.returncode
        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")

        if return_code != 0:
            recovered = self._recover_from_error(
                returncode=return_code,
                stdout=stdout_text,
                stderr=stderr_text,
                sanitized_command=sanitized_command,
                duration_seconds=duration,
                output_file_content=None,
            )
            if recovered is not None:
                return recovered

            raise CLIAgentError(
                f"CLI '{self.client.name}' exited with status {return_code}",
                returncode=return_code,
                stdout=stdout_text,
                stderr=stderr_text,
            )

        try:
            parsed = self._parser.parse(stdout_text, stderr_text)
        except ParserError as exc:
            raise CLIAgentError(
                f"Failed to parse output from CLI '{self.client.name}': {exc}",
                returncode=return_code,
                stdout=stdout_text,
                stderr=stderr_text,
            ) from exc

        return AgentOutput(
            parsed=parsed,
            sanitized_command=sanitized_command,
            returncode=return_code,
            stdout=stdout_text,
            stderr=stderr_text,
            duration_seconds=duration,
            parser_name=self._parser.name,
            output_file_content=None,
        )

    def _recover_from_error(
        self,
        *,
        returncode: int,
        stdout: str,
        stderr: str,
        sanitized_command: list[str],
        duration_seconds: float,
        output_file_content: str | None,
    ) -> AgentOutput | None:
        combined = "\n".join(part for part in (stderr, stdout) if part)
        if not combined:
            return None

        brace_index = combined.find("{")
        if brace_index == -1:
            return None

        json_candidate = combined[brace_index:]
        try:
            payload: dict[str, Any] = json.loads(json_candidate)
        except json.JSONDecodeError:
            return None

        error_block = payload.get("error")
        if not isinstance(error_block, dict):
            return None

        code = error_block.get("code")
        err_type = error_block.get("type")
        detail_message = error_block.get("message")

        prologue = combined[:brace_index].strip()
        lines: list[str] = []
        if prologue and (not detail_message or prologue not in detail_message):
            lines.append(prologue)
        if detail_message:
            lines.append(detail_message)

        header = "Gemini CLI reported a tool failure"
        if code:
            header = f"{header} ({code})"
        elif err_type:
            header = f"{header} ({err_type})"

        content_lines = [header.rstrip(".") + "."]
        content_lines.extend(lines)
        message = "\n".join(content_lines).strip()

        metadata = {
            "cli_error_recovered": True,
            "cli_error_code": code,
            "cli_error_type": err_type,
            "cli_error_payload": payload,
        }

        parsed = ParsedCLIResponse(content=message or header, metadata=metadata)
        return AgentOutput(
            parsed=parsed,
            sanitized_command=sanitized_command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration_seconds,
            parser_name=self._parser.name,
            output_file_content=output_file_content,
        )
