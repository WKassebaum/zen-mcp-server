"""
Workflow Session Management - Enables multi-step workflow continuity

This module provides session-based workflow management for WorkflowTools,
allowing them to work seamlessly in CLI mode by maintaining conversation
state between invocations.

Key Features:
- Auto-generated unique session IDs
- Session state persistence (file/redis/memory)
- Automatic continuation instructions for Claude Code
- Session expiration and cleanup (3 hour TTL)
- Resume workflows across multiple CLI invocations
"""

import logging
import random
import string
import time
from datetime import datetime, timezone
from typing import Any, Optional

from utils.storage_backend import get_storage_backend

logger = logging.getLogger(__name__)

# Session TTL: 3 hours (same as conversation timeout)
SESSION_TTL_SECONDS = 10800


def generate_session_id(tool_name: str) -> str:
    """
    Generate unique session ID for workflow continuity.

    Format: {tool_name}_{timestamp}_{random_suffix}
    Example: planner_1728483022_a3f9b2c1

    Args:
        tool_name: Name of the workflow tool (planner, analyze, etc.)

    Returns:
        Unique session ID string
    """
    timestamp = int(time.time())
    random_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    session_id = f"{tool_name}_{timestamp}_{random_suffix}"

    logger.debug(f"Generated session ID: {session_id}")
    return session_id


def save_session_state(session_id: str, tool_name: str, result_data: dict[str, Any], arguments: dict[str, Any]) -> None:
    """
    Save workflow state for next continuation.

    Persists all necessary information to resume the workflow from
    the current step, including accumulated findings, files checked,
    and workflow metadata.

    Args:
        session_id: Unique session identifier
        tool_name: Name of the workflow tool
        result_data: Current tool execution result
        arguments: Arguments used for current step
    """
    state = {
        "session_id": session_id,
        "tool_name": tool_name,
        # Workflow progress
        "step_number": result_data.get("step_number", 1),
        "total_steps": result_data.get("total_steps", 5),
        "next_step_required": result_data.get("next_step_required", True),
        # Accumulated investigation data
        "findings": result_data.get("findings", ""),
        "files_checked": result_data.get("files_checked", []),
        "relevant_files": result_data.get("relevant_files", []),
        "relevant_context": result_data.get("relevant_context", []),
        "confidence": result_data.get("confidence", "exploring"),
        # Tool-specific data
        "issues_found": result_data.get("issues_found", []),
        "hypotheses": result_data.get("hypotheses", []),
        # Metadata
        "last_arguments": arguments,
        "created_at": (
            state.get("created_at", datetime.now(timezone.utc).isoformat())
            if isinstance(state := load_session_state(session_id) or {}, dict)
            else datetime.now(timezone.utc).isoformat()
        ),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    storage = get_storage_backend()
    key = f"workflow_session:{session_id}"
    storage.set(key, state, ttl=SESSION_TTL_SECONDS)

    logger.info(f"Saved session state for {session_id} (step {state['step_number']}/{state['total_steps']})")


def load_session_state(session_id: str) -> Optional[dict[str, Any]]:
    """
    Load previous workflow state from storage.

    Args:
        session_id: Unique session identifier

    Returns:
        Session state dict if found and not expired, None otherwise
    """
    storage = get_storage_backend()
    key = f"workflow_session:{session_id}"
    state = storage.get(key)

    if state:
        logger.debug(f"Loaded session state for {session_id}")
    else:
        logger.debug(f"No session state found for {session_id}")

    return state


def delete_session_state(session_id: str) -> None:
    """
    Delete session state from storage.

    Called when workflow completes or user explicitly cancels.

    Args:
        session_id: Unique session identifier
    """
    storage = get_storage_backend()
    key = f"workflow_session:{session_id}"
    storage.delete(key)

    logger.info(f"Deleted session state for {session_id}")


def list_active_sessions(tool_name: Optional[str] = None) -> list:
    """
    List all active workflow sessions.

    Args:
        tool_name: Optional filter by tool name

    Returns:
        List of (session_id, state_dict) tuples
    """
    storage = get_storage_backend()
    keys = storage.list_keys("workflow_session:*")

    active_sessions = []
    for key in keys:
        session_id = key.replace("workflow_session:", "")
        state = storage.get(key)

        if state:
            # Filter by tool name if specified
            if tool_name and state.get("tool_name") != tool_name:
                continue

            active_sessions.append((session_id, state))

    # Sort by last updated (most recent first)
    active_sessions.sort(key=lambda x: x[1].get("last_updated", ""), reverse=True)

    return active_sessions


def enhance_with_continuation_instructions(
    result_data: dict[str, Any], session_id: str, tool_name: str
) -> dict[str, Any]:
    """
    Add session ID and continuation instructions to tool response.

    This is the key function that makes session-based workflows work seamlessly
    with Claude Code. It embeds instructions directly in the tool response,
    telling Claude exactly how to continue the workflow.

    Args:
        result_data: Original tool execution result
        session_id: Session identifier for this workflow
        tool_name: Name of the workflow tool

    Returns:
        Enhanced result with session metadata and instructions
    """
    enhanced = result_data.copy()
    enhanced["session_id"] = session_id

    # Only add continuation instructions if more steps needed
    if result_data.get("next_step_required", False):
        continuation_cmd = f"zen {tool_name} --session {session_id} --continue '<your findings here>'"

        enhanced["continuation_command"] = continuation_cmd
        enhanced["workflow_status"] = "in_progress"
        enhanced["workflow_instructions"] = {
            "for_claude_code": (
                f"MANDATORY WORKFLOW CONTINUATION:\n"
                f"1. You MUST perform the investigation/work requested in the step content above\n"
                f"2. After completing the work, you MUST call this exact command:\n"
                f"   {continuation_cmd}\n"
                f"3. Replace '<your findings here>' with your actual investigation results/work output\n"
                f"4. Do NOT proceed with other tasks until this workflow is marked as complete\n"
                f"5. This session will expire in 3 hours if not continued\n"
                f"6. Current progress: Step {result_data.get('step_number', 1)} of {result_data.get('total_steps', '?')}"
            ),
            "for_manual_users": (
                f"To continue this workflow:\n"
                f"1. Perform the investigation or work described above\n"
                f"2. Run: {continuation_cmd}\n"
                f"3. Replace '<your findings here>' with what you discovered or completed\n"
                f"4. Session expires in 3 hours"
            ),
        }
    else:
        # Workflow complete
        enhanced["workflow_status"] = "complete"
        enhanced["workflow_instructions"] = {
            "for_claude_code": "Workflow completed successfully. You may now proceed with presenting results or next tasks.",
            "for_manual_users": "Workflow completed successfully. No further action needed.",
        }

        # Clean up session since workflow is complete
        delete_session_state(session_id)

    return enhanced


def build_continuation_arguments(
    session_state: dict[str, Any], continue_findings: str, model: Optional[str] = None
) -> dict[str, Any]:
    """
    Build arguments for workflow continuation step.

    Reconstructs the full argument set needed for the next workflow step
    by combining session state with new findings.

    Args:
        session_state: Loaded session state from previous step
        continue_findings: New findings/work from user/Claude
        model: Optional model override

    Returns:
        Complete arguments dict for tool.execute()
    """
    # Increment step number
    next_step = session_state["step_number"] + 1

    arguments = {
        # Current step info
        "step": continue_findings,
        "step_number": next_step,
        "total_steps": session_state["total_steps"],
        "next_step_required": True,  # Will be determined by tool
        # Accumulated state from previous steps
        "findings": session_state.get("findings", ""),
        "files_checked": session_state.get("files_checked", []),
        "relevant_files": session_state.get("relevant_files", []),
        "relevant_context": session_state.get("relevant_context", []),
        "confidence": session_state.get("confidence", "exploring"),
        # Tool-specific accumulated data
        "issues_found": session_state.get("issues_found", []),
        # Working directory from original invocation
        "working_directory": session_state.get("last_arguments", {}).get("working_directory", "."),
    }

    # Add model if specified (override session default)
    if model:
        arguments["model"] = model
    elif "model" in session_state.get("last_arguments", {}):
        arguments["model"] = session_state["last_arguments"]["model"]

    # Carry forward any files from original invocation
    if "files" in session_state.get("last_arguments", {}):
        arguments["files"] = session_state["last_arguments"]["files"]

    return arguments


def format_session_info(session_state: dict[str, Any]) -> str:
    """
    Format session information for display.

    Args:
        session_state: Session state dictionary

    Returns:
        Formatted string for console output
    """
    created = session_state.get("created_at", "unknown")
    updated = session_state.get("last_updated", "unknown")
    step = session_state.get("step_number", "?")
    total = session_state.get("total_steps", "?")

    return (
        f"Session: {session_state['session_id']}\n"
        f"Tool: {session_state['tool_name']}\n"
        f"Progress: Step {step}/{total}\n"
        f"Created: {created}\n"
        f"Last Updated: {updated}"
    )
