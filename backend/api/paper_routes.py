"""科研论文助读 API 路由。

所有 LLM 调用（搜索参数解析、摘要翻译、段落翻译/总结/解释/分析/问答）
均使用 DeepSeek。混元仅负责对话回答。

流程：
- POST /api/paper/search       搜索论文（arXiv API + DeepSeek 翻译摘要）
- POST /api/paper/download     从 arXiv 下载 PDF，返回 file_id（后端自动完成）
- POST /api/paper/upload       手动上传 PDF（备用）
- POST /api/paper/translate    翻译段落（SSE 流式，DeepSeek）
- POST /api/paper/summarize    总结段落（SSE 流式，DeepSeek）
- POST /api/paper/explain      解释术语/公式（SSE 流式，DeepSeek）
- POST /api/paper/analyze      全文分析（SSE 流式，DeepSeek）
- POST /api/paper/full-translate 全文翻译（SSE 流式，DeepSeek）
- POST /api/paper/terms        提取术语（SSE 流式，DeepSeek）
- POST /api/paper/qa           论文问答（SSE 流式，DeepSeek）
"""
from __future__ import annotations

import json
import re
import uuid

import httpx
from fastapi import APIRouter, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse, FileResponse

from config import settings
from database.repositories.conversation_repo import DEFAULT_CONVERSATION_ID, LOCAL_USER_ID
from database.repositories.file_repo import get_file
from services.file_service import store_pdf
from services.hunyuan_service import _check_quota_error, QuotaExhaustedError
from prompts.paper_prompts import (
    PAPER_TRANSLATE_PROMPT,
    PAPER_SUMMARIZE_PROMPT,
    PAPER_EXPLAIN_PROMPT,
    PAPER_FORMULA_PROMPT,
    PAPER_FULL_ANALYSIS_PROMPT,
    PAPER_EXTRACT_TERMS_PROMPT,
    PAPER_QA_PROMPT,
)

router = APIRouter(prefix="/api/paper", tags=["paper"])

_paper_cache: dict[str, dict] = {}


async def _get_paper(file_id: str) -> dict | None:
    cached = _paper_cache.get(file_id)
    if cached:
        return cached
    stored = await get_file(file_id)
    if not stored:
        return None
    metadata = stored.get("metadata") or {}
    paper = {
        "path": stored["storage_path"],
        "filename": stored["original_name"],
        "arxiv_id": metadata.get("arxiv_id", ""),
        "title": metadata.get("title", stored["original_name"]),
        "full_text": stored.get("extracted_text", ""),
    }
    _paper_cache[file_id] = paper
    return paper


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ============ 论文搜索 ============

@router.post("/search")
async def search_papers(
    request: Request,
    topic: str = Form(...),
    user_message: str = Form(""),
) -> dict:
    """Search arXiv through the shared paper service and ModelGateway."""
    from services.paper_search_service import PaperSearchService

    service = PaperSearchService(request.app.state.model_gateway)
    try:
        return await service.search(topic=topic, user_message=user_message)
    except Exception as error:
        return {"error": f"arXiv 搜索失败：{type(error).__name__}: {error}"}


# ============ 论文下载 ============

@router.post("/download")
async def download_paper(
    arxiv_id: str = Form(...),
    title: str = Form(""),
) -> dict:
    """从 arXiv 下载 PDF，提取全文，返回 file_id。

    前端拿到 file_id 后可直接打开 PaperReader。
    """
    arxiv_id = arxiv_id.strip()
    if not arxiv_id:
        return {"error": "请提供 arXiv ID"}

    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                return {"error": f"下载失败：arXiv 返回 {resp.status_code}"}

            pdf_bytes = resp.content
            if len(pdf_bytes) < 1000:
                return {"error": "下载的文件太小，可能不是有效 PDF"}

            # 安全标题
            safe_title = re.sub(r'[^\w\s\-]', '', title)[:60] or arxiv_id
            stored = await store_pdf(
                pdf_bytes,
                f"{safe_title}.pdf",
                DEFAULT_CONVERSATION_ID,
                {"source": "arxiv", "arxiv_id": arxiv_id, "title": title},
            )
            file_id = stored["id"]
            full_text = stored["extracted_text"]
            _paper_cache[file_id] = {
                "path": stored["storage_path"], "filename": stored["original_name"],
                "arxiv_id": arxiv_id, "title": title, "full_text": full_text,
            }

            return {
                "file_id": file_id,
                "filename": f"{safe_title}.pdf",
                "title": title,
                "arxiv_id": arxiv_id,
                "total_chars": len(full_text),
                "preview": full_text[:300] + "..." if len(full_text) > 300 else full_text,
            }

    except httpx.TimeoutException:
        return {"error": "下载超时，请重试"}
    except Exception as e:
        return {"error": f"下载失败：{type(e).__name__}: {e}"}


# ============ 我的阅读（保存/列表/删除） ============

@router.post("/save")
async def save_paper(
    file_id: str = Form(...),
    title: str = Form(""),
    arxiv_id: str = Form(""),
    session_id: str = Form("default"),
) -> dict:
    """将已下载的论文保存到「我的阅读」。"""
    paper = await _get_paper(file_id)
    if not paper:
        return {"error": "文件不存在"}

    from database.connection import get_db

    db = await get_db()
    import time
    paper_id = uuid.uuid4().hex[:12]
    await db.execute(
        "INSERT INTO papers (id, session_id, file_id, title, arxiv_id, filename, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (paper_id, LOCAL_USER_ID, file_id, title, arxiv_id, paper.get("filename", ""), time.time()),
    )
    await db.commit()
    return {"ok": True, "paper_id": paper_id}


@router.get("/saved/{session_id}")
async def list_saved_papers(session_id: str) -> dict:
    """列出「我的阅读」中的论文。"""
    from database.connection import get_db

    db = await get_db()
    cursor = await db.execute(
        "SELECT id, file_id, title, arxiv_id, filename, created_at FROM papers WHERE session_id = ? ORDER BY created_at DESC",
        (LOCAL_USER_ID,),
    )
    rows = await cursor.fetchall()
    papers = []
    for r in rows:
        papers.append({
            "id": r[0],
            "file_id": r[1],
            "title": r[2],
            "arxiv_id": r[3],
            "filename": r[4],
            "created_at": r[5],
        })
    return {"papers": papers}


@router.delete("/saved/{paper_id}")
async def delete_saved_paper(paper_id: str) -> dict:
    """从「我的阅读」中删除论文。"""
    from database.connection import get_db

    db = await get_db()
    await db.execute(
        "DELETE FROM papers WHERE id = ? AND session_id = ?",
        (paper_id, LOCAL_USER_ID),
    )
    await db.commit()
    return {"ok": True}


# ============ 手动上传（备用） ============

@router.post("/upload")
async def upload_paper(file: UploadFile = File(...)) -> dict:
    """手动上传 PDF 文件（备用方案）。"""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return {"error": "请上传 PDF 文件"}

    content = await file.read()
    try:
        stored = await store_pdf(content, file.filename, DEFAULT_CONVERSATION_ID)
    except ValueError as error:
        return {"error": str(error)}
    file_id = stored["id"]
    full_text = stored["extracted_text"]

    return {
        "file_id": file_id,
        "filename": file.filename,
        "full_text": full_text[:500] + "..." if len(full_text) > 500 else full_text,
        "total_chars": len(full_text),
    }


@router.get("/file/{file_id}")
async def get_paper_file(file_id: str):
    """返回 PDF 文件内容（供前端 pdf.js 渲染）。"""
    paper = await _get_paper(file_id)
    if not paper:
        return {"error": "文件不存在"}
    return FileResponse(paper["path"], media_type="application/pdf")


# ============ SSE 流式 LLM ============

async def _stream_llm(
    system_prompt: str,
    user_content: str,
    session_id: str = "paper",
    max_tokens: int = 2000,
):
    """流式 LLM 调用（DeepSeek）—— 用于论文翻译/总结/分析等附加功能。"""
    if not settings.deepseek_ready:
        yield _sse({"error": "系统需要配置 DeepSeek API，暂未接入"})
        return

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{settings.deepseek_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                json={
                    "model": settings.deepseek_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.6,
                    "stream": True,
                },
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    _check_quota_error(resp.status_code, body.decode("utf-8", errors="replace"), "DeepSeek")
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        text = delta.get("content", "")
                        if text:
                            yield _sse({"delta": text})
                    except (json.JSONDecodeError, IndexError):
                        continue
        yield _sse({"done": True})
    except QuotaExhaustedError as e:
        yield _sse({"error": str(e), "error_type": "quota_exhausted"})
    except httpx.HTTPStatusError as e:
        yield _sse({"error": f"DeepSeek API 错误: {e.response.status_code}"})
    except Exception as e:
        yield _sse({"error": f"请求失败: {type(e).__name__}: {e}"})


@router.post("/translate")
async def translate_paragraph(text: str = Form(...), session_id: str = Form("paper")):
    return StreamingResponse(
        _stream_llm(PAPER_TRANSLATE_PROMPT, text, session_id, max_tokens=1500),
        media_type="text/event-stream",
    )

@router.post("/summarize")
async def summarize_paragraph(text: str = Form(...), session_id: str = Form("paper")):
    return StreamingResponse(
        _stream_llm(PAPER_SUMMARIZE_PROMPT, text, session_id, max_tokens=800),
        media_type="text/event-stream",
    )

@router.post("/explain")
async def explain_term(text: str = Form(...), session_id: str = Form("paper")):
    return StreamingResponse(
        _stream_llm(PAPER_EXPLAIN_PROMPT, text, session_id, max_tokens=1000),
        media_type="text/event-stream",
    )

@router.post("/formula")
async def explain_formula(text: str = Form(...), session_id: str = Form("paper")):
    return StreamingResponse(
        _stream_llm(PAPER_FORMULA_PROMPT, text, session_id, max_tokens=1500),
        media_type="text/event-stream",
    )

@router.post("/analyze")
async def analyze_paper(file_id: str = Form(...), session_id: str = Form("paper")):
    paper = await _get_paper(file_id)
    if not paper:
        return {"error": "文件不存在，请重新下载"}
    return StreamingResponse(
        _stream_llm(PAPER_FULL_ANALYSIS_PROMPT, paper["full_text"][:60000], session_id, max_tokens=3000),
        media_type="text/event-stream",
    )

@router.post("/full-translate")
async def full_translate(file_id: str = Form(...), session_id: str = Form("paper")):
    paper = await _get_paper(file_id)
    if not paper:
        return {"error": "文件不存在，请重新下载"}
    return StreamingResponse(
        _stream_llm(PAPER_TRANSLATE_PROMPT, paper["full_text"][:60000], session_id, max_tokens=4000),
        media_type="text/event-stream",
    )

@router.post("/terms")
async def extract_terms(file_id: str = Form(...), session_id: str = Form("paper")):
    paper = await _get_paper(file_id)
    if not paper:
        return {"error": "文件不存在，请重新下载"}
    return StreamingResponse(
        _stream_llm(PAPER_EXTRACT_TERMS_PROMPT, paper["full_text"][:40000], session_id, max_tokens=1500),
        media_type="text/event-stream",
    )

@router.post("/qa")
async def paper_qa(file_id: str = Form(...), question: str = Form(...), session_id: str = Form("paper")):
    paper = await _get_paper(file_id)
    if not paper:
        return {"error": "文件不存在，请重新下载"}

    full_text = paper["full_text"][:50000]
    messages = [
        {"role": "system", "content": PAPER_QA_PROMPT + f"\n\n【论文文本（可能截断）】：\n{full_text}"},
        {"role": "user", "content": question},
    ]

    async def qa_stream():
        if not settings.deepseek_ready:
            yield _sse({"error": "系统需要配置 DeepSeek API，暂未接入"})
            return
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{settings.deepseek_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                    json={
                        "model": settings.deepseek_model,
                        "messages": messages,
                        "max_tokens": 2000,
                        "temperature": 0.6,
                        "stream": True,
                    },
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        _check_quota_error(resp.status_code, body.decode("utf-8", errors="replace"), "DeepSeek")
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            text = delta.get("content", "")
                            if text:
                                yield _sse({"delta": text})
                        except (json.JSONDecodeError, IndexError):
                            continue
            yield _sse({"done": True})
        except QuotaExhaustedError as e:
            yield _sse({"error": str(e), "error_type": "quota_exhausted"})
        except Exception as e:
            yield _sse({"error": f"请求失败: {type(e).__name__}: {e}"})

    return StreamingResponse(qa_stream(), media_type="text/event-stream")
