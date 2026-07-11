from fastapi import APIRouter, Depends, HTTPException, Request
from routes.dependencies import get_current_user
from pydantic import BaseModel
from typing import List, Dict, Any

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryQuery(BaseModel):
    conversation_id: str
    user_id: str


@router.post("/context")
async def get_context(req: MemoryQuery, user: dict = Depends(get_current_user)):
    from memory.manager import get_memory

    mem = get_memory()
    context = mem.get_context(req.conversation_id, req.user_id)
    return {"context": context, "conversation_id": req.conversation_id}


@router.get("/long-term/{user_id}")
async def get_long_term(user_id: str, user: dict = Depends(get_current_user)):
    from memory.manager import get_memory

    mem = get_memory()
    memory = mem._get_long_term_memory(user_id)
    return {"user_id": user_id, "long_term_memory": memory}


@router.post("/cleanup")
async def cleanup_memory(user: dict = Depends(get_current_user)):
    from memory.manager import get_memory

    mem = get_memory()
    mem.cleanup()
    return {"status": "success", "message": "记忆已清理"}
