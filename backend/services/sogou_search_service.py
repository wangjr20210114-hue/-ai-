"""搜狗多源搜索服务（免费，替代 WSA 为主搜索）。

搜索渠道：
1. 网页搜索 — 通用 web 结果
2. 微信文章 — 公众号文章 + gh_id + 头像
3. 知乎搜索 — 知乎问答
4. 百科搜索 — 搜狗百科摘要
"""
from __future__ import annotations

import asyncio
import html as html_mod
import json
import re
from typing import Any

import httpx

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def _clean(text: str) -> str:
    """去除 HTML 标签并反转义。"""
    text = re.sub(r"<[^>]+>", "", text)
    return html_mod.unescape(text).strip()


async def _resolve_sogou_link(sogou_url: str) -> str:
    """跟踪搜狗 /link?url=xxx 跳转链接，返回真实 URL。"""
    if not sogou_url or "/link" not in sogou_url:
        return sogou_url
    try:
        async with httpx.AsyncClient(
            timeout=8, headers=_HEADERS, follow_redirects=False
        ) as client:
            r = await client.get(sogou_url)
            text = r.text
            # 方式1: window.location.replace("url")
            m = re.search(r'window\.location\.replace\(\s*["\']([^"\']+)["\']', text)
            if m:
                return m.group(1)
            # 方式2: url += '...' (微信文章用)
            parts = re.findall(r"url \+= '([^']+)'", text)
            if parts:
                return "".join(parts).replace("@", "")
            # 方式3: meta refresh
            m = re.search(r"url=([^\"\'>\s]+)", text)
            if m:
                return m.group(1)
            # 方式4: 302 Location
            loc = r.headers.get("location", "")
            if loc and loc.startswith("http"):
                return loc
            return sogou_url
    except Exception:
        return sogou_url


async def _resolve_link_for_result(result: dict[str, Any]) -> None:
    """为搜索结果跟踪并更新真实 URL。"""
    real_url = await _resolve_sogou_link(result.get("url", ""))
    result["url"] = real_url
# ============================================================
async def search_web(query: str, cnt: int = 5, sort_by_time: bool = False) -> list[dict[str, Any]]:
    """搜狗网页搜索。

    Args:
        sort_by_time: 是否按时间排序（时效型查询用）
    """
    try:
        params = {"query": query}
        if sort_by_time:
            params["tsn"] = "1"  # 按时间排序
        async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as client:
            resp = await client.get(
                "https://www.sogou.com/web",
                params=params,
            )
            resp.raise_for_status()
            text = resp.text

        results: list[dict[str, Any]] = []
        # 匹配所有 h3 块内的 a 标签（支持多种格式：class=" " / name="dttl" 等）
        h3_blocks = re.findall(r"<h3[^>]*>(.*?)</h3>", text, re.DOTALL)
        titles = []
        raw_urls = []
        for block in h3_blocks:
            # 提取标题文本
            m_title = re.search(r"<a[^>]*>(.*?)</a>", block, re.DOTALL)
            m_url = re.search(r'href="([^"]*)"', block)
            if m_title:
                titles.append(m_title.group(1))
                raw_urls.append(m_url.group(1) if m_url else "")
        snippets = re.findall(r'class="fz-mid space-txt">(.*?)</p>', text, re.DOTALL)

        for i in range(min(cnt, len(titles))):
            title = _clean(titles[i])
            if not title:
                continue
            url = raw_urls[i] if i < len(raw_urls) else ""
            # 搜狗百科等直链直接使用
            if url.startswith("http") and "/link" not in url:
                pass
            elif url.startswith("/link"):
                url = f"https://www.sogou.com{url}"
            snippet = _clean(snippets[i]) if i < len(snippets) else ""
            results.append({
                "source": "web",
                "title": title,
                "url": url,
                "snippet": snippet[:200],
                "site": "",
            })

        # 异步跟踪跳转链接获取真实 URL
        tasks = [_resolve_link_for_result(r) for r in results if "/link" in r.get("url", "")]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        return results
    except Exception as e:
        print(f"[sogou_web] failed: {e}")
        return []


# ============================================================
# 2. 微信文章搜索
# ============================================================
async def search_wechat(
    query: str, cnt: int = 5, with_detail: bool = True
) -> list[dict[str, Any]]:
    """搜狗微信文章搜索 + 跟踪链接提取公众号详情。

    Returns:
        [{"source": "wechat", "title", "account_name", "gh_id",
          "avatar", "snippet", "article_url"}, ...]
    """
    try:
        async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as client:
            resp = await client.get(
                "https://weixin.sogou.com/weixin",
                params={"type": "2", "query": query, "ie": "utf8"},
            )
            resp.raise_for_status()
            text = resp.text

        results: list[dict[str, Any]] = []
        accounts = re.findall(
            r'<span class="all-time-y2">(.*?)</span>', text
        )
        titles_raw = re.findall(
            r'id="sogou_vr_11002601_title_\d+"[^>]*>(.*?)</a>', text, re.DOTALL
        )
        summaries = re.findall(
            r'id="sogou_vr_11002601_summary_\d+"[^>]*>(.*?)</p>', text, re.DOTALL
        )
        links = re.findall(r'href="(/link\?url=[^"]+)"', text)
        # 提取时间戳：timeConvert('xxx')
        timestamps = re.findall(r"timeConvert\('(\d+)'\)", text)

        for i in range(min(cnt, len(accounts))):
            title = _clean(titles_raw[i]) if i < len(titles_raw) else ""
            account = _clean(accounts[i])
            snippet = _clean(summaries[i])[:200] if i < len(summaries) else ""
            link = links[i] if i < len(links) else ""
            # 提取日期
            date_str = ""
            if i < len(timestamps):
                ts = int(timestamps[i])
                import datetime
                dt = datetime.datetime.fromtimestamp(ts)
                date_str = dt.strftime("%Y-%m-%d")
            results.append({
                "source": "wechat",
                "title": title,
                "account_name": account,
                "gh_id": "",
                "avatar": "",
                "snippet": snippet,
                "date": date_str,
                "article_url": f"https://weixin.sogou.com{link}" if link else "",
                "_sogou_link": f"https://weixin.sogou.com{link}" if link else "",
            })

        # 跟踪前 N 条链接提取 gh_id + 头像
        if with_detail:
            tasks = [_fetch_wechat_detail(r) for r in results[:cnt]]
            await asyncio.gather(*tasks, return_exceptions=True)

        # 过滤失效链接（公众号迁移/文章删除）
        results = [r for r in results if not r.get("_invalid")]

        return results
    except Exception as e:
        print(f"[sogou_wechat] failed: {e}")
        return []


async def _fetch_wechat_detail(result: dict[str, Any]) -> None:
    """跟踪搜狗加密链接 → 微信文章页 → 提取 gh_id + 头像。"""
    sogou_link = result.get("_sogou_link", "")
    if not sogou_link:
        return
    try:
        async with httpx.AsyncClient(
            timeout=10, headers=_HEADERS, follow_redirects=False
        ) as client:
            r = await client.get(sogou_link)
            # 从 JS 中拼接真实 URL
            parts = re.findall(r"url \+= '([^']+)'", r.text)
            if not parts:
                return
            mp_url = "".join(parts).replace("@", "")

            r2 = await client.get(mp_url)
            page = r2.text

            # 检测失效链接（公众号迁移/文章删除）
            if "此账号已迁移" in page or "该公众号已迁移" in page:
                result["_invalid"] = True
                return
            if "临时无法访问" in page or "该内容已被发布者删除" in page:
                result["_invalid"] = True
                return

            # 提取 gh_id
            gh_matches = re.findall(
                r'(?:user_name|userName|gh_id)\s*[=:]\s*[\'"]([^\'"]+)[\'"]',
                page, re.IGNORECASE,
            )
            for g in gh_matches:
                if g.startswith("gh_"):
                    result["gh_id"] = g
                    break

            # 提取公众号名（更准确）
            nick_matches = re.findall(
                r'(?:nickname|nick_name|nickName)\s*[=:]\s*[\'"]([^\'"]+)[\'"]',
                page, re.IGNORECASE,
            )
            if nick_matches:
                result["account_name"] = nick_matches[0]

            # 提取头像
            head_matches = re.findall(
                r'(?:head_img|headimg|avatar|round_head|headimage)\S*\s*[=:]\s*'
                r'[\'"](https?://[^\'"]+)[\'"]',
                page, re.IGNORECASE,
            )
            if head_matches:
                result["avatar"] = head_matches[0]

            # 真实文章 URL
            result["article_url"] = mp_url

            await asyncio.sleep(0.5)  # 礼貌延时
    except Exception as e:
        print(f"[wechat_detail] failed for {result.get('account_name', '?')}: {e}")


# ============================================================
# 3. 知乎搜索
# ============================================================
async def search_zhihu(query: str, cnt: int = 5) -> list[dict[str, Any]]:
    """搜狗知乎搜索（跟随重定向）。

    Returns:
        [{"source": "zhihu", "title", "url", "snippet"}, ...]
    """
    try:
        async with httpx.AsyncClient(
            timeout=15, headers=_HEADERS, follow_redirects=True
        ) as client:
            resp = await client.get(
                "https://zhihu.sogou.com/zhihu",
                params={"query": query},
            )
            resp.raise_for_status()
            text = resp.text

        results: list[dict[str, Any]] = []
        # 知乎标题在 <h3> 中
        h3_blocks = re.findall(r"<h3[^>]*>(.*?)</h3>", text, re.DOTALL)
        # 知乎链接
        zhihu_urls = re.findall(
            r'href="(https://www\.zhihu\.com/question/[^"]+)"', text
        )

        for i in range(min(cnt, len(h3_blocks))):
            title = _clean(h3_blocks[i])
            if not title or len(title) < 4:
                continue
            url = zhihu_urls[i] if i < len(zhihu_urls) else ""
            results.append({
                "source": "zhihu",
                "title": title,
                "url": url,
                "snippet": "",
            })
        return results[:cnt]
    except Exception as e:
        print(f"[sogou_zhihu] failed: {e}")
        return []


# ============================================================
# 4. 百科搜索
# ============================================================
async def search_baike(query: str) -> dict[str, Any] | None:
    """搜狗百科搜索（先从网页搜索结果中找百科链接，再抓取摘要）。

    Returns:
        {"source": "baike", "title", "url", "snippet", "image"} or None
    """
    try:
        # 先搜网页找到百科链接
        web_results = await search_web(query, cnt=10)
        baike_url = ""
        for r in web_results:
            url = r.get("url", "")
            title = r.get("title", "")
            if "baike.sogou.com" in url or "百科" in title:
                baike_url = url
                break

        if not baike_url:
            return None

        async with httpx.AsyncClient(
            timeout=15, headers=_HEADERS, follow_redirects=True
        ) as client:
            resp = await client.get(baike_url)
            if resp.status_code != 200:
                print(f"[sogou_baike] status={resp.status_code}")
                return None
            text = resp.text

        # 提取百科摘要
        summary = ""
        m = re.search(r'<div class="abstract"[^>]*>(.*?)</div>', text, re.DOTALL)
        if m:
            summary = _clean(m.group(1))[:300]
        if not summary:
            m = re.search(r'name="description" content="(.*?)"', text)
            if m:
                summary = _clean(m.group(1))[:300]
        if not summary:
            # 尝试从 meta 标签提取
            m = re.search(r'<meta[^>]*content="(.*?)"[^>]*name="description"', text)
            if m:
                summary = _clean(m.group(1))[:300]

        # 提取百科中的图片
        image = ""
        m = re.search(r'src="(https?://[^"]*\.(?:jpg|png|jpeg)[^"]*)"', text)
        if m:
            candidate = m.group(1)
            # 排除 logo、icon 等小图
            if "logo" not in candidate.lower() and "icon" not in candidate.lower():
                image = candidate

        # 提取标题
        title = ""
        m = re.search(r"<title>(.*?)</title>", text)
        if m:
            title = _clean(m.group(1)).split("-")[0].strip()

        if not summary:
            return None

        return {
            "source": "baike",
            "title": title or query,
            "url": baike_url,
            "snippet": summary,
            "image": image,
        }
    except Exception as e:
        print(f"[sogou_baike] failed: {type(e).__name__}: {e}")
        return None


# ============================================================
# 5. 聚合搜索
# ============================================================
async def search_all(query: str, cnt_per_source: int = 5) -> dict[str, Any]:
    """多源并行搜索，返回聚合结果。

    Returns:
        {
            "query": "...",
            "results": [...],          # 所有结果（已去重）
            "images": [...],           # 提取的图片URL
            "sources_used": ["web", "wechat", "zhihu", "baike"],
            "total": N,
        }
    """
    web_task = search_web(query, cnt=cnt_per_source)
    wechat_task = search_wechat(query, cnt=cnt_per_source)
    zhihu_task = search_zhihu(query, cnt=cnt_per_source)
    baike_task = search_baike(query)

    web_res, wechat_res, zhihu_res, baike_res = await asyncio.gather(
        web_task, wechat_task, zhihu_task, baike_task,
        return_exceptions=True,
    )

    results: list[dict[str, Any]] = []
    images: list[str] = []
    sources_used: list[str] = []

    if isinstance(web_res, list) and web_res:
        results.extend(web_res)
        sources_used.append("web")

    if isinstance(wechat_res, list) and wechat_res:
        results.extend(wechat_res)
        sources_used.append("wechat")
        # 提取微信头像
        for r in wechat_res:
            if r.get("avatar"):
                images.append(r["avatar"])

    if isinstance(zhihu_res, list) and zhihu_res:
        results.extend(zhihu_res)
        sources_used.append("zhihu")

    if isinstance(baike_res, dict) and baike_res:
        results.append(baike_res)
        sources_used.append("baike")
        if baike_res.get("image"):
            images.append(baike_res["image"])

    return {
        "query": query,
        "results": results,
        "images": images,
        "sources_used": sources_used,
        "total": len(results),
    }


# ============================================================
# 6. WSA 兜底搜索（搜狗失败时使用）
# ============================================================
async def wsa_search(query: str, cnt: int = 5) -> list[dict[str, Any]]:
    """WSA 联网搜索（兜底）。"""
    from config import settings

    if not settings.wsa_api_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{settings.wsa_base_url}/SearchPro",
                headers={
                    "Authorization": f"Bearer {settings.wsa_api_key}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json={"Query": query},
            )
            resp.raise_for_status()
            data = resp.json()
            response = data.get("Response", data)
            pages = response.get("Pages", [])

            results = []
            for p in pages[:cnt]:
                page = json.loads(p) if isinstance(p, str) else p
                results.append({
                    "source": "wsa",
                    "title": page.get("title", ""),
                    "url": page.get("url", ""),
                    "snippet": page.get("passage", ""),
                    "site": page.get("site", ""),
                })
            return results
    except Exception as e:
        print(f"[wsa_search] failed: {e}")
        return []
