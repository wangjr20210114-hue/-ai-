"""搜索系统框架。

架构：
1. 意图分类 → 决定搜哪些源
2. 多源并行搜索 → 网页/微信/知乎/百科
3. 评分排序 → 相关性 + 权威性 + 多样性
4. 随机选择 → 高分结果中随机抽取，避免每次相同
5. 图片提取 → 从网页中提取相关图片

设计参考：Perplexity 的多阶段流水线
"""
from __future__ import annotations

import random
import re
from typing import Any

from services.sogou_search_service import (
    search_web,
    search_wechat,
    search_zhihu,
    search_baike,
    wsa_search,
)
import asyncio

from services.safe_http import request_public_url, safe_head_or_get

# ============================================================
# 1. 意图分类
# ============================================================

class SearchIntent:
    """搜索意图类型。"""
    FACT = "fact"          # 事实查询（XX是什么）
    RECOMMEND = "recommend" # 推荐型（推荐什么书/电影）
    DISCUSSION = "discussion" # 讨论型（怎么评价/怎么看）
    NEWS = "news"          # 时效型（最新/今天/最近）
    GENERAL = "general"    # 通用

# 所有搜索都搜全部来源，不按意图限制
ALL_SOURCES = ["web", "wechat", "zhihu", "baike"]

# 搜索深度 → 总搜索量（翻倍，确保充分搜索）
# 最终展示：basic 6-8 | standard 10-16 | deep 16-24
# 原始搜索池：basic ~25 | standard ~35 | deep ~50
DEPTH_CNT = {
    "basic":    12,
    "standard": 20,
    "deep":     32,
}


def classify_search_intent(query: str) -> str:
    """根据查询词推断搜索意图。"""
    # 推荐型
    if any(kw in query for kw in ["推荐", "什么书", "哪些书", "入门", "书单", "排行", "最好", "最佳"]):
        return SearchIntent.RECOMMEND
    # 讨论型
    if any(kw in query for kw in ["怎么评价", "怎么看", "知乎", "讨论", "观点", "争议"]):
        return SearchIntent.DISCUSSION
    # 时效型
    if any(kw in query for kw in ["最新", "今天", "现在", "最近", "刚刚", "进展", "动态", "更新", "2025", "2026", "怎么了", "发生什么"]):
        return SearchIntent.NEWS
    # 事实型
    if any(kw in query for kw in ["是什么", "什么是", "简介", "百科", "概念", "定义"]):
        return SearchIntent.FACT
    return SearchIntent.GENERAL


# ============================================================
# 2. 评分系统
# ============================================================

# 来源权威性权重
SOURCE_AUTHORITY = {
    "baike": 25,
    "zhihu": 20,
    "wechat": 15,
    "web": 10,
    "wsa": 10,
}


def score_result(result: dict[str, Any], query: str, source_count: dict[str, int], time_sensitive: bool = False) -> float:
    """对搜索结果打分。"""
    import datetime

    score = 0.0
    source = result.get("source", "web")
    title = result.get("title", "")
    snippet = result.get("snippet", "")

    # 1. 相关性（关键词分词匹配）
    query_lower = query.lower()
    title_lower = title.lower()
    snippet_lower = snippet.lower()
    # 分词：中文按字，英文按词
    keywords = [w for w in re.split(r'[\s,，。、？？]+', query_lower) if len(w) >= 1]
    # 去掉常见停用词
    stop_words = {'的', '了', '是', '在', '有', '什么', '怎么', '最近', '今天', '最新', '一个', '可以', '帮我', '搜', '搜索', '查询'}
    keywords = [w for w in keywords if w not in stop_words and len(w) >= 1]

    title_hits = sum(1 for kw in keywords if kw in title_lower)
    snippet_hits = sum(1 for kw in keywords if kw in snippet_lower)
    total_kw = max(len(keywords), 1)
    title_ratio = title_hits / total_kw
    snippet_ratio = snippet_hits / total_kw

    score += title_ratio * 40  # 标题匹配最多40分
    score += snippet_ratio * 20  # 摘要匹配最多20分

    # 2. 权威性
    score += SOURCE_AUTHORITY.get(source, 5)

    # 3. 多样性（轻度惩罚，不过度过滤）
    count = source_count.get(source, 0)
    if count >= 3:
        score -= 8
    elif count >= 2:
        score -= 4

    # 4. 完整性
    if snippet and len(snippet) > 20:
        score += 10
    if result.get("avatar"):
        score += 5
    if result.get("image"):
        score += 5
    if result.get("gh_id"):
        score += 3

    # 5. 时效性加分（时效型查询时大幅加权）
    date_str = result.get("date", "")
    if time_sensitive and date_str:
        today = datetime.date.today()
        try:
            d = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            diff_days = (today - d).days
            if diff_days == 0:
                score += 50  # 今天的内容
            elif diff_days == 1:
                score += 30  # 昨天
            elif diff_days <= 3:
                score += 20  # 3天内
            elif diff_days <= 7:
                score += 10  # 一周内
            elif diff_days > 30:
                score -= 5  # 超过一个月轻度降分
        except (ValueError, TypeError):
            pass

    # 6. 长度惩罚
    if len(title) > 60:
        score -= 10

    return score


# ============================================================
# 3. 图片提取
# ============================================================

async def extract_images_from_results(results: list[dict[str, Any]]) -> list[str]:
    """从搜索结果中提取图片URL。

    来源：
    1. 百科结果中的图片
    2. 网页结果中尝试抓取页面内的图片（取前4条）

    注意：微信公众号头像属于微信公众平台版权资源，不提取使用。
    """
    images: list[str] = []

    for r in results:
        # 百科图片
        if r.get("image"):
            images.append(r["image"])
        # 微信头像不提取（版权限制）

    # 尝试从前 4 条网页结果中提取图片（多提一条弥补移除头像的缺口）
    web_results = [r for r in results if r.get("source") == "web" and r.get("url", "").startswith("http")][:4]
    if web_results:
        tasks = [_extract_page_image(r["url"]) for r in web_results]
        page_images = await asyncio.gather(*tasks, return_exceptions=True)
        for img in page_images:
            if isinstance(img, str) and img:
                images.append(img)

    return images[:8]  # 最多8张（翻倍）


async def _extract_page_image(url: str) -> str:
    """尝试从网页中提取第一张图片。"""
    if not url or not url.startswith("http"):
        return ""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }
        response = await request_public_url(
            "GET",
            url,
            headers=headers,
            timeout_seconds=8,
            max_redirects=3,
            max_bytes=2 * 1024 * 1024,
            allowed_content_types=("text/html", "application/xhtml+xml"),
        )
        if response.status_code != 200:
            return ""
        text = response.text

        # 提取 og:image
        m = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', text, re.IGNORECASE)
        if m:
            img_url = m.group(1)
            img_url = _fix_url_scheme(img_url)
            if _is_meaningful_image(img_url):
                return img_url

        # 提取第一张 jpg/png/webp（也匹配协议相对路径 //xxx）
        m = re.search(r'src="((?:https?:)?//[^"]*\.(?:jpg|jpeg|png|webp)[^"]*)"', text, re.IGNORECASE)
        if m:
            img_url = _fix_url_scheme(m.group(1))
            if _is_meaningful_image(img_url):
                return img_url
        return ""
    except Exception:
        return ""


# 明显的默认图/占位符 URL 模式
_MEANINGLESS_PATTERNS = re.compile(
    r"(default|placeholder|loading|empty|no[-_]?image|fallback|"
    r"not[-_]?found|404|error|blank|spacer|1x1|pixel|"
    r"logo|icon|avatar|share|banner|button|"
    r"\?x-oss-process=.*/resize.*blur|video)",
    re.IGNORECASE,
)


def _is_meaningful_image(url: str) -> bool:
    """判断图片URL是否是有意义的内容图（不是默认图/占位符/logo）。"""
    if not url:
        return False
    return not _MEANINGLESS_PATTERNS.search(url)


def _fix_url_scheme(url: str) -> str:
    """修复协议相对 URL（//xxx → https://xxx）。"""
    if url.startswith("//"):
        return "https:" + url
    return url


async def _check_url_valid(url: str) -> bool:
    """检测 URL 是否可访问（200 且内容不为空）。"""
    if not url or not url.startswith("http"):
        return False
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }
        response = await safe_head_or_get(
            url,
            headers=headers,
            timeout_seconds=6,
        )
        return response.status_code == 200
    except Exception:
        return False


async def _ai_rank_results(
    query: str, results: list[dict[str, Any]], time_sensitive: bool
) -> list[tuple[float, dict[str, Any]]]:
    """用 DeepSeek 对搜索结果评分排序。

    Returns:
        [(score, result), ...] 按分数降序
    """
    if not results:
        return []

    import json
    import httpx
    from config import settings

    # 构建简洁的结果摘要
    items = []
    for i, r in enumerate(results):
        source = r.get("source", "web")
        title = r.get("title", "")[:60]
        snippet = r.get("snippet", "")[:80]
        date = r.get("date", "")
        items.append(f"[{i}] 来源:{source} 标题:{title} 日期:{date} 摘要:{snippet}")

    items_text = "\n".join(items)

    prompt = (
        f"用户查询：{query}\n"
        f"时效性要求：{'是' if time_sensitive else '否'}\n\n"
        f"搜索结果：\n{items_text}\n\n"
        f"请对每条结果评分（0-10分），评估维度：\n"
        f"1. 与查询的相关性（最重要：标题和摘要必须与用户查询直接相关，不相关的给0-2分）\n"
        f"2. 信息质量（内容是否有价值、是否有实质信息）\n"
        f"3. 时效性（如果有时效性要求，近期内容加分）\n"
        f"4. 评分标准：9-10=完美匹配，7-8=高度相关，5-6=相关但信息一般，3-4=弱相关，0-2=不相关/广告/死链\n\n"
        f"只输出 JSON 数组，格式：[[序号, 评分], ...]，按评分降序排列。\n"
        f"例如：[[0, 8.5], [2, 7.0], [1, 3.0]]"
    )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{settings.deepseek_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                json={
                    "model": settings.deepseek_model,
                    "messages": [
                        {"role": "system", "content": "你是搜索结果评估器。只输出 JSON，不要其他内容。"},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 800,
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            content = content.strip("`").strip()
            if content.startswith("json"):
                content = content[4:].strip()
            scores = json.loads(content)

        # 映射回结果
        ranked = []
        for item in scores:
            idx, score = int(item[0]), float(item[1])
            if 0 <= idx < len(results):
                ranked.append((score, results[idx]))
        # 补上未被评分的
        scored_idxs = {int(item[0]) for item in scores}
        for i, r in enumerate(results):
            if i not in scored_idxs:
                ranked.append((0.0, r))
        return ranked
    except Exception as e:
        print(f"[ai_rank] failed: {e}, fallback to rule-based")
        # fallback: 简单规则评分
        source_count: dict[str, int] = {}
        ranked = []
        for r in results:
            src = r.get("source", "web")
            score = score_result(r, query, source_count, time_sensitive=time_sensitive)
            source_count[src] = source_count.get(src, 0) + 1
            ranked.append((score, r))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked# ============================================================
# 4. 聚合搜索（核心入口）
# ============================================================

async def search(query: str, intent: str = None, time_sensitive: bool = None, depth: str = None) -> dict[str, Any]:
    """搜索系统主入口。

    Args:
        query: 搜索关键词
        intent: 搜索意图（fact/recommend/discussion/news/general），由 LLM 推断
        time_sensitive: 是否时效性查询，由 LLM 推断
        depth: 搜索深度（basic/standard/deep），由 LLM 推断
    """
    # 1. 意图分类（fallback）
    if not intent:
        intent = classify_search_intent(query)

    # 时效性：time_sensitive 参数优先于意图分类
    is_time_sensitive = time_sensitive if time_sensitive is not None else (intent == SearchIntent.NEWS)

    # 搜索深度 → 总搜索量（翻倍，确保充分搜索）
    # 最终展示：basic 6-8 | standard 10-16 | deep 16-24
    total_cnt = DEPTH_CNT.get(depth, DEPTH_CNT["standard"])

    # 按来源分配搜索量，每种源至少搜 5 条（多搜多筛）
    sources_to_search = ALL_SOURCES
    per_source = max(5, total_cnt // 3)

    # 2. 并行搜索
    tasks = {}
    if "web" in sources_to_search:
        tasks["web"] = search_web(query, cnt=per_source + 1, sort_by_time=is_time_sensitive)
    if "wechat" in sources_to_search:
        tasks["wechat"] = search_wechat(query, cnt=per_source)
    if "zhihu" in sources_to_search:
        tasks["zhihu"] = search_zhihu(query, cnt=per_source)
    if "baike" in sources_to_search:
        tasks["baike"] = search_baike(query)
    # WSA 并行搜索（与搜狗同时进行，结果合并）
    tasks["wsa"] = wsa_search(query, cnt=per_source)

    raw_results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    # 3. 汇总结果
    results: list[dict[str, Any]] = []
    sources_used: list[str] = []

    for source_name, res in zip(tasks.keys(), raw_results):
        if isinstance(res, Exception) or not res:
            continue
        if isinstance(res, list):
            results.extend(res)
            sources_used.append(source_name)
        elif isinstance(res, dict):
            results.append(res)
            sources_used.append(source_name)

    # 时效型查询：过滤掉超过 6 个月的结果（有日期的才过滤）
    if is_time_sensitive:
        import datetime
        cutoff = datetime.date.today() - datetime.timedelta(days=180)
        filtered = []
        for r in results:
            date_str = r.get("date", "")
            if date_str:
                try:
                    d = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                    if d < cutoff:
                        continue  # 超过6个月，跳过
                except (ValueError, TypeError):
                    pass
            filtered.append(r)
        results = filtered

    if not results:
        return {
            "query": query, "intent": intent, "results": [],
            "images": [], "sources_used": [], "total": 0,
        }

    # 3.5 检测所有源的有效性，排除 404/失效链接
    # 检查所有结果的真实 URL（跳过搜狗 /link 跳转链接）
    web_results_to_check = [
        r for r in results
        if r.get("url", "").startswith("http")
        and "sogou.com/link" not in r.get("url", "")
    ]
    if web_results_to_check:
        validity_results = await asyncio.gather(
            *[_check_url_valid(r["url"]) for r in web_results_to_check],
            return_exceptions=True,
        )
        invalid_urls = set()
        for r, is_valid in zip(web_results_to_check, validity_results):
            if isinstance(is_valid, bool) and not is_valid:
                invalid_urls.add(r["url"])
        if invalid_urls:
            results = [r for r in results if r.get("url") not in invalid_urls]
            print(f"[search] filtered {len(invalid_urls)} invalid URLs")

    # 4. AI 筛选：用 DeepSeek 评估每条结果的相关性和质量
    ai_ranked = await _ai_rank_results(query, results, is_time_sensitive)

    # 5. 随机选择：从 AI 推荐的高分结果中随机选
    quality_results = [(s, r) for s, r in ai_ranked if s >= 6]  # AI 评分 >= 6 的保留
    if not quality_results:
        quality_results = ai_ranked[:8]  # 兜底：取前8条

    # depth 决定最终展示数量范围（翻倍）
    if depth == "basic":
        top_n = random.randint(6, max(6, min(8, len(quality_results))))
    elif depth == "deep":
        top_n = random.randint(16, max(16, min(24, len(quality_results))))
    else:  # standard
        top_n = random.randint(10, max(10, min(16, len(quality_results))))
    pool_size = min(len(quality_results), top_n * 2)
    pool = quality_results[:pool_size]
    # 权重随机：分数越高被选概率越大
    weights = [max(s + 10, 1) for s, _ in pool]
    chosen = set()
    while len(chosen) < min(top_n, len(pool)):
        remaining = [i for i in range(len(pool)) if i not in chosen]
        rem_weights = [weights[i] for i in remaining]
        if sum(rem_weights) == 0:
            chosen.update(remaining[:top_n - len(chosen)])
            break
        idx = random.choices(remaining, weights=rem_weights, k=1)[0]
        chosen.add(idx)

    final_results = [pool[i][1] for i in sorted(chosen)]

    # 6. 提取图片
    images = await extract_images_from_results(final_results)

    # 7. 用混元视觉模型描述图片内容（图文交错的关键）
    image_descriptions: list[dict[str, str]] = []
    if images:
        try:
            from services.hunyuan_service import hunyuan_service
            image_descriptions = await hunyuan_service.describe_images(images[:5], context=query)
            # 二次过滤：丢弃视觉描述为占位符/logo/默认图/纯装饰的图片
            _USELESS_DESC = re.compile(
                r"(占位符|默认图|空白|logo|图标|装饰|无内容|纯色|背景|视频|播放器|无法识别)",
                re.IGNORECASE,
            )
            before = len(image_descriptions)
            image_descriptions = [
                item for item in image_descriptions
                if not _USELESS_DESC.search(item["description"])
            ]
            if before != len(image_descriptions):
                print(f"[search] vision filtered {before - len(image_descriptions)} useless images")
            if image_descriptions:
                print(f"[search] vision kept {len(image_descriptions)} meaningful images")
            else:
                print("[search] vision describe returned empty (model may be unavailable)")
        except Exception as e:
            print(f"[search] vision describe failed: {e}")

    return {
        "query": query,
        "intent": intent,
        "results": final_results,
        "images": images,
        "image_descriptions": image_descriptions,
        "sources_used": sources_used,
        "total": len(final_results),
    }
