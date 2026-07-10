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
from pathlib import Path

import httpx
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse

from config import settings
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

PAPER_SEARCH_PROMPT = """你是学术论文搜索助手。根据用户的自然语言需求，构建 arXiv 搜索查询。

## 你的任务：
分析用户需求，提取搜索参数，输出 JSON 供系统调用 arXiv API。

## 参数说明：
- query: arXiv 查询字符串
- max_results: 数量（用户说"2篇"就2，没说默认5）
- year_from: 起始年份（"近5年"→2021，"近3年"→2023，没说填 null）

## arXiv 查询语法（极其重要）：
- 关键词: "diffusion model"
- 作者搜索（用引号包裹全名）: au:"Yungang Zhu"
- 单姓搜索: au:LeCun
- 组合: au:"Yungang Zhu" AND cat:cs
- 标题: ti:attention
- 中文人名转拼音: "朱允刚" → Yungang Zhu，搜索时用 au:"Yungang Zhu"

## 重要规则：
1. 作者全名必须用双引号包裹：au:"Yungang Zhu"（不是 au:Yungang Zhu）
2. 中文人名转拼音：朱允刚 → Yungang Zhu
3. 中文关键词转英文：扩散模型 → diffusion model
4. 不要添加机构/学校作为搜索条件（arXiv 不索引学校信息）
5. 简单优先：如果用户只指定作者，query 就只有 au:"名字"

## 输出格式（严格 JSON）：
{"query": "au:\"Yungang Zhu\"", "max_results": 5, "year_from": null}

示例：
用户"找朱允刚老师的论文" → {"query": "au:\"Yungang Zhu\"", "max_results": 5, "year_from": null}
用户"2篇近3年扩散模型论文" → {"query": "diffusion model", "max_results": 2, "year_from": 2023}
用户"LeCun关于自监督学习" → {"query": "au:LeCun AND self-supervised", "max_results": 5, "year_from": null}"""


async def _parse_search_params(user_message: str) -> dict:
    """用 DeepSeek 解析用户需求为 arXiv 搜索参数。"""
    if not settings.deepseek_ready:
        return {"query": user_message, "max_results": 5, "year_from": None}

    messages = [
        {"role": "system", "content": PAPER_SEARCH_PROMPT},
        {"role": "user", "content": user_message},
    ]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.deepseek_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                json={
                    "model": settings.deepseek_model,
                    "messages": messages,
                    "max_tokens": 200,
                    "temperature": 0.3,
                },
            )
            _check_quota_error(resp.status_code, resp.text, "DeepSeek")
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()
            return json.loads(content)
    except Exception as e:
        print(f"[paper_search] DeepSeek parse failed: {e}")
        return {"query": user_message, "max_results": 5, "year_from": None}


@router.post("/search")
async def search_papers(
    topic: str = Form(...),
    user_message: str = Form(""),
) -> dict:
    """搜索论文：LLM 解析需求 → arXiv API 真实搜索 → LLM 翻译摘要。"""
    query_text = user_message.strip() if user_message.strip() else f"帮我找关于{topic}的论文"

    # 1. LLM 解析搜索参数
    params = await _parse_search_params(query_text)
    arxiv_query = params.get("query", topic)
    max_results = min(params.get("max_results", 5) or 5, 10)
    year_from = params.get("year_from")

    # 2. 调用 arXiv API 真实搜索
    try:
        import arxiv as arxiv_lib

        sort_by = arxiv_lib.SortCriterion.Relevance
        search = arxiv_lib.Search(
            query=arxiv_query,
            max_results=max_results * 2,  # 多搜一些，后面按年份过滤
            sort_by=sort_by,
        )
        raw_results = list(arxiv_lib.Client().results(search))
    except Exception as e:
        return {"error": f"arXiv 搜索失败：{type(e).__name__}: {e}"}

    # 3. 过滤 + 格式化
    papers = []
    for r in raw_results:
        # 年份过滤
        if year_from and r.published.year < year_from:
            continue
        arxiv_id = r.entry_id.split("/")[-1].split("v")[0]
        papers.append({
            "title": r.title.replace("\n", " ").strip(),
            "arxiv_id": arxiv_id,
            "authors": ", ".join(a.name for a in r.authors[:6]),
            "year": r.published.year,
            "abstract_zh": r.summary[:200].replace("\n", " "),  # 先用英文摘要，后面 LLM 翻译
            "key_contribution": "",
            "citations": "",
            "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        })
        if len(papers) >= max_results:
            break

    # 4. DeepSeek 翻译摘要为中文（批量）
    if papers and settings.deepseek_ready:
        try:
            paper_list = "\n".join(
                f"[{i}] {p['title']}\n{p['abstract_zh']}"
                for i, p in enumerate(papers)
            )
            messages = [
                {"role": "system", "content": "你是学术翻译。将每篇论文的摘要翻译成中文（100字以内），并概括其核心贡献。输出 JSON 数组，每项格式 {\"index\": 0, \"abstract_zh\": \"中文摘要\", \"key_contribution\": \"一句话贡献\"}"},
                {"role": "user", "content": paper_list},
            ]
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{settings.deepseek_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                    json={"model": settings.deepseek_model, "messages": messages, "max_tokens": 1500, "temperature": 0.5},
                )
                _check_quota_error(resp.status_code, resp.text, "DeepSeek")
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"].strip()
                content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()
                translations = json.loads(content)
                for t in translations:
                    idx = t.get("index", -1)
                    if 0 <= idx < len(papers):
                        papers[idx]["abstract_zh"] = t.get("abstract_zh", papers[idx]["abstract_zh"])
                        papers[idx]["key_contribution"] = t.get("key_contribution", "")
        except Exception as e:
            print(f"[paper_search] DeepSeek translate failed: {e}")

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
