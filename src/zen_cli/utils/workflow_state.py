"""Workflow state management for multi-step tool execution.

This module provides state tracking for workflow tools that require
multiple steps to complete their analysis.
"""

import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class WorkflowState:
    """Tracks the state of a multi-step workflow execution."""
    
    tool_name: str
    continuation_id: str
    current_step: int = 1
    total_steps: int = 1
    next_step_required: bool = True
    findings: str = ""
    files_checked: list = field(default_factory=list)
    relevant_files: list = field(default_factory=list)
    issues_found: list = field(default_factory=list)
    confidence: str = "exploring"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowState':
        """Create state from dictionary."""
        return cls(**data)
    
    def should_continue(self) -> bool:
        """Check if workflow should continue to next step."""
        return self.next_step_required and self.current_step < self.total_steps
    
    def advance_step(self) -> None:
        """Advance to the next step."""
        self.current_step += 1
        if self.current_step >= self.total_steps:
            self.next_step_required = False


class WorkflowStateManager:
    """Manages workflow states across tool executions."""
    
    def __init__(self):
        """Initialize the workflow state manager."""
        # In-memory storage for now, can be backed by file/redis later
        self._states: Dict[str, WorkflowState] = {}
    
    def get_state(self, continuation_id: str, tool_name: str) -> Optional[WorkflowState]:
        """Retrieve workflow state for a continuation ID."""
        key = f"{tool_name}:{continuation_id}"
        return self._states.get(key)
    
    def save_state(self, state: WorkflowState) -> None:
        """Save workflow state."""
        key = f"{state.tool_name}:{state.continuation_id}"
        self._states[key] = state
        logger.debug(f"Saved workflow state for {key}: step {state.current_step}/{state.total_steps}")
    
    def delete_state(self, continuation_id: str, tool_name: str) -> None:
        """Delete workflow state when complete."""
        key = f"{tool_name}:{continuation_id}"
        if key in self._states:
            del self._states[key]
            logger.debug(f"Deleted workflow state for {key}")
    
    def update_from_response(self, state: WorkflowState, response: Dict[str, Any]) -> WorkflowState:
        """Update workflow state from tool response."""
        # Extract workflow information from response
        if isinstance(response, dict):
            # Update step information
            state.current_step = response.get('step_number', state.current_step)
            state.total_steps = response.get('total_steps', state.total_steps)
            state.next_step_required = response.get('next_step_required', False)
            
            # Update findings and files
            if 'findings' in response:
                state.findings = response['findings']
            if 'files_checked' in response:
                state.files_checked.extend(response['files_checked'])
            if 'relevant_files' in response:
                state.relevant_files = response['relevant_files']
            if 'issues_found' in response:
                state.issues_found.extend(response['issues_found'])
            if 'confidence' in response:
                state.confidence = response['confidence']
            
            # Store any additional metadata
            state.metadata.update({
                k: v for k, v in response.items() 
                if k not in ['step_number', 'total_steps', 'next_step_required', 
                            'findings', 'files_checked', 'relevant_files', 
                            'issues_found', 'confidence']
            })
        
        return state


# Global instance for easy access
_manager = None

def get_workflow_manager() -> WorkflowStateManager:
    """Get the global workflow state manager."""
    global _manager
    if _manager is None:
        _manager = WorkflowStateManager()
    return _manager