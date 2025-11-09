# Tool Schema Compatibility Analysis

## Executive Summary

**CRITICAL ISSUE DISCOVERED**: All 13 newly added CLI tools have schema mismatches with the current CLI implementation. The CLI assumes a simple prompt-based pattern, but tools are divided into two categories with different schema requirements:

- **9 WorkflowTools** (planner, analyze, thinkdeep, precommit, testgen, secaudit, refactor, docgen, tracer)
- **3 SimpleTools** (clink, challenge, apilookup)

All require different invocation patterns than what the CLI currently provides.

---

## Tool Categorization

### Category 1: WorkflowTools (9 tools)

These tools implement multi-step workflows requiring complex request schemas:

| Tool | Request Class | Required Fields |
|------|---------------|-----------------|
| **planner** | PlannerRequest(WorkflowRequest) | step, step_number, total_steps, next_step_required |
| **analyze** | AnalyzeRequest(WorkflowRequest) | step, step_number, total_steps, next_step_required, findings, files_checked, relevant_files |
| **thinkdeep** | ThinkDeepRequest(WorkflowRequest) | step, step_number, total_steps, next_step_required, findings |
| **precommit** | PrecommitRequest(WorkflowRequest) | step, step_number, total_steps, next_step_required, findings, files_checked, relevant_files |
| **testgen** | TestgenRequest(WorkflowRequest) | step, step_number, total_steps, next_step_required, findings, files_checked, relevant_files |
| **secaudit** | SecauditRequest(WorkflowRequest) | step, step_number, total_steps, next_step_required, findings, files_checked, relevant_files, issues_found |
| **refactor** | RefactorRequest(WorkflowRequest) | step, step_number, total_steps, next_step_required, findings, files_checked, relevant_files, issues_found |
| **docgen** | DocgenRequest(WorkflowRequest) | step, step_number, total_steps, next_step_required, findings, relevant_files, num_files_documented, total_files_to_document |
| **tracer** | TracerRequest(WorkflowRequest) | step, step_number, total_steps, next_step_required, findings, files_checked, relevant_files, trace_mode, target_description |

**Common Pattern**: All inherit from `WorkflowRequest` which requires:
```python
class WorkflowRequest(BaseModel):
    step: str                    # Description of current step
    step_number: int            # Current step index (starts at 1)
    total_steps: int           # Estimated total steps
    next_step_required: bool   # Whether to continue workflow
    # Plus tool-specific fields
```

### Category 2: SimpleTools (3 tools)

These tools use simple, single-invocation patterns:

| Tool | Request Class | Required Fields | Purpose |
|------|---------------|-----------------|---------|
| **clink** | ToolRequest | prompt, cli_name, role | CLI-to-CLI bridge for spawning subagents |
| **challenge** | ChallengeRequest(ToolRequest) | prompt | Critical thinking prompt wrapper |
| **apilookup** | LookupRequest(ToolRequest) | prompt | API documentation lookup instructions |

**Common Pattern**: Inherit from `ToolRequest` or `SimpleTool.execute()` pattern:
```python
class ToolRequest(BaseModel):
    prompt: str                 # The main input
    # Plus optional tool-specific fields
```

---

## Current CLI Implementation

**What the CLI currently does** (src/zen_cli/main.py):

```python
@cli.command()
@click.argument('goal')
@click.option('--model', '-m')
@click.option('--files', '-f', multiple=True)
@click.option('--json', 'output_json', is_flag=True)
def planner(ctx, goal, model, files, output_json):
    arguments = {
        "prompt": goal,                          # ❌ Tool expects "step", not "prompt"
        "working_directory": os.getcwd(),        # ❌ Not part of schema
        # Missing: step_number, total_steps, next_step_required
    }

    if model:
        arguments["model"] = model

    result = asyncio.run(PlannerTool().execute(arguments))
```

**What the tool expects** (tools/planner.py):

```python
class PlannerRequest(WorkflowRequest):
    step: str = Field(...)                  # ✅ Required
    step_number: int = Field(...)          # ❌ Missing from CLI
    total_steps: int = Field(...)          # ❌ Missing from CLI
    next_step_required: bool = Field(...)  # ❌ Missing from CLI
```

**Result**: `ValidationError: 3 validation errors for PlannerRequest`
- `step_number: Field required`
- `total_steps: Field required`
- `next_step_required: Field required`

---

## Why This Mismatch Exists

### MCP Server vs CLI Usage Pattern

**MCP Server Pattern (Original Design)**:
1. MCP client (Claude Code) calls planner with step 1
2. Tool responds with next_step_required=True
3. Claude Code performs investigation work
4. Claude Code calls planner again with step 2
5. Repeat until next_step_required=False
6. Multi-turn conversational workflow

**CLI Single-Call Pattern (Current Implementation)**:
1. User runs `zen planner "goal"`
2. Tool should complete entire workflow
3. Single invocation, single result
4. No conversational loop

### The Fundamental Problem

WorkflowTools were designed for **conversational MCP workflows** where:
- Each step is a separate tool call
- MCP client manages the workflow loop
- Steps build on previous conversation context

CLI needs **single-invocation completion** where:
- One command executes entire workflow
- Tool manages all steps internally
- Returns final result to user

---

## Proposed Solutions

### Solution A: Workflow Wrapper Layer ⭐ RECOMMENDED

Create CLI-specific wrapper that handles workflow internally:

```python
@cli.command()
def planner(ctx, goal, model, files, output_json):
    """Generate sequential task plan (multi-step workflow)"""

    # Initialize workflow with step 1
    step_number = 1
    total_steps = 5  # Initial estimate
    next_step_required = True

    workflow_results = []

    while next_step_required and step_number <= 10:  # Safety limit
        arguments = {
            "step": goal if step_number == 1 else f"Continue planning - Step {step_number}",
            "step_number": step_number,
            "total_steps": total_steps,
            "next_step_required": True,  # Will be updated by tool response
            "working_directory": os.getcwd(),
        }

        if model:
            arguments["model"] = model
        if files:
            arguments["files"] = list(files)

        # Execute workflow step
        result = asyncio.run(PlannerTool().execute(arguments))
        workflow_results.append(result)

        # Parse result to determine if continuation needed
        result_data = json.loads(result[0].text)
        next_step_required = result_data.get("next_step_required", False)
        step_number += 1
        total_steps = result_data.get("total_steps", total_steps)

    # Present final result
    if output_json:
        console.print_json(data=workflow_results[-1])
    else:
        # Present consolidated workflow output
        for result in workflow_results:
            content = json.loads(result[0].text)
            console.print(Markdown(content.get('content', str(content))))
```

**Pros**:
- ✅ Maintains tool architecture unchanged
- ✅ Works with existing MCP server patterns
- ✅ CLI provides simplified UX (one command = full workflow)
- ✅ Reuses all existing tool logic

**Cons**:
- ⚠️ More complex CLI implementation
- ⚠️ Requires workflow management logic in CLI

### Solution B: SimpleTool Adapters

Create simplified CLI-only versions:

```python
# tools/cli_adapters/planner_cli.py
class PlannerCLITool(SimpleTool):
    """CLI-friendly wrapper around PlannerTool"""

    async def execute(self, arguments: dict):
        # Convert simple prompt to workflow format
        # Execute all steps internally
        # Return consolidated result
        pass
```

**Pros**:
- ✅ Clean separation of CLI vs MCP patterns
- ✅ Simple CLI invocation

**Cons**:
- ❌ Code duplication
- ❌ Maintenance burden (two versions of each tool)
- ❌ May diverge over time

### Solution C: Remove WorkflowTools from CLI

Only expose SimpleTools (clink, challenge, apilookup):

```python
# Keep these in CLI
zen clink "prompt" --cli-name codex
zen challenge "statement to challenge"
zen apilookup "API documentation query"

# Remove these from CLI (MCP-only)
# zen planner, zen analyze, zen thinkdeep, etc.
```

**Pros**:
- ✅ Quick fix
- ✅ No schema mismatches
- ✅ Simpler CLI

**Cons**:
- ❌ Massive feature loss
- ❌ Defeats purpose of CLI feature parity
- ❌ User disappointment

---

## Recommended Implementation Plan

### Phase 1: Fix SimpleTools (Quick Win)

**clink** (CLI-to-CLI bridge):
```python
@cli.command()
@click.argument('prompt')
@click.option('--cli-name', required=True)
@click.option('--role', default=None)
def clink(ctx, prompt, cli_name, role):
    arguments = {
        "prompt": prompt,
        "cli_name": cli_name,
        "role": role or "assistant",
        "files": [],
        "working_directory": os.getcwd(),
    }
    result = asyncio.run(ClinkTool().execute(arguments))
    # Present result
```

**challenge**:
```python
@cli.command()
@click.argument('statement', nargs=-1, required=True)
def challenge(ctx, statement):
    full_statement = ' '.join(statement)
    arguments = {"prompt": full_statement}
    result = asyncio.run(ChallengeTool().execute(arguments))
    # Present wrapped challenge prompt
```

**apilookup**:
```python
@cli.command()
@click.argument('query', nargs=-1, required=True)
def apilookup(ctx, query):
    full_query = ' '.join(query)
    arguments = {"prompt": full_query}
    result = asyncio.run(LookupTool().execute(arguments))
    # Present lookup instructions
```

### Phase 2: Implement Workflow Wrapper (WorkflowTools)

Create `utils/cli_workflow_runner.py`:

```python
class CLIWorkflowRunner:
    """Manages multi-step workflow execution for CLI tools"""

    async def run_workflow(self, tool_instance, initial_prompt, options):
        """
        Execute a complete workflow tool from CLI invocation.

        Args:
            tool_instance: Instance of WorkflowTool (PlannerTool, AnalyzeTool, etc.)
            initial_prompt: User's initial prompt/goal
            options: Dict of CLI options (model, files, etc.)

        Returns:
            Complete workflow results
        """
        step_number = 1
        total_steps = 5  # Initial estimate
        next_step_required = True
        max_steps = 20  # Safety limit

        workflow_history = []

        while next_step_required and step_number <= max_steps:
            # Build step-specific arguments
            step_arguments = self._build_step_arguments(
                tool_instance,
                initial_prompt,
                step_number,
                total_steps,
                workflow_history,
                options
            )

            # Execute workflow step
            result = await tool_instance.execute(step_arguments)
            workflow_history.append(result)

            # Parse continuation signals
            result_data = json.loads(result[0].text)
            next_step_required = result_data.get("next_step_required", False)
            total_steps = result_data.get("total_steps", total_steps)
            step_number += 1

            # Optional: Add progress indicator
            if next_step_required:
                console.print(f"[dim]Step {step_number-1}/{total_steps} complete...[/dim]")

        return self._consolidate_results(workflow_history)

    def _build_step_arguments(self, tool, prompt, step_num, total, history, opts):
        """Build tool-specific arguments for current workflow step"""
        # Tool-specific argument building logic
        pass
```

Then update CLI commands to use runner:

```python
from utils.cli_workflow_runner import CLIWorkflowRunner

@cli.command()
def planner(ctx, goal, model, files, output_json):
    """Generate sequential task plan"""
    runner = CLIWorkflowRunner()
    options = {"model": model, "files": files, "output_json": output_json}

    result = asyncio.run(
        runner.run_workflow(PlannerTool(), goal, options)
    )

    # Present result
    if output_json:
        console.print_json(data=result)
    else:
        console.print(Markdown(result.get('content')))
```

### Phase 3: Tool-Specific Customization

Each WorkflowTool may need custom step argument building:

- **planner**: Simple step progression
- **analyze**: Needs analysis_type, findings accumulation
- **thinkdeep**: Extended reasoning mode support
- **testgen**: Framework selection, test type
- **secaudit**: Security focus areas, severity tracking
- **refactor**: Refactor type, focus areas, style guides
- **docgen**: File counting, num_files_documented tracking
- **tracer**: trace_mode selection (precision vs dependencies)
- **precommit**: Pre-commit validation workflow

---

## Testing Strategy

### Unit Tests
- Test workflow runner with mock tools
- Verify step argument building
- Test continuation logic
- Safety limits (max steps)

### Integration Tests
```bash
# SimpleTools
zen clink "Review this code" --cli-name codex --role reviewer
zen challenge "AI will replace all developers"
zen apilookup "latest React hooks API 2025"

# WorkflowTools (after wrapper implementation)
zen planner "Implement OAuth authentication"
zen analyze --files src/**/*.py --analysis-type architecture
zen testgen --files auth.py --framework pytest
```

### Acceptance Criteria
- ✅ All 13 tools execute without validation errors
- ✅ SimpleTools work with correct argument patterns
- ✅ WorkflowTools complete multi-step workflows
- ✅ Results presented correctly (JSON and Markdown)
- ✅ No schema mismatches or missing field errors

---

## Implementation Timeline

| Phase | Task | Estimated Effort | Priority |
|-------|------|------------------|----------|
| 1 | Fix SimpleTools (clink, challenge, apilookup) | 2-3 hours | HIGH |
| 2 | Create CLIWorkflowRunner utility | 4-6 hours | HIGH |
| 3 | Update planner CLI command (proof of concept) | 2 hours | HIGH |
| 4 | Update remaining 8 WorkflowTools | 6-8 hours | MEDIUM |
| 5 | Testing and validation | 4 hours | HIGH |
| 6 | Documentation updates | 2 hours | MEDIUM |

**Total Estimated Effort**: 20-29 hours

---

## Next Steps

1. ✅ Complete tool schema analysis (DONE)
2. ⏭️ Implement SimpleTools fixes (clink, challenge, apilookup)
3. ⏭️ Create CLIWorkflowRunner utility class
4. ⏭️ Update planner command as proof of concept
5. ⏭️ Extend to all WorkflowTools
6. ⏭️ Comprehensive testing
7. ⏭️ Update documentation

---

## Conclusion

The schema mismatch is a **fundamental architectural difference** between:
- **MCP Server Pattern**: Multi-turn conversational workflows
- **CLI Pattern**: Single-invocation completion

**Solution A (Workflow Wrapper)** is recommended because it:
- Maintains tool architecture integrity
- Provides simplified CLI UX
- Achieves complete feature parity
- Requires reasonable implementation effort

This approach allows zen-cli to offer the same powerful workflow capabilities as the MCP server while providing the simplicity expected from command-line tools.

---

**Status**: Analysis complete. Ready for implementation.
**Next Action**: Implement SimpleTools fixes (Phase 1)
