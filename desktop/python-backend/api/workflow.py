"""Workflow engine API — list and execute predefined workflows."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from workflow_engine import WORKFLOWS, build_workflow_prompt

logger = logging.getLogger("hermes-backend.workflow")
router = APIRouter()


class WorkflowListResponse(BaseModel):
    workflows: list[dict]


class WorkflowDetailResponse(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    category: str
    inputs: list[dict]
    prompt: str


class WorkflowExecuteRequest(BaseModel):
    workflow_id: str
    inputs: dict = {}
    session_id: Optional[str] = None
    model: Optional[str] = "default"
    base_url: Optional[str] = None
    api_key: Optional[str] = None


@router.get("/api/workflows", response_model=WorkflowListResponse)
async def list_workflows():
    """List all available workflows."""
    workflows = []
    for wf_id, wf in WORKFLOWS.items():
        workflows.append({
            "id": wf_id,
            "name": wf["name"],
            "description": wf["description"],
            "icon": wf["icon"],
            "category": wf["category"],
            "inputs": wf.get("inputs", []),
        })
    return WorkflowListResponse(workflows=workflows)


@router.get("/api/workflows/{workflow_id}", response_model=WorkflowDetailResponse)
async def get_workflow(workflow_id: str):
    """Get workflow details with rendered prompt."""
    if workflow_id not in WORKFLOWS:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    
    wf = WORKFLOWS[workflow_id]
    # Render prompt with default values
    defaults = {inp["name"]: inp.get("default", "") for inp in wf.get("inputs", [])}
    prompt = build_workflow_prompt(workflow_id, defaults)
    
    return WorkflowDetailResponse(
        id=workflow_id,
        name=wf["name"],
        description=wf["description"],
        icon=wf["icon"],
        category=wf["category"],
        inputs=wf.get("inputs", []),
        prompt=prompt,
    )


@router.post("/api/workflows/execute")
async def execute_workflow(request: WorkflowExecuteRequest):
    """Execute a workflow by building its prompt and sending to chat.
    
    Returns the rendered prompt — the frontend should send it via /api/chat.
    """
    if request.workflow_id not in WORKFLOWS:
        raise HTTPException(status_code=404, detail=f"Workflow '{request.workflow_id}' not found")
    
    prompt = build_workflow_prompt(request.workflow_id, request.inputs)
    
    return {
        "workflow_id": request.workflow_id,
        "prompt": prompt,
        "session_id": request.session_id,
        "model": request.model,
        "base_url": request.base_url,
        "api_key": request.api_key,
    }
