"""
CLI Workflow Runner - Manages multi-step workflow execution for WorkflowTools

This utility enables CLI commands to execute WorkflowTools (planner, analyze, etc.)
in a single invocation by managing the multi-step workflow internally.

WorkflowTools are designed for conversational MCP workflows where each step is a
separate tool call. The CLI needs single-invocation completion, so this runner:
- Initializes workflow with step 1
- Executes steps in a loop until completion
- Consolidates results for CLI presentation
"""

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CLIWorkflowRunner:
    """Manages multi-step workflow execution for CLI tools"""

    def __init__(self, max_steps: int = 20):
        """
        Initialize workflow runner.

        Args:
            max_steps: Safety limit for maximum workflow steps (default: 20)
        """
        self.max_steps = max_steps

    async def run_workflow(
        self, tool_instance, initial_prompt: str, options: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """
        Execute a complete workflow tool from CLI invocation.

        Args:
            tool_instance: Instance of WorkflowTool (PlannerTool, AnalyzeTool, etc.)
            initial_prompt: User's initial prompt/goal
            options: Dict of CLI options (model, files, etc.)

        Returns:
            Dict with consolidated workflow results

        Raises:
            ValueError: If workflow exceeds max_steps
            Exception: If workflow execution fails
        """
        options = options or {}

        step_number = 1
        total_steps = 5  # Initial estimate
        next_step_required = True

        workflow_history = []
        tool_name = tool_instance.get_name()

        logger.info(f"Starting {tool_name} workflow with prompt: {initial_prompt[:50]}...")

        try:
            while next_step_required and step_number <= self.max_steps:
                # Build step-specific arguments
                step_arguments = self._build_step_arguments(
                    tool_instance=tool_instance,
                    initial_prompt=initial_prompt,
                    step_number=step_number,
                    total_steps=total_steps,
                    workflow_history=workflow_history,
                    options=options,
                )

                logger.debug(f"Executing {tool_name} step {step_number}/{total_steps}")

                # Execute workflow step
                result = await tool_instance.execute(step_arguments)
                workflow_history.append({"step_number": step_number, "arguments": step_arguments, "result": result})

                # Parse continuation signals
                result_data = json.loads(result[0].text)
                next_step_required = result_data.get("next_step_required", False)

                # Update total_steps if tool provides new estimate
                if "total_steps" in result_data:
                    total_steps = result_data["total_steps"]

                step_number += 1

                # Log progress
                if next_step_required:
                    logger.info(f"{tool_name} step {step_number-1}/{total_steps} complete, continuing...")

            if step_number > self.max_steps:
                raise ValueError(
                    f"Workflow exceeded maximum steps ({self.max_steps}). "
                    f"Possible infinite loop or overly complex task."
                )

            logger.info(f"{tool_name} workflow completed in {len(workflow_history)} steps")

            return self._consolidate_results(workflow_history, tool_name)

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}", exc_info=True)
            raise

    def _build_step_arguments(
        self,
        tool_instance,
        initial_prompt: str,
        step_number: int,
        total_steps: int,
        workflow_history: list[dict],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build tool-specific arguments for current workflow step.

        Args:
            tool_instance: The workflow tool instance
            initial_prompt: Initial user prompt
            step_number: Current step number (1-indexed)
            total_steps: Current estimate of total steps
            workflow_history: List of previous step results
            options: CLI options (model, files, etc.)

        Returns:
            Dict of arguments for tool.execute()
        """
        tool_name = tool_instance.get_name()

        # Base workflow arguments (required by all WorkflowRequest schemas)
        arguments = {
            "step": initial_prompt if step_number == 1 else f"Continue {tool_name} - Step {step_number}",
            "step_number": step_number,
            "total_steps": total_steps,
            "next_step_required": True,  # Will be determined by tool response
            "working_directory": os.getcwd(),
        }

        # Add tool-specific initialization fields for step 1
        if step_number == 1:
            arguments.update(self._get_step_one_fields(tool_name, initial_prompt, options))
        else:
            # For continuation steps, carry forward accumulated data
            arguments.update(self._get_continuation_fields(tool_name, workflow_history, options))

        # Add common optional fields
        if options.get("model"):
            arguments["model"] = options["model"]

        if options.get("files"):
            arguments["files"] = list(options["files"])

        return arguments

    def _get_step_one_fields(self, tool_name: str, initial_prompt: str, options: dict[str, Any]) -> dict[str, Any]:
        """
        Get tool-specific fields required for step 1 initialization.

        Each WorkflowTool has different requirements for step 1.
        This method provides tool-specific defaults.
        """
        # Common defaults for most WorkflowTools
        step_one_fields = {
            "findings": f"Initializing {tool_name} workflow",
            "files_checked": [],
            "relevant_files": options.get("files", []),
            "relevant_context": [],
            "confidence": "exploring",
        }

        # Tool-specific customizations
        if tool_name == "planner":
            # Planner doesn't need findings/files_checked initially
            step_one_fields = {}

        elif tool_name == "analyze":
            step_one_fields.update(
                {
                    "analysis_type": options.get("analysis_type", "architecture"),
                }
            )

        elif tool_name == "thinkdeep":
            step_one_fields.update(
                {
                    "reasoning_depth": options.get("depth", "extended"),
                }
            )

        elif tool_name == "testgen":
            step_one_fields.update(
                {
                    "framework": options.get("framework", "pytest"),
                    "test_type": options.get("test_type", "unit"),
                }
            )

        elif tool_name == "secaudit":
            step_one_fields.update(
                {
                    "focus": options.get("focus", "all"),
                    "issues_found": [],
                }
            )

        elif tool_name == "refactor":
            step_one_fields.update(
                {
                    "refactor_type": options.get("refactor_type", "codesmells"),
                    "focus_areas": options.get("focus_areas", []),
                    "issues_found": [],
                }
            )

        elif tool_name == "docgen":
            step_one_fields = {
                "findings": "Discovery phase - identifying files needing documentation",
                "relevant_files": options.get("files", []),
                "relevant_context": [],
                "num_files_documented": 0,
                "total_files_to_document": 0,
                "document_complexity": options.get("document_complexity", True),
                "document_flow": options.get("document_flow", True),
                "update_existing": options.get("update_existing", True),
                "comments_on_complex_logic": options.get("comments_on_complex_logic", True),
            }

        elif tool_name == "tracer":
            step_one_fields = {
                "findings": f"Beginning trace analysis of: {initial_prompt}",
                "files_checked": [],
                "relevant_files": [],
                "relevant_context": [],
                "trace_mode": options.get("trace_mode", "ask"),
                "target_description": initial_prompt,
            }

        elif tool_name == "precommit":
            step_one_fields.update(
                {
                    "validation_type": options.get("validation_type", "all"),
                }
            )

        return step_one_fields

    def _get_continuation_fields(
        self, tool_name: str, workflow_history: list[dict], options: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Get fields for continuation steps (step 2+).

        For now, returns basic continuation fields. In the future, this could
        analyze workflow_history to carry forward accumulated findings.
        """
        # Get last result to carry forward state
        if workflow_history:
            last_result = json.loads(workflow_history[-1]["result"][0].text)

            return {
                "findings": last_result.get("findings", f"Continuing {tool_name} analysis"),
                "files_checked": last_result.get("files_checked", []),
                "relevant_files": last_result.get("relevant_files", []),
                "relevant_context": last_result.get("relevant_context", []),
                "confidence": last_result.get("confidence", "medium"),
            }

        # Fallback if no history available
        return {
            "findings": f"Continuing {tool_name} analysis",
            "files_checked": [],
            "relevant_files": options.get("files", []),
            "relevant_context": [],
            "confidence": "medium",
        }

    def _consolidate_results(self, workflow_history: list[dict], tool_name: str) -> dict[str, Any]:
        """
        Consolidate workflow results for CLI presentation.

        Args:
            workflow_history: List of step results
            tool_name: Name of the workflow tool

        Returns:
            Consolidated workflow results
        """
        if not workflow_history:
            return {
                "status": "error",
                "error": "No workflow steps executed",
                "content": "Workflow completed with no steps",
            }

        # Get final step result
        final_result = json.loads(workflow_history[-1]["result"][0].text)

        # Build consolidated response
        consolidated = {
            "status": "completed",
            "tool": tool_name,
            "total_steps": len(workflow_history),
            "content": final_result.get("content", final_result.get("step", "")),
            "final_result": final_result,
            "workflow_summary": {
                "steps_completed": len(workflow_history),
                "final_confidence": final_result.get("confidence", "unknown"),
                "files_analyzed": len(final_result.get("relevant_files", [])),
            },
        }

        # Add tool-specific consolidated data
        if "findings" in final_result:
            consolidated["findings"] = final_result["findings"]

        if "issues_found" in final_result:
            consolidated["issues_found"] = final_result["issues_found"]

        return consolidated
