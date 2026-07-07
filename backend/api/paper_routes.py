"""科研论文助读 API 路由。

流程：
- POST /api/paper/search       搜索论文（LLM 生成推荐列表：标题/摘要/arXiv ID/链接）
- POST /api/paper/download     从 arXiv 下载 PDF，返回 file_id（后端自动完成）
- POST /api/paper/upload       手动上传 PDF（备用）
- POST /api/paper/translate    翻译段落（SSE 流式）
- POST /api/paper/summarize    总结段落（SSE 流式）
- POST /api/paper/explain      解释术语/公式（SSE 流式）
- POST /api/paper/analyze      全文分析（SSE 流式）
- POST /api/paper/full-translate 全文翻译（SSE 流式）
- POST /api/paper/terms        提取术语（SSE 流式）
- POST /api/paper/qa           论文问答（SSE 流式）
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse

from config import settings
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

UPLOAD_DIR = Path("./uploads/papers")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_paper_cache: dict[str, dict] = {}


def _extract_text_from_pdf(pdf_path: str) -> str:
    """用 pymupdf 提取 PDF 全文文本。"""
    try:
        import fitz
    except ImportError:
        return ""
    doc = fitz.open(pdf_path)
    texts = []
    for page in doc:
        texts.append(page.get_text())
    doc.close()
    return "\n\n".join(texts)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ============ 论文搜索 ============

PAPER_SEARCH_PROMPT = """你是学术论文推荐助手。根据用户的自然语言需求推荐论文。

## 核心原则：完全尊重用户的所有需求
用户可能提出各种约束条件，你都必须严格遵守：
- 数量："2篇"就推荐2篇，"5篇"就5篇，没说默认3篇
- 年份："近5年"→ 2021年及之后；"近3年"→ 2023年及之后；"2023年以后"→ 2023年
- 作者："作者是Yann LeCun"→ 只推荐该作者参与的论文
- 机构："Google/DeepMind发的"→ 只推荐该机构的论文
- 领域/方法："关于扩散模型"→ 只推荐该方向的论文
- 类型："综述论文"→ 只推荐 survey/review 类型
- 任何其他约束条件都要遵守

如果约束太多导致找不到足够论文，宁少不多，不要凑数。不确定真实存在的论文不要编造。

## 输出格式（严格 JSON）
{
  "papers": [
    {
      "title": "论文英文标题",
      "arxiv_id": "1706.03762",
      "authors": "作者1, 作者2",
      "year": 2017,
      "abstract_zh": "中文摘要（100-150字）",
      "key_contribution": "一句话说明主要贡献",
      "citations": "引用数（如不知道写'高引用'）"
    }
  ]
}"""


@router.post("/search")
async def search_papers(
    topic: str = Form(...),
    user_message: str = Form(""),
) -> dict:
    """搜索论文：LLM 根据用户完整需求生成推荐列表。"""
    if not settings.llm_ready:
        return {"error": "系统需要申请大模型 API，暂未接入"}

    # 优先用用户原始消息（包含"2篇""近5年"等约束），没有则用 topic
    query = user_message.strip() if user_message.strip() else f"帮我找关于{topic}的论文"

    messages = [
        {"role": "system", "content": PAPER_SEARCH_PROMPT},
        {"role": "user", "content": query},
    ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.llm_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.llm_model,
                "messages": messages,
                "max_tokens": 2000,
                "temperature": 0.7,
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

    # 从 LLM 输出中提取 JSON
    content = content.strip()
    content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return {"error": "解析论文列表失败，请重试"}
        else:
            return {"error": "解析论文列表失败，请重试"}

    papers = data.get("papers", [])
    # 给每篇论文加上完整的 arXiv 链接
    for p in papers:
        arxiv_id = p.get("arxiv_id", "")
        if arxiv_id:
            p["arxiv_url"] = f"https://arxiv.org/abs/{arxiv_id}"
            p["pdf_url"] = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    return {"papers": papers, "topic": topic}


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
            file_id = uuid.uuid4().hex[:16]
            file_path = UPLOAD_DIR / f"{file_id}_{safe_title}.pdf"
            file_path.write_bytes(pdf_bytes)

            # 提取全文文本
            full_text = _extract_text_from_pdf(str(file_path))
            if not full_text:
                return {"error": "PDF 下载成功但无法提取文本，可能是扫描件"}

            _paper_cache[file_id] = {
                "path": str(file_path),
                "filename": f"{safe_title}.pdf",
                "arxiv_id": arxiv_id,
                "title": title,
                "full_text": full_text,
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
    paper = _paper_cache.get(file_id)
    if not paper:
        return {"error": "文件不存在"}

    from database.connection import get_db

    db = await get_db()
    import time
    paper_id = uuid.uuid4().hex[:12]
    await db.execute(
        "INSERT INTO papers (id, session_id, file_id, title, arxiv_id, filename, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (paper_id, session_id, file_id, title, arxiv_id, paper.get("filename", ""), time.time()),
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
        (session_id,),
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
    await db.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
    await db.commit()
    return {"ok": True}


# ============ 手动上传（备用） ============

@router.post("/upload")
async def upload_paper(file: UploadFile = File(...)) -> dict:
    """手动上传 PDF 文件（备用方案）。"""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return {"error": "请上传 PDF 文件"}

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        return {"error": "文件过大，请上传 50MB 以下的 PDF"}

    file_id = uuid.uuid4().hex[:16]
    file_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
    file_path.write_bytes(content)

    full_text = _extract_text_from_pdf(str(file_path))
    if not full_text:
        return {"error": "无法提取 PDF 文本，可能是扫描件或加密文件"}

    _paper_cache[file_id] = {
        "path": str(file_path),
        "filename": file.filename,
        "full_text": full_text,
    }

    return {
        "file_id": file_id,
        "filename": file.filename,
        "full_text": full_text[:500] + "..." if len(full_text) > 500 else full_text,
        "total_chars": len(full_text),
    }


@router.get("/file/{file_id}")
async def get_paper_file(file_id: str):
    """返回 PDF 文件内容（供前端 pdf.js 渲染）。"""
    paper = _paper_cache.get(file_id)
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
    if not settings.llm_ready:
        yield _sse({"error": "系统需要申请大模型 API，暂未接入"})
        return

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{settings.llm_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={
                    "model": settings.llm_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.6,
                    "stream": True,
                },
            ) as resp:
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
    except httpx.HTTPStatusError as e:
        yield _sse({"error": f"LLM API 错误: {e.response.status_code}"})
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
    paper = _paper_cache.get(file_id)
    if not paper:
        return {"error": "文件不存在，请重新下载"}
    return StreamingResponse(
        _stream_llm(PAPER_FULL_ANALYSIS_PROMPT, paper["full_text"][:60000], session_id, max_tokens=3000),
        media_type="text/event-stream",
    )

@router.post("/full-translate")
async def full_translate(file_id: str = Form(...), session_id: str = Form("paper")):
    paper = _paper_cache.get(file_id)
    if not paper:
        return {"error": "文件不存在，请重新下载"}
    return StreamingResponse(
        _stream_llm(PAPER_TRANSLATE_PROMPT, paper["full_text"][:60000], session_id, max_tokens=4000),
        media_type="text/event-stream",
    )

@router.post("/terms")
async def extract_terms(file_id: str = Form(...), session_id: str = Form("paper")):
    paper = _paper_cache.get(file_id)
    if not paper:
        return {"error": "文件不存在，请重新下载"}
    return StreamingResponse(
        _stream_llm(PAPER_EXTRACT_TERMS_PROMPT, paper["full_text"][:40000], session_id, max_tokens=1500),
        media_type="text/event-stream",
    )

@router.post("/qa")
async def paper_qa(file_id: str = Form(...), question: str = Form(...), session_id: str = Form("paper")):
    paper = _paper_cache.get(file_id)
    if not paper:
        return {"error": "文件不存在，请重新下载"}

    full_text = paper["full_text"][:50000]
    messages = [
        {"role": "system", "content": PAPER_QA_PROMPT + f"\n\n【论文文本（可能截断）】：\n{full_text}"},
        {"role": "user", "content": question},
    ]

    async def qa_stream():
        if not settings.llm_ready:
            yield _sse({"error": "系统需要申请大模型 API，暂未接入"})
            return
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{settings.llm_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json={
                        "model": settings.llm_model,
                        "messages": messages,
                        "max_tokens": 2000,
                        "temperature": 0.6,
                        "stream": True,
                    },
                ) as resp:
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
        except Exception as e:
            yield _sse({"error": f"请求失败: {type(e).__name__}: {e}"})

    return StreamingResponse(qa_stream(), media_type="text/event-stream")
