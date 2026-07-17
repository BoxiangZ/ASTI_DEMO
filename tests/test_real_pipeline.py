from __future__ import annotations

import tempfile
import unittest
import sqlite3
import csv
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from engine.config import TOPICS
from engine.real_collector import canonicalize_url, collect_prompts, identify_media
from engine.real_store import load_real_data, real_summary
from engine.gt_corpus import _is_original
from engine.topic_playbook import TOPIC_ACTIONS, build_topic_playbook
from engine.topic_strategy import PROMPTS_PATH, PROMPT_CONFIG_VERSION, ensure_prompt_config


class RealPipelineTest(unittest.TestCase):
    def test_topic_playbook_compares_real_competitor_evidence(self) -> None:
        prompts = pd.DataFrame(
            [
                {"topic": "China Military", "question": "Q1", "prompt_kind": "broad"},
                {"topic": "China Military", "question": "Q2", "prompt_kind": "gt_longtail"},
            ]
        )
        answers = pd.DataFrame(
            [
                {"answer_id": 1, "topic": "China Military", "question": "Q1", "query_intent": "analysis", "captured_at": "2026-07-16", "status": "success"},
                {"answer_id": 2, "topic": "China Military", "question": "Q2", "query_intent": "article_longtail", "captured_at": "2026-07-16", "status": "success"},
            ]
        )
        source_rows = [
            (1, "Global Times", 3, "GT page", "https://www.globaltimes.cn/a", 400),
            (1, "CSIS", 1, "CSIS analysis", "https://www.csis.org/a", 900),
            (2, "CSIS", 1, "CSIS platform dossier", "https://www.csis.org/b", 1200),
        ]
        sources = pd.DataFrame(
            [
                {
                    "answer_id": answer_id,
                    "media_name": media,
                    "source_position": position,
                    "article_title": title,
                    "source_title": title,
                    "source_url": url,
                    "article_word_count": words,
                    "article_text": "According to data, the Type 076 reached 40,000 tons. An expert said \"test evidence\".",
                    "valid_evidence": True,
                }
                for answer_id, media, position, title, url, words in source_rows
            ]
        )
        matches = sources.copy()
        matches["content_match_score"] = [55.0, 76.0, 82.0]

        report = build_topic_playbook("China Military", prompts, answers, sources, matches)

        self.assertEqual(set(TOPIC_ACTIONS), set(TOPICS))
        self.assertEqual(report["dominant_competitor"], "CSIS")
        self.assertEqual(report["tested_questions"], 2)
        self.assertEqual(len(report["lost_prompts"]), 2)
        self.assertEqual(len(report["comparison"]), 8)
        self.assertGreaterEqual(len(report["observations"]), 2)
        self.assertEqual(len(report["competitor_ranking"]), 1)
        self.assertEqual(len(report["prompt_actions"]), 2)
        self.assertGreaterEqual(len(report["actions"]), 7)
        self.assertEqual(len(report["roadmap"]), 3)

    def test_first_hand_signal_requires_reporting_evidence(self) -> None:
        self.assertFalse(_is_original("Global Times", "An article based entirely on public data."))
        self.assertTrue(
            _is_original("Global Times", "A defense expert told the Global Times that the new test was significant.")
        )

    def test_topic_playbook_counts_repeated_daily_answers_as_separate_samples(self) -> None:
        prompts = pd.DataFrame([{"topic": "China Military", "question": "Repeated Q", "prompt_kind": "broad"}])
        answers = pd.DataFrame(
            [
                {"answer_id": 1, "topic": "China Military", "question": "Repeated Q", "query_intent": "analysis", "captured_at": "2026-07-15", "status": "success"},
                {"answer_id": 2, "topic": "China Military", "question": "Repeated Q", "query_intent": "analysis", "captured_at": "2026-07-16", "status": "success"},
            ]
        )
        sources = pd.DataFrame(
            [
                {
                    "answer_id": answer_id,
                    "media_name": "CSIS",
                    "source_position": 1,
                    "article_title": f"Evidence {answer_id}",
                    "source_title": f"Evidence {answer_id}",
                    "source_url": f"https://www.csis.org/{answer_id}",
                    "article_word_count": 500,
                    "article_text": "A detailed evidence page with data and attributed analysis.",
                    "valid_evidence": True,
                }
                for answer_id in [1, 2]
            ]
        )
        matches = sources.copy()
        matches["content_match_score"] = [70.0, 72.0]
        matches["best_matching_passage"] = ["Evidence passage one", "Evidence passage two"]

        report = build_topic_playbook("China Military", prompts, answers, sources, matches)

        self.assertEqual(report["tested_questions"], 2)
        self.assertEqual(report["competitor_metrics"]["coverage_count"], 2)
        self.assertEqual(report["competitor_metrics"]["top3_count"], 2)
        self.assertEqual(len(report["lost_prompts"]), 2)

    def test_researched_longtails_are_natural_and_traceable(self) -> None:
        ensure_prompt_config()
        with PROMPTS_PATH.open(encoding="utf-8", newline="") as handle:
            prompts = list(csv.DictReader(handle))

        longtails = [row for row in prompts if row["prompt_kind"] == "gt_longtail"]
        self.assertEqual(len(prompts), 80)
        self.assertGreaterEqual(len(longtails), 24)
        self.assertEqual({row["config_version"] for row in prompts}, {PROMPT_CONFIG_VERSION})
        self.assertEqual(
            {row["generation_method"] for row in longtails},
            {"researched_event_synthesis"},
        )

        for row in longtails:
            question = row["question"].lower()
            title = row["seed_article_title"].lower()
            self.assertNotIn("global times", question)
            self.assertNotIn("the article", question)
            self.assertTrue(row["seed_article_url"].startswith("https://www.globaltimes.cn/"))
            self.assertTrue(row["core_fact"].strip())
            self.assertLess(SequenceMatcher(None, question, title).ratio(), 0.75)

    def test_all_references_are_stored_and_tenth_position_is_coverage_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ten-references.db"

            def fake_provider(question: str, model: str) -> tuple[dict, int]:
                references = [f"https://source-{index}.example.com/article" for index in range(1, 10)]
                references.append("https://www.globaltimes.cn/page/202607/tenth-reference.shtml")
                return (
                    {
                        "model": model,
                        "choices": [{"message": {"content": f"A sourced answer for {question}."}}],
                        "citations": references,
                    },
                    50,
                )

            collect_prompts(
                provider="perplexity",
                model="sonar-test",
                limit=1,
                delay_seconds=0,
                db_path=db_path,
                response_provider=fake_provider,
            )
            data = load_real_data(db_path)
            gt_score = data["scores"][data["scores"]["media_name"] == "Global Times"].iloc[0]
            outcome = data["prompt_outcomes"].iloc[0]

            self.assertEqual(len(data["citations"]), 10)
            self.assertEqual(data["citations"]["source_position"].tolist(), list(range(1, 11)))
            self.assertEqual(gt_score["cited_prompt_count"], 1)
            self.assertEqual(gt_score["ai_visibility"], 100.0)
            self.assertEqual(gt_score["top3_prompt_count"], 0)
            self.assertEqual(gt_score["top3_rate"], 0.0)
            self.assertEqual(outcome["target_position"], 10)
            self.assertEqual(outcome["competition_result"], "Weak Citation")
            self.assertEqual(outcome["citation_count"], 10)

    def test_collection_storage_and_scoring(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "pilot.db"

            def fake_provider(question: str, model: str) -> tuple[dict, int]:
                return (
                    {
                        "model": model,
                        "choices": [
                            {
                                "message": {
                                    "content": f"A grounded answer for: {question} [1][2]",
                                    "annotations": [
                                        {
                                            "type": "url_citation",
                                            "url_citation": {
                                                "title": "Global Times example",
                                                "url": "https://www.globaltimes.cn/page/202607/example.shtml?utm_source=test",
                                            },
                                        },
                                        {
                                            "type": "url_citation",
                                            "url_citation": {
                                                "title": "Reuters example",
                                                "url": "https://www.reuters.com/world/china/example-2026-07-14/",
                                            },
                                        },
                                    ],
                                }
                            }
                        ],
                    },
                    125,
                )

            result = collect_prompts(
                provider="perplexity",
                model="sonar-test",
                limit=2,
                delay_seconds=0,
                db_path=db_path,
                response_provider=fake_provider,
            )
            unaudited = load_real_data(db_path)
            gt_unaudited = unaudited["scores"][unaudited["scores"]["media_name"] == "Global Times"].iloc[0]
            self.assertEqual(gt_unaudited["ai_visibility"], 100.0)
            self.assertEqual(gt_unaudited["top3_rate"], 100.0)
            self.assertEqual(gt_unaudited["content_evidence_rate"], 0.0)
            self.assertEqual(gt_unaudited["verified_prompt_count"], 0)
            self.assertTrue((unaudited["content_matches"]["match_level"] == "Unverified").all())

            article_text = " ".join(
                ["This verified article provides grounded evidence about China, policy, technology, trade and international developments."] * 20
            )
            with sqlite3.connect(db_path) as conn:
                citation_ids = [row[0] for row in conn.execute("SELECT citation_id FROM citations")]
                conn.executemany(
                    """
                    INSERT INTO citation_audits (
                        citation_id, http_status, access_status, final_url, content_type,
                        article_title, article_text, article_word_count, published_at,
                        author, fetched_at, content_hash, tls_fallback, error_message
                    ) VALUES (?, 200, 'verified', '', 'text/html', 'Verified article', ?, 200,
                              '2026-07-16', 'Test', '2026-07-16T00:00:00+00:00', 'hash', 0, '')
                    """,
                    [(citation_id, article_text) for citation_id in citation_ids],
                )
                conn.commit()

            data = load_real_data(db_path)
            summary = real_summary(data)

            self.assertEqual(result["success_count"], 2)
            self.assertEqual(result["error_count"], 0)
            self.assertEqual(summary["successful_answers"], 2)
            self.assertEqual(summary["citations"], 4)
            self.assertEqual(summary["verified_citations"], 4)
            self.assertEqual(data["runs"].iloc[0]["platform"], "Perplexity")
            self.assertTrue((data["answers"]["ai_platform"] == "Perplexity").all())
            self.assertIn("Global Times", data["scores"]["media_name"].tolist())
            gt_score = data["scores"][data["scores"]["media_name"] == "Global Times"].iloc[0]
            self.assertEqual(gt_score["cited_prompt_count"], 2)
            self.assertEqual(gt_score["top3_prompt_count"], 2)
            self.assertEqual(gt_score["verified_prompt_count"], 2)
            self.assertEqual(len(data["daily_trend"]), 1)
            self.assertEqual(len(data["content_matches"]), 4)
            self.assertIn("content_match_score", data["content_matches"].columns)
            self.assertIn("China Diplomacy", data["topic_diagnostics"]["topic"].tolist())
            self.assertEqual(len(data["prompt_outcomes"]), 2)
            self.assertTrue((data["prompt_outcomes"]["competition_result"] == "GT Win").all())
            self.assertEqual(
                canonicalize_url("https://example.com/a?utm_source=x&id=2#part"),
                "https://example.com/a?id=2",
            )
            self.assertEqual(identify_media("www.globaltimes.cn")[0], "Global Times")
            self.assertEqual(identify_media("www.mfa.gov.cn")[0], "MFA China")
            self.assertEqual(identify_media("fmprc.gov.cn")[0], "MFA China")


if __name__ == "__main__":
    unittest.main()
