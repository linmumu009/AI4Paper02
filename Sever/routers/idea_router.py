"""
Idea Workbench Router.

All routes are prefixed with /api/idea and registered in api.py via
    app.include_router(idea_router)
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services import auth_service, data_service, idea_pipeline_service, idea_service, kb_service
from routers._deps import _get_optional_user, _tier_quota_limit, _tier_label

router = APIRouter(prefix="/api/idea", tags=["idea"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ExtractAtomsBody(BaseModel):
    paper_id: str
    date_str: str = ""


class GenerateQuestionsBody(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)


class GenerateCandidatesBody(BaseModel):
    question_id: Optional[int] = None
    custom_question: str = ""
    strategies: Optional[list[str]] = None


class CreateCandidateBody(BaseModel):
    title: str
    goal: str = ""
    mechanism: str = ""
    risks: str = ""
    strategy: str = ""
    question_id: Optional[int] = None
    tags: Optional[list[str]] = None
    folder_id: Optional[int] = None


class UpdateCandidateBody(BaseModel):
    title: Optional[str] = None
    goal: Optional[str] = None
    mechanism: Optional[str] = None
    risks: Optional[str] = None
    scores: Optional[dict] = None
    status: Optional[str] = None
    tags: Optional[list[str]] = None
    folder_id: Optional[int] = None
    strategy: Optional[str] = None


class ReviewCandidateBody(BaseModel):
    candidate_id: int


class ReviseCandidateBody(BaseModel):
    candidate_id: int
    review_feedback: str = ""


class GeneratePlanBody(BaseModel):
    candidate_id: int


class SavePlanBody(BaseModel):
    candidate_id: int
    milestones: Optional[list[dict]] = None
    metrics: str = ""
    datasets: str = ""
    ablation: str = ""
    cost: str = ""
    timeline: str = ""
    full_plan: str = ""


class FeedbackBody(BaseModel):
    candidate_id: int
    action: Optional[str] = Field(None, description="collect|discard|modify|implement|rate")
    event_type: Optional[str] = None
    context: Optional[dict] = None

    @property
    def resolved_action(self) -> str:
        return self.action or self.event_type or "view"


class CreateExemplarBody(BaseModel):
    candidate_id: int
    pattern: Optional[dict] = None
    score: float = 0.0
    notes: str = ""


class CreateBenchmarkBody(BaseModel):
    name: str
    question_ids: Optional[list[int]] = None
    model_version: str = ""


class EvalReplayBody(BaseModel):
    question_ids: list[int]


class CreatePromptVersionBody(BaseModel):
    stage: str
    prompt_text: str
    metrics: Optional[dict] = None


class UpdateAtomBody(BaseModel):
    atom_type: Optional[str] = None
    content: Optional[str] = None
    section: Optional[str] = None
    tags: Optional[list[str]] = None
    evidence: Optional[list[dict]] = None


class UpdatePlanBody(BaseModel):
    milestones: Optional[list[dict]] = None
    metrics: Optional[str] = None
    datasets: Optional[str] = None
    ablation: Optional[str] = None
    cost: Optional[str] = None
    timeline: Optional[str] = None
    full_plan: Optional[str] = None


class UpdateExemplarBody(BaseModel):
    score: Optional[float] = None
    notes: Optional[str] = None
    pattern: Optional[dict] = None


class UpdateBenchmarkBody(BaseModel):
    name: Optional[str] = None
    model_version: Optional[str] = None
    question_ids: Optional[list[int]] = None
    results: Optional[dict] = None


class UpdatePromptVersionBody(BaseModel):
    stage: Optional[str] = None
    prompt_text: Optional[str] = None
    metrics: Optional[dict] = None


class CreateIdeaFolderBody(BaseModel):
    name: str
    parent_id: Optional[int] = None


class MoveIdeaCandidatesBody(BaseModel):
    candidate_ids: list[int]
    target_folder_id: Optional[int] = None


class ManualReviewBody(BaseModel):
    action: str
    feedback: Optional[str] = None
    scores: Optional[dict] = None


class GenerateForPaperBody(BaseModel):
    paper_id: str
    force: bool = False


# ---------------------------------------------------------------------------
# Dashboard & stats
# ---------------------------------------------------------------------------

@router.get("/stats", summary="Idea dashboard stats")
def api_idea_stats(_user=Depends(auth_service.require_user)):
    return {"ok": True, **idea_service.get_stats(_user["id"])}


# ---------------------------------------------------------------------------
# Atoms
# ---------------------------------------------------------------------------

@router.get("/atoms", summary="List idea atoms")
def api_idea_list_atoms(
    paper_id: Optional[str] = None,
    atom_type: Optional[str] = None,
    tag: Optional[str] = None,
    date_str: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _user=Depends(auth_service.require_user),
):
    if query:
        try:
            atoms = idea_service.search_atoms_fts(query, user_id=_user["id"], limit=limit)
        except Exception:
            atoms = idea_service.list_atoms(user_id=_user["id"], limit=limit, offset=offset)
    else:
        atoms = idea_service.list_atoms(
            user_id=_user["id"], paper_id=paper_id, atom_type=atom_type,
            tag=tag, date_str=date_str, limit=limit, offset=offset,
        )
    return {"ok": True, "atoms": atoms, "count": len(atoms)}


@router.get("/atoms/{atom_id}", summary="Get idea atom")
def api_idea_get_atom(atom_id: int, _user=Depends(auth_service.require_user)):
    atom = idea_service.get_atom(atom_id)
    if not atom:
        raise HTTPException(status_code=404, detail="Atom not found")
    if atom.get("user_id") != _user["id"]:
        raise HTTPException(status_code=403, detail="Permission denied")
    return {"ok": True, "atom": atom}


@router.post("/atoms/extract", summary="Extract atoms from a paper")
def api_idea_extract_atoms(body: ExtractAtomsBody, _user=Depends(auth_service.require_user)):
    result = idea_pipeline_service.extract_atoms_for_paper(
        _user["id"], body.paper_id, body.date_str,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"ok": True, **result}


@router.patch("/atoms/{atom_id}", summary="Update an idea atom")
def api_idea_update_atom(atom_id: int, body: UpdateAtomBody, _user=Depends(auth_service.require_user)):
    updates = body.dict(exclude_unset=True)
    a = idea_service.update_atom(_user["id"], atom_id, **updates)
    if not a:
        raise HTTPException(status_code=404, detail="Atom not found or permission denied")
    return {"ok": True, "atom": a}


@router.delete("/atoms/{atom_id}", summary="Delete a single idea atom")
def api_idea_delete_atom(atom_id: int, _user=Depends(auth_service.require_user)):
    ok = idea_service.delete_atom(_user["id"], atom_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Atom not found or permission denied")
    return {"ok": True}


@router.delete("/atoms/paper/{paper_id}", summary="Delete atoms for a paper")
def api_idea_delete_atoms_for_paper(paper_id: str, _user=Depends(auth_service.require_user)):
    count = idea_service.delete_atoms_for_paper(_user["id"], paper_id)
    return {"ok": True, "deleted": count}


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

@router.get("/questions", summary="List generated questions")
def api_idea_list_questions(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _user=Depends(auth_service.require_user),
):
    questions = idea_service.list_questions(_user["id"], limit=limit, offset=offset)
    return {"ok": True, "questions": questions, "count": len(questions)}


@router.post("/questions/generate", summary="Generate research questions from atoms")
def api_idea_generate_questions(body: GenerateQuestionsBody, _user=Depends(auth_service.require_user)):
    result = idea_pipeline_service.generate_questions(_user["id"], limit=body.limit)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"ok": True, **result}


# ---------------------------------------------------------------------------
# Idea digest (permission-filtered, date-scoped)
# ---------------------------------------------------------------------------

@router.get("/digest/{date}", summary="Idea digest for a date (permission-filtered)")
def api_idea_digest(
    date: str,
    _user=Depends(auth_service.require_user),
):
    uid = _user.get("id", 0) if _user else 0
    digest = data_service.get_daily_digest(date, user_id=uid)
    all_papers = digest.get("papers", [])

    quota_limit = _tier_quota_limit(_user)
    if quota_limit is not None:
        visible_papers = all_papers[:quota_limit]
    else:
        visible_papers = all_papers
    allowed_paper_ids = [p["paper_id"] for p in visible_papers if p.get("paper_id")]

    candidates, total_available = idea_service.list_shared_candidates_for_date(
        date_str=date,
        allowed_paper_ids=allowed_paper_ids,
        viewer_user_id=_user["id"],
    )

    return {
        "ok": True,
        "candidates": candidates,
        "total_available": total_available,
        "quota_limit": quota_limit,
        "tier": _tier_label(_user),
    }


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------

@router.get("/candidates", summary="List inspiration candidates")
def api_idea_list_candidates(
    status: Optional[str] = None,
    folder_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _user=Depends(auth_service.require_user),
):
    candidates = idea_service.list_candidates(
        _user["id"], status=status, folder_id=folder_id, limit=limit, offset=offset,
    )
    return {"ok": True, "candidates": candidates, "count": len(candidates)}


@router.get("/candidates/{candidate_id}", summary="Get candidate detail")
def api_idea_get_candidate(candidate_id: int, _user=Depends(auth_service.require_user)):
    c = idea_service.get_candidate(candidate_id)
    if not c or c.get("user_id") != _user["id"]:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"ok": True, "candidate": c}


@router.post("/candidates", summary="Create candidate manually")
def api_idea_create_candidate(body: CreateCandidateBody, _user=Depends(auth_service.require_user)):
    c = idea_service.create_candidate(
        user_id=_user["id"],
        title=body.title,
        goal=body.goal,
        mechanism=body.mechanism,
        risks=body.risks,
        strategy=body.strategy,
        question_id=body.question_id,
        tags=body.tags,
        folder_id=body.folder_id,
    )
    return {"ok": True, "candidate": c}


@router.patch("/candidates/{candidate_id}", summary="Update candidate")
def api_idea_update_candidate(candidate_id: int, body: UpdateCandidateBody, _user=Depends(auth_service.require_user)):
    updates = body.dict(exclude_unset=True)
    c = idea_service.update_candidate(candidate_id, _user["id"], **updates)
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"ok": True, "candidate": c}


@router.delete("/candidates/{candidate_id}", summary="Delete candidate")
def api_idea_delete_candidate(candidate_id: int, _user=Depends(auth_service.require_user)):
    ok = idea_service.delete_candidate(_user["id"], candidate_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"ok": True}


@router.post("/candidates/{candidate_id}/review", summary="Submit manual review for a candidate")
def api_idea_manual_review(candidate_id: int, body: ManualReviewBody, _user=Depends(auth_service.require_user)):
    c = idea_service.get_candidate(candidate_id)
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")

    status_map = {"approve": "approved", "reject": "archived", "revise": "review"}
    new_status = status_map.get(body.action, "review")

    revision_entry = {
        "type": "manual_review",
        "action": body.action,
        "verdict": body.action,
        "feedback": body.feedback or "",
        "scores": body.scores or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    update_kwargs: dict = {
        "status": new_status,
        "revision_entry": revision_entry,
    }
    if body.scores:
        update_kwargs["scores"] = body.scores

    updated = idea_service.update_candidate(candidate_id, _user["id"], **update_kwargs)
    if not updated:
        raise HTTPException(status_code=404, detail="Candidate not found or permission denied")
    return {"ok": True, "message": "评审已提交", "candidate": updated}


@router.post("/candidates/generate", summary="Generate candidates (SSE stream)")
def api_idea_generate_candidates(body: GenerateCandidatesBody, _user=Depends(auth_service.require_user)):
    return StreamingResponse(
        idea_pipeline_service.stream_generate_candidates(
            _user["id"],
            question_id=body.question_id,
            custom_question=body.custom_question,
            strategies=body.strategies,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/candidates/generate-for-paper", summary="Generate candidates for a user paper")
def api_idea_generate_candidates_for_paper(body: GenerateForPaperBody, _user=Depends(auth_service.require_user)):
    result = idea_pipeline_service.generate_candidates_for_paper(_user["id"], body.paper_id, force=body.force)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@router.patch("/candidates/move", summary="Move candidates to folder")
def api_idea_move_candidates(body: MoveIdeaCandidatesBody, _user=Depends(auth_service.require_user)):
    count = 0
    for cid in body.candidate_ids:
        result = idea_service.update_candidate(cid, _user["id"], folder_id=body.target_folder_id)
        if result:
            count += 1
    return {"ok": True, "moved": count}


# ---------------------------------------------------------------------------
# Review & Revise (SSE)
# ---------------------------------------------------------------------------

@router.post("/review", summary="Review candidate (SSE stream)")
def api_idea_review_candidate(body: ReviewCandidateBody, _user=Depends(auth_service.require_user)):
    return StreamingResponse(
        idea_pipeline_service.stream_review_candidate(_user["id"], body.candidate_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/revise", summary="Revise candidate (SSE stream)")
def api_idea_revise_candidate(body: ReviseCandidateBody, _user=Depends(auth_service.require_user)):
    return StreamingResponse(
        idea_pipeline_service.stream_revise_candidate(
            _user["id"], body.candidate_id, body.review_feedback,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

@router.post("/plans/generate", summary="Generate execution plan (SSE stream)")
def api_idea_generate_plan(body: GeneratePlanBody, _user=Depends(auth_service.require_user)):
    return StreamingResponse(
        idea_pipeline_service.stream_generate_plan(_user["id"], body.candidate_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/plans", summary="Save execution plan")
def api_idea_save_plan(body: SavePlanBody, _user=Depends(auth_service.require_user)):
    plan = idea_service.create_plan(
        user_id=_user["id"],
        candidate_id=body.candidate_id,
        milestones=body.milestones,
        metrics=body.metrics,
        datasets=body.datasets,
        ablation=body.ablation,
        cost=body.cost,
        timeline=body.timeline,
        full_plan=body.full_plan,
    )
    return {"ok": True, "plan": plan}


@router.get("/plans/{candidate_id}", summary="Get plan for candidate")
def api_idea_get_plan(candidate_id: int, _user=Depends(auth_service.require_user)):
    plan = idea_service.get_plan_for_candidate(_user["id"], candidate_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"ok": True, "plan": plan}


@router.patch("/plans/{plan_id}", summary="Update plan")
def api_idea_update_plan(plan_id: int, body: UpdatePlanBody, _user=Depends(auth_service.require_user)):
    updates = body.dict(exclude_unset=True)
    p = idea_service.update_plan(_user["id"], plan_id, **updates)
    if not p:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"ok": True, "plan": p}


@router.delete("/plans/{plan_id}", summary="Delete plan")
def api_idea_delete_plan(plan_id: int, _user=Depends(auth_service.require_user)):
    ok = idea_service.delete_plan(_user["id"], plan_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

@router.post("/feedback", summary="Record user feedback")
def api_idea_feedback(body: FeedbackBody, _user=Depends(auth_service.require_user)):
    fb = idea_service.create_feedback(
        user_id=_user["id"],
        candidate_id=body.candidate_id,
        action=body.resolved_action,
        context=body.context,
    )
    return {"ok": True, "feedback": fb}


@router.get("/feedback", summary="List feedback events")
def api_idea_list_feedback(
    candidate_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    _user=Depends(auth_service.require_user),
):
    events = idea_service.list_feedback(_user["id"], candidate_id=candidate_id, limit=limit)
    return {"ok": True, "events": events, "count": len(events)}


# ---------------------------------------------------------------------------
# Exemplars
# ---------------------------------------------------------------------------

@router.get("/exemplars", summary="List exemplars")
def api_idea_list_exemplars(
    limit: int = Query(100, ge=1, le=500),
    _user=Depends(auth_service.require_user),
):
    exemplars = idea_service.list_exemplars(_user["id"], limit=limit)
    return {"ok": True, "exemplars": exemplars}


@router.post("/exemplars", summary="Create exemplar")
def api_idea_create_exemplar(body: CreateExemplarBody, _user=Depends(auth_service.require_user)):
    ex = idea_service.create_exemplar(
        user_id=_user["id"],
        candidate_id=body.candidate_id,
        pattern=body.pattern,
        score=body.score,
        notes=body.notes,
    )
    return {"ok": True, "exemplar": ex}


@router.get("/exemplars/{exemplar_id}", summary="Get exemplar")
def api_idea_get_exemplar(exemplar_id: int, _user=Depends(auth_service.require_user)):
    ex = idea_service.get_exemplar(exemplar_id)
    if not ex:
        raise HTTPException(status_code=404, detail="Exemplar not found")
    return {"ok": True, "exemplar": ex}


@router.patch("/exemplars/{exemplar_id}", summary="Update exemplar")
def api_idea_update_exemplar(exemplar_id: int, body: UpdateExemplarBody, _user=Depends(auth_service.require_user)):
    updates = body.dict(exclude_unset=True)
    ex = idea_service.update_exemplar(_user["id"], exemplar_id, **updates)
    if not ex:
        raise HTTPException(status_code=404, detail="Exemplar not found")
    return {"ok": True, "exemplar": ex}


@router.delete("/exemplars/{exemplar_id}", summary="Delete exemplar")
def api_idea_delete_exemplar(exemplar_id: int, _user=Depends(auth_service.require_user)):
    ok = idea_service.delete_exemplar(_user["id"], exemplar_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Exemplar not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Prompt versions
# ---------------------------------------------------------------------------

@router.get("/prompt-versions", summary="List prompt versions")
def api_idea_list_prompt_versions(
    stage: Optional[str] = None,
    _user=Depends(auth_service.require_user),
):
    versions = idea_service.list_prompt_versions(_user["id"], stage=stage)
    return {"ok": True, "versions": versions}


@router.post("/prompt-versions", summary="Create prompt version")
def api_idea_create_prompt_version(body: CreatePromptVersionBody, _user=Depends(auth_service.require_user)):
    v = idea_service.create_prompt_version(
        user_id=_user["id"],
        stage=body.stage,
        prompt_text=body.prompt_text,
        metrics=body.metrics,
    )
    return {"ok": True, "version": v}


@router.get("/prompt-versions/{version_id}", summary="Get prompt version")
def api_idea_get_prompt_version(version_id: int, _user=Depends(auth_service.require_user)):
    v = idea_service.get_prompt_version(version_id)
    if not v:
        raise HTTPException(status_code=404, detail="Prompt version not found")
    return {"ok": True, "version": v}


@router.patch("/prompt-versions/{version_id}", summary="Update prompt version")
def api_idea_update_prompt_version(version_id: int, body: UpdatePromptVersionBody, _user=Depends(auth_service.require_user)):
    updates = body.dict(exclude_unset=True)
    v = idea_service.update_prompt_version(_user["id"], version_id, **updates)
    if not v:
        raise HTTPException(status_code=404, detail="Prompt version not found")
    return {"ok": True, "version": v}


@router.delete("/prompt-versions/{version_id}", summary="Delete prompt version")
def api_idea_delete_prompt_version(version_id: int, _user=Depends(auth_service.require_user)):
    ok = idea_service.delete_prompt_version(_user["id"], version_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Prompt version not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Benchmarks & eval replay
# ---------------------------------------------------------------------------

@router.get("/benchmarks", summary="List benchmarks")
def api_idea_list_benchmarks(_user=Depends(auth_service.require_user)):
    benchmarks = idea_service.list_benchmarks(_user["id"])
    return {"ok": True, "benchmarks": benchmarks}


@router.post("/benchmarks", summary="Create benchmark")
def api_idea_create_benchmark(body: CreateBenchmarkBody, _user=Depends(auth_service.require_user)):
    bm = idea_service.create_benchmark(
        user_id=_user["id"],
        name=body.name,
        question_ids=body.question_ids,
        model_version=body.model_version,
    )
    return {"ok": True, "benchmark": bm}


@router.get("/benchmarks/{benchmark_id}", summary="Get benchmark")
def api_idea_get_benchmark(benchmark_id: int, _user=Depends(auth_service.require_user)):
    bm = idea_service.get_benchmark(benchmark_id)
    if not bm:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    return {"ok": True, "benchmark": bm}


@router.patch("/benchmarks/{benchmark_id}", summary="Update benchmark")
def api_idea_update_benchmark(benchmark_id: int, body: UpdateBenchmarkBody, _user=Depends(auth_service.require_user)):
    updates = body.dict(exclude_unset=True)
    bm = idea_service.update_benchmark(_user["id"], benchmark_id, **updates)
    if not bm:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    return {"ok": True, "benchmark": bm}


@router.delete("/benchmarks/{benchmark_id}", summary="Delete a benchmark")
def api_idea_delete_benchmark(benchmark_id: int, _user=Depends(auth_service.require_user)):
    ok = idea_service.delete_benchmark(_user["id"], benchmark_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Benchmark not found or permission denied")
    return {"ok": True}


@router.post("/eval-replay", summary="Eval replay (SSE stream)")
def api_idea_eval_replay(body: EvalReplayBody, _user=Depends(auth_service.require_user)):
    return StreamingResponse(
        idea_pipeline_service.stream_eval_replay(_user["id"], body.question_ids),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Idea library (folders, reuses KB folder logic with scope='idea_library')
# ---------------------------------------------------------------------------

@router.get("/library/tree", summary="Get idea library tree")
def api_idea_library_tree(_user=Depends(auth_service.require_user)):
    folders = kb_service.get_tree(_user["id"], scope="idea_library")
    candidates = idea_service.list_candidates(_user["id"], limit=500)
    return {"ok": True, "folders": folders, "candidates": candidates}


@router.post("/library/folders", summary="Create idea library folder")
def api_idea_library_create_folder(body: CreateIdeaFolderBody, _user=Depends(auth_service.require_user)):
    folder = kb_service.create_folder(_user["id"], body.name, body.parent_id, scope="idea_library")
    return folder
