from agents._tests.support.workspace_environment import *  # noqa: F401,F403


class PaperDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_paper_capability_checksum_prevents_plain_answer_bypass(self):
        model = StructuredPlannerModel(args={
            "capabilities": ["papers"],
            "prompt_topics": ["paper"],
            # Reproduce the observed gateway inconsistency: the semantic
            # capability is present while its detailed boolean was omitted.
            "needs_papers": False,
            "paper_topic": "",
            "paper_author": "Xin Peng",
            "paper_institution": "Fudan University",
            "paper_identity_evidence_supplied": True,
            "paper_year_from": 2025,
            "paper_year_to": 2026,
            "paper_limit": 2,
        })
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "给我找两篇复旦大学彭鑫老师近2年的论文",
            timeout_seconds=2,
        )
        self.assertFalse(timed_out)
        self.assertTrue(plan["needs_papers"])
        self.assertEqual(plan["_capabilities"], ["papers"])
        self.assertEqual(required_tools_for_plan(plan), ("search_arxiv",))
        self.assertEqual(
            direct_paper_tool_arguments(plan)["search_arxiv"]["limit"],
            2,
        )
        self.assertEqual(
            direct_paper_tool_arguments(plan)["search_arxiv"]["topic"],
            "",
        )

    async def test_ambiguous_paper_author_is_stopped_before_search(self):
        model = StructuredPlannerModel(args={
            "capabilities": ["papers"],
            "prompt_topics": ["paper"],
            "needs_papers": True,
            "paper_author": "Xin Peng",
            "paper_limit": 2,
            "paper_identity_evidence_supplied": False,
            "paper_identity_globally_unambiguous": False,
        })
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "Find two papers by the professor I named.",
            timeout_seconds=2,
        )
        self.assertFalse(timed_out)
        self.assertTrue(plan["needs_clarification"])
        self.assertFalse(plan["needs_papers"])
        self.assertEqual(
            required_tools_for_plan(plan),
            ("ask_user_clarification",),
        )
        self.assertEqual(
            plan["clarification_fields"][0]["id"],
            "paper-author-identity",
        )

    async def test_user_supplied_paper_identity_reaches_search(self):
        model = StructuredPlannerModel(args={
            "capabilities": ["papers"],
            "prompt_topics": ["paper"],
            "needs_papers": True,
            "paper_author": "Xin Peng",
            "paper_institution": "Fudan University",
            "paper_identity_evidence_supplied": True,
            "paper_identity_globally_unambiguous": False,
            "paper_limit": 2,
        })
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "Find two papers by the identified professor.",
            timeout_seconds=2,
        )
        self.assertFalse(timed_out)
        self.assertFalse(plan["needs_clarification"])
        self.assertTrue(plan["needs_papers"])
        self.assertEqual(required_tools_for_plan(plan), ("search_arxiv",))

    def test_prompt_topic_does_not_execute_paper_without_capability(self):
        plan = parse_capability_plan({
            "capabilities": [],
            "prompt_topics": ["paper"],
            "needs_papers": False,
            "paper_author": "Xin Peng",
            "paper_identity_globally_unambiguous": True,
        })
        self.assertFalse(plan["needs_papers"])
        self.assertEqual(plan["_capabilities"], [])
        self.assertEqual(required_tools_for_plan(plan), ())

    def test_news_may_load_paper_boundary_without_running_paper_search(self):
        plan = parse_capability_plan({
            "capabilities": ["web_search"],
            "prompt_topics": ["web", "paper"],
            "needs_web_search": True,
            "needs_images": True,
            "needs_papers": False,
            "search_query": "今天 AI 新闻",
            "image_query": "今天 AI 新闻事件现场",
        })
        self.assertEqual(plan["_capabilities"], ["web_search"])
        self.assertEqual(required_tools_for_plan(plan), ("rich_search",))

    def test_paper_chain_skips_only_redundant_argument_model_rounds(self):
        direct = direct_paper_tool_arguments({
            "needs_papers": True,
            "needs_web_search": False,
            "paper_topic": "retrieval augmented generation",
            "paper_author": "Xin Peng",
            "paper_institution": "Fudan University",
            "paper_year_from": 2025,
            "paper_year_to": 2026,
            "paper_limit": 6,
        })
        self.assertEqual(
            direct["search_arxiv"]["topic"],
            "retrieval augmented generation",
        )
        self.assertEqual(direct["search_arxiv"]["limit"], 6)
        self.assertEqual(direct["search_arxiv"]["author"], "Xin Peng")
        self.assertEqual(direct["search_arxiv"]["institution"], "Fudan University")
        self.assertEqual(direct["search_arxiv"]["year_from"], 2025)
        self.assertEqual(direct["search_arxiv"]["year_to"], 2026)
        self.assertEqual(
            direct_paper_tool_arguments({
                "needs_papers": True,
                "needs_web_search": True,
                "paper_topic": "retrieval augmented generation",
            }),
            {},
        )

    def test_paper_plan_uses_arxiv_without_requiring_web_search(self):
        self.assertEqual(
            required_tools_for_plan({"needs_papers": True}),
            ("search_arxiv",),
        )
        self.assertEqual(
            required_tools_for_plan({"needs_papers": True, "needs_web_search": True}),
            ("rich_search", "search_arxiv"),
        )

    def test_empty_paper_result_cannot_override_successful_web_search(self):
        web = ToolMessage(
            name="rich_search",
            tool_call_id="web-1",
            content=json.dumps({
                "ui_action": "rich_search_results",
                "search_results": {
                    "results": [{
                        "title": "AI 新闻",
                        "url": "https://news.example.com/ai",
                    }],
                },
            }, ensure_ascii=False),
        )
        paper = ToolMessage(
            name="search_arxiv",
            tool_call_id="paper-1",
            content=json.dumps({
                "ui_action": "paper_results",
                "papers": [],
            }, ensure_ascii=False),
        )
        answer = tool_result_fallback([web, paper])
        self.assertIn("[AI 新闻](https://news.example.com/ai)", answer)
        self.assertNotIn("没有核实到符合作者", answer)

    def test_arxiv_title_matching_rejects_topic_level_noise(self):
        candidates = [
            {"title": "Algebraic Zhou valuations", "arxiv_id": "bad"},
            {"title": "Tradeoffs Between Contrastive and Supervised Learning: An Empirical Study", "arxiv_id": "good"},
        ]
        matched = _best_title_match("Tradeoffs Between Contrastive and Supervised Learning: An Empirical Study", candidates)
        self.assertEqual(matched["arxiv_id"], "good")
        self.assertIsNone(_best_title_match("Efficient Rectification of Neuro-Symbolic Reasoning Inconsistencies", candidates))

    def test_topic_relevance_accepts_acronym_expansion_and_inflection(self):
        self.assertTrue(_paper_matches_topic({
            "title": "Evaluating Retrieval-Augmented Generation Systems",
            "abstract_zh": "A benchmark for grounded question answering.",
        }, "RAG evaluation"))
        self.assertFalse(_paper_matches_topic({
            "title": "Vision-Language Action Models for Robot Manipulation",
            "abstract_zh": "We evaluate a robotic control policy.",
        }, "RAG evaluation"))

    async def test_topic_search_drops_verified_but_unrelated_candidates(self):
        unrelated = {
            "title": "Clinical Decision Support with Language Models",
            "arxiv_id": "2608.00001",
            "abstract_zh": "A clinical assistant evaluated by physicians.",
        }
        relevant = {
            "title": "A Benchmark for Retrieval-Augmented Generation",
            "arxiv_id": "2608.00002",
            "abstract_zh": "We evaluate RAG pipelines across diverse corpora.",
        }
        with patch(
            "agents._infrastructure.providers.arxiv._lookup_arxiv_ids_sync",
            return_value=[unrelated, relevant],
        ):
            papers = await search_arxiv(
                "RAG evaluation",
                2,
                candidate_ids=["2608.00001", "2608.00002"],
            )
        self.assertEqual(papers, [relevant])

    async def test_named_author_search_falls_back_to_crossref_with_range(self):
        crossref_paper = {
            "title": "Recent Software Engineering Work",
            "arxiv_id": "webpdf-example",
            "authors": "Xin Peng",
            "year": 2026,
            "abstract_zh": "",
            "key_contribution": "",
            "citations": "Crossref",
            "source": "Crossref",
            "source_url": "https://doi.org/10.1000/example",
            "arxiv_url": "",
            "pdf_url": "https://publisher.example/paper.pdf",
        }
        with patch(
            "agents._infrastructure.providers.arxiv._search_arxiv_sync",
            return_value=[],
        ), patch(
            "agents._infrastructure.providers.arxiv._search_dblp_sync",
            return_value=[],
        ), patch(
            "agents._infrastructure.providers.arxiv._search_openalex_sync",
            return_value=[],
        ), patch(
            "agents._infrastructure.providers.arxiv._search_crossref_sync",
            return_value=[crossref_paper],
        ) as crossref:
            papers = await search_arxiv(
                "",
                2,
                author="Xin Peng",
                institution="Fudan University",
                year_from=2025,
                year_to=2026,
            )
        self.assertEqual(papers, [crossref_paper])
        self.assertEqual(
            crossref.call_args.args,
            ("", 2, "Xin Peng", "Fudan University", 2025, 2026),
        )

    def test_dblp_identity_resolution_accepts_two_token_signature_order(self):
        verified_root = object()
        with patch(
            "agents._infrastructure.providers.arxiv._dblp_profile_cached",
            side_effect=[
                ("", None),
                ("14/6370-1", verified_root),
            ],
        ) as cached:
            pid, root = _dblp_profile("Peng Xin", "Fudan University")
        self.assertEqual(pid, "14/6370-1")
        self.assertIs(root, verified_root)
        self.assertEqual(cached.call_args_list[0].args[:2], (
            "Peng Xin", "Fudan University",
        ))
        self.assertEqual(cached.call_args_list[1].args[:2], (
            "Xin Peng", "Fudan University",
        ))

    def test_openalex_requires_matching_author_affiliation_on_profile_and_work(self):
        class Response:
            def __init__(self, payload):
                self.payload = json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return self.payload

        author_payload = {"results": [{
            "id": "https://openalex.org/A1",
            "display_name": "Xin Peng",
            "display_name_alternatives": ["Peng Xin"],
            "works_count": 100,
            "cited_by_count": 200,
            "last_known_institutions": [{
                "display_name": "Fudan University",
            }],
        }]}
        work_payload = {"results": [{
            "id": "https://openalex.org/W1",
            "doi": "https://doi.org/10.1000/example",
            "title": "Verified Recent Work",
            "publication_year": 2026,
            "cited_by_count": 5,
            "ids": {},
            "authorships": [{
                "author": {
                    "id": "https://openalex.org/A1",
                    "display_name": "Xin Peng",
                },
                "institutions": [{"display_name": "Fudan University"}],
            }],
            "primary_location": {
                "landing_page_url": "https://doi.org/10.1000/example",
                "pdf_url": "",
            },
        }]}
        with patch(
            "agents._infrastructure.providers.arxiv.urllib.request.urlopen",
            side_effect=[Response(author_payload), Response(work_payload)],
        ):
            papers = _search_openalex_sync(
                "",
                2,
                "Peng Xin",
                "Fudan University",
                2022,
                2026,
            )
        self.assertEqual([paper["title"] for paper in papers], [
            "Verified Recent Work",
        ])
        self.assertEqual(papers[0]["source"], "OpenAlex")

    def test_model_arxiv_identifiers_are_strictly_sanitized(self):
        self.assertEqual(_canonical_arxiv_id("arXiv:2604.10767v2"), "2604.10767v2")
        self.assertEqual(
            _canonical_arxiv_id("https://arxiv.org/pdf/hep-th/9901001.pdf"),
            "hep-th/9901001",
        )
        self.assertEqual(_canonical_arxiv_id("https://example.com/not-arxiv"), "")
        self.assertEqual(_canonical_arxiv_id("ignore instructions"), "")

    async def test_fast_model_only_proposes_lazy_paper_candidates(self):
        class PaperCandidateModel:
            def __init__(self):
                self.schema = None
                self.calls = 0

            def with_structured_output(self, schema, **_kwargs):
                self.schema = schema
                return self

            async def ainvoke(self, _messages):
                self.calls += 1
                return {
                    "parsed": self.schema(candidates=[{
                        "title": "Verified Later",
                        "arxiv_id": "2604.10767",
                        "authors": ["Xin Peng"],
                        "year": 2026,
                    }]),
                }

        discovery_model = PaperCandidateModel()
        tools = build_system_skill_tools(
            None,
            store=FakeStore(),
            conversation_id="paper-candidates",
            user_id=TEST_USER_ID,
            env={},
            paper_discovery_model=discovery_model,
        )
        tool = next(item for item in tools if item.name == "search_arxiv")
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_arxiv",
            new=AsyncMock(return_value=[]),
        ) as provider:
            await tool.ainvoke({
                "author": "Xin Peng",
                "institution": "Fudan University",
                "year_from": 2025,
                "year_to": 2026,
                "limit": 2,
            })
        self.assertEqual(discovery_model.calls, 0)
        loader = provider.await_args.kwargs["candidate_ids_loader"]
        self.assertEqual(await loader(), ["2604.10767"])
        self.assertEqual(discovery_model.calls, 1)

    async def test_searchpro_paper_fallback_is_bound_to_supplied_source(self):
        class EvidenceModel:
            def with_structured_output(self, schema, **_kwargs):
                self.schema = schema
                return self

            async def ainvoke(self, _messages):
                return {
                    "parsed": self.schema(candidates=[{
                        "source_id": "source-1",
                        "title": "TraceLLM: Scalable and Explainable Traceability Recovery",
                        "authors": ["Xin Peng"],
                        "year": 2026,
                        "arxiv_id": "",
                    }]),
                }

        papers = await _paper_candidates_from_searchpro(
            EvidenceModel(),
            metadata={"results": [{
                "id": "source-1",
                "title": "TraceLLM publication record",
                "snippet": "Xin Peng, Fudan University, 2026.",
                "url": "https://dblp.org/rec/conf/icse/example",
                "date": "2026",
            }]},
            topic="",
            author="Xin Peng",
            institution="Fudan University",
            year=0,
            year_from=2025,
            year_to=2026,
            limit=2,
        )

        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["source"], "DBLP")
        self.assertEqual(
            papers[0]["source_url"],
            "https://dblp.org/rec/conf/icse/example",
        )
        self.assertEqual(papers[0]["arxiv_url"], "")

    async def test_author_institution_tool_uses_makers_search_as_fallback(self):
        class EvidenceModel:
            def with_structured_output(self, schema, **_kwargs):
                self.schema = schema
                return self

            async def ainvoke(self, _messages):
                if self.schema.__name__ == "PaperSearchEvidenceCandidates":
                    return {
                        "parsed": self.schema(candidates=[{
                            "source_id": "source-1",
                            "title": "Verified Makers Paper",
                            "authors": ["Xin Peng"],
                            "year": 2026,
                            "arxiv_id": "2604.10767",
                        }]),
                    }
                return {"parsed": self.schema(candidates=[])}

        tools = build_system_skill_tools(
            None,
            store=FakeStore(),
            conversation_id="paper-makers-fallback",
            user_id=TEST_USER_ID,
            env={"WSA_API_KEY": "test-key"},
            paper_discovery_model=EvidenceModel(),
        )
        tool = next(item for item in tools if item.name == "search_arxiv")
        search_metadata = {"results": [{
            "id": "source-1",
            "title": "Verified Makers Paper arXiv:2604.10767",
            "snippet": "Xin Peng, Fudan University, 2026, arXiv 2604.10767.",
            "url": "https://arxiv.org/abs/2604.10767",
            "date": "2026",
        }]}
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_arxiv",
            new=AsyncMock(return_value=[]),
        ), patch(
            "agents._infrastructure.skills.builtin_operations.provider_rich_search",
            new=AsyncMock(return_value=search_metadata),
        ) as search, patch(
            "agents._infrastructure.skills.builtin_operations.record_provider_usage",
            new=AsyncMock(),
        ):
            result = json.loads(await tool.ainvoke({
                "author": "Xin Peng",
                "institution": "Fudan University",
                "year_from": 2025,
                "year_to": 2026,
                "limit": 2,
            }))

        self.assertEqual(len(result["papers"]), 1)
        self.assertEqual(result["papers"][0]["arxiv_id"], "2604.10767")
        search.assert_awaited_once()

    async def test_mixed_language_topic_reuses_makers_search_concurrently(self):
        class EvidenceModel:
            def with_structured_output(self, schema, **_kwargs):
                self.schema = schema
                return self

            async def ainvoke(self, _messages):
                if self.schema.__name__ == "PaperSearchEvidenceCandidates":
                    return {
                        "parsed": self.schema(candidates=[{
                            "source_id": "source-1",
                            "title": "A Verified RAG Evaluation Benchmark",
                            "authors": ["Researcher"],
                            "year": 2025,
                            "arxiv_id": "2501.01234",
                        }]),
                    }
                return {"parsed": self.schema(candidates=[])}

        tools = build_system_skill_tools(
            None,
            store=FakeStore(),
            conversation_id="paper-mixed-language",
            user_id=TEST_USER_ID,
            env={"WSA_API_KEY": "test-key"},
            paper_discovery_model=EvidenceModel(),
        )
        tool = next(item for item in tools if item.name == "search_arxiv")
        search_metadata = {"results": [{
            "id": "source-1",
            "title": "A Verified RAG Evaluation Benchmark arXiv:2501.01234",
            "snippet": "RAG evaluation benchmark, 2025, arXiv 2501.01234.",
            "url": "https://arxiv.org/abs/2501.01234",
            "date": "2025",
        }]}
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_arxiv",
            new=AsyncMock(return_value=[]),
        ) as academic, patch(
            "agents._infrastructure.skills.builtin_operations.provider_rich_search",
            new=AsyncMock(return_value=search_metadata),
        ) as search, patch(
            "agents._infrastructure.skills.builtin_operations.record_provider_usage",
            new=AsyncMock(),
        ):
            result = json.loads(await tool.ainvoke({
                "topic": "RAG 评测",
                "year_from": 2024,
                "limit": 3,
            }))

        academic.assert_awaited_once()
        search.assert_awaited_once()
        self.assertEqual(len(result["papers"]), 1)
        self.assertEqual(result["papers"][0]["arxiv_id"], "2501.01234")

    async def test_verified_model_paper_results_skip_makers_search(self):
        class CandidateModel:
            def with_structured_output(self, schema, **_kwargs):
                self.schema = schema
                return self

            async def ainvoke(self, _messages):
                return {"parsed": self.schema(candidates=[])}

        verified = {
            "title": "Verified arXiv Paper",
            "arxiv_id": "2604.10767",
            "authors": "Xin Peng",
            "year": 2026,
            "pdf_url": "https://arxiv.org/pdf/2604.10767.pdf",
        }
        tools = build_system_skill_tools(
            None,
            store=FakeStore(),
            conversation_id="paper-model-first",
            user_id=TEST_USER_ID,
            env={"WSA_API_KEY": "test-key"},
            paper_discovery_model=CandidateModel(),
        )
        tool = next(item for item in tools if item.name == "search_arxiv")
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_arxiv",
            new=AsyncMock(return_value=[verified]),
        ), patch(
            "agents._infrastructure.skills.builtin_operations.provider_rich_search",
            new=AsyncMock(),
        ) as search:
            result = json.loads(await tool.ainvoke({
                "author": "Xin Peng",
                "institution": "Fudan University",
                "limit": 1,
            }))
        self.assertEqual(result["papers"], [verified])
        search.assert_not_awaited()

    async def test_author_and_institution_disable_broad_arxiv_homonym_search(self):
        verified = {
            "title": "Institution-Matched Paper",
            "arxiv_id": "2604.10767",
            "authors": "Xin Peng",
            "year": 2026,
            "source": "arXiv",
        }
        dblp = {
            "title": "Institution-Matched Paper",
            "arxiv_id": "",
            "authors": "Xin Peng",
            "year": 2026,
            "source": "DBLP",
        }
        with patch(
            "agents._infrastructure.providers.arxiv._lookup_arxiv_ids_sync",
            return_value=[verified],
        ) as exact_lookup, patch(
            "agents._infrastructure.providers.arxiv._search_dblp_sync",
            return_value=[dblp],
        ), patch(
            "agents._infrastructure.providers.arxiv._search_arxiv_sync",
            return_value=[{"title": "Wrong Homonym"}],
        ) as broad_lookup, patch(
            "agents._infrastructure.providers.arxiv._search_openalex_sync",
            return_value=[],
        ), patch(
            "agents._infrastructure.providers.arxiv._search_crossref_sync",
            return_value=[],
        ) as crossref:
            papers = await search_arxiv(
                "",
                2,
                author="Xin Peng",
                institution="Fudan University",
                year_from=2025,
                year_to=2026,
                candidate_ids=["2604.10767"],
            )
        broad_lookup.assert_not_called()
        exact_lookup.assert_called_once_with(
            ["2604.10767"], "Xin Peng", 2025, 2026,
        )
        crossref.assert_not_called()
        self.assertEqual(papers, [verified])

    async def test_arxiv_tool_accepts_author_and_year_without_topic(self):
        tools = build_system_skill_tools(
            None, store=FakeStore(), conversation_id="papers",
            user_id=TEST_USER_ID, env={},
        )
        tool = next(item for item in tools if item.name == "search_arxiv")
        with patch("agents._infrastructure.skills.builtin_operations.provider_search_arxiv", new=AsyncMock(return_value=[])) as provider:
            result = await tool.ainvoke({"author": "Zhi-Hua Zhou", "year": 2026, "limit": 5})
        self.assertIn('"papers": []', result)
        provider.assert_awaited_once_with(
            "", 5, [], "Zhi-Hua Zhou", 2026, "", 0, 0,
        )

    async def test_arxiv_tool_preserves_user_author_year_and_limit_constraints(self):
        tools = build_system_skill_tools(
            None, store=FakeStore(), conversation_id="papers", env={},
            user_id=TEST_USER_ID,
            paper_constraints={"author": "Zhi-Hua Zhou", "year": 2026, "limit": 5},
        )
        tool = next(item for item in tools if item.name == "search_arxiv")
        with patch("agents._infrastructure.skills.builtin_operations.provider_search_arxiv", new=AsyncMock(return_value=[])) as provider:
            await tool.ainvoke({"titles": ["Unrelated title"], "limit": 20})
        provider.assert_awaited_once_with(
            "", 5, ["Unrelated title"], "Zhi-Hua Zhou", 2026, "", 0, 0,
        )

