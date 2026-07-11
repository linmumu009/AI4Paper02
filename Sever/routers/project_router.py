"""Research project (课题空间) API."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services import auth_service, project_service


router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    objective: str = Field(default="", max_length=2000)
    description: str = Field(default="", max_length=5000)


class UpdateProjectBody(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    objective: Optional[str] = Field(default=None, max_length=2000)
    description: Optional[str] = Field(default=None, max_length=5000)


class ProjectAssetBody(BaseModel):
    asset_type: str = Field(..., min_length=1, max_length=40)
    asset_id: str = Field(..., min_length=1, max_length=200)
    source_scope: str = Field(default="", max_length=40)
    metadata: dict = Field(default_factory=dict)


@router.get("", summary="List research projects")
def api_list_projects(
    include_archived: bool = False,
    user=Depends(auth_service.require_user),
):
    return {"projects": project_service.list_projects(user["id"], include_archived)}


@router.post("", summary="Create a research project")
def api_create_project(
    body: CreateProjectBody,
    user=Depends(auth_service.require_user),
):
    try:
        return project_service.create_project(
            user["id"], body.name, body.objective, body.description
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}", summary="Get a research project and its assets")
def api_get_project(project_id: int, user=Depends(auth_service.require_user)):
    project = project_service.get_project(user["id"], project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", summary="Update a research project")
def api_update_project(
    project_id: int,
    body: UpdateProjectBody,
    user=Depends(auth_service.require_user),
):
    try:
        project = project_service.update_project(
            user["id"], project_id, **body.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/{project_id}/archive", summary="Archive a research project")
def api_archive_project(project_id: int, user=Depends(auth_service.require_user)):
    if not project_service.set_project_status(user["id"], project_id, "archived"):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"ok": True}


@router.post("/{project_id}/restore", summary="Restore an archived research project")
def api_restore_project(project_id: int, user=Depends(auth_service.require_user)):
    if not project_service.set_project_status(user["id"], project_id, "active"):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"ok": True}


@router.delete("/{project_id}", summary="Soft-delete a research project")
def api_delete_project(project_id: int, user=Depends(auth_service.require_user)):
    if not project_service.set_project_status(user["id"], project_id, "deleted"):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"ok": True}


@router.post("/{project_id}/assets", summary="Add an asset to a research project")
def api_add_project_asset(
    project_id: int,
    body: ProjectAssetBody,
    user=Depends(auth_service.require_user),
):
    try:
        return project_service.add_asset(
            user["id"],
            project_id,
            body.asset_type,
            body.asset_id,
            body.source_scope,
            body.metadata,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/{project_id}/assets/{asset_type}/{asset_id}",
    summary="Remove an asset relation without deleting the source asset",
)
def api_remove_project_asset(
    project_id: int,
    asset_type: str,
    asset_id: str,
    source_scope: str = Query(default=""),
    user=Depends(auth_service.require_user),
):
    removed = project_service.remove_asset(
        user["id"], project_id, asset_type, asset_id, source_scope
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Project asset not found")
    return {"ok": True}
