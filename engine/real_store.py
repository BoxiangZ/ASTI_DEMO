from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from engine.config import CORE_QUERY_INTENTS, MEDIA, STRATEGIC_WEIGHTS, TARGET_MEDIA
from engine.topic_strategy import ensure_prompt_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "database" / "real_monitor.db"
PILOT_PROMPTS_PATH = PROJECT_ROOT / "config" / "pilot_prompts.csv"


def load_pilot_prompts() -> pd.DataFrame:
    ensure_prompt_config()
    prompts = pd.read_csv(PILOT_PROMPTS_PATH)
    prompts["is_brand_query"] = prompts["is_brand_query"].map(
        lambda value: str(value).strip().lower() in {"true", "1", "yes"}
    )
    return prompts


def initialize_database(db_path: Path | str = DEFAULT_DB_PATH) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                platform TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                total_prompts INTEGER NOT NULL,
                success_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS answers (
                answer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                prompt_id INTEGER NOT NULL,
                topic TEXT NOT NULL,
                query_intent TEXT NOT NULL,
                language TEXT NOT NULL,
                ai_platform TEXT NOT NULL,
                model TEXT NOT NULL,
                question TEXT NOT NULL,
                answer_text TEXT,
                captured_at TEXT NOT NULL,
                latency_ms INTEGER,
                status TEXT NOT NULL,
                error_message TEXT,
                raw_response_json TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(run_id),
                UNIQUE(run_id, prompt_id)
            );

            CREATE TABLE IF NOT EXISTS citations (
                citation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                answer_id INTEGER NOT NULL,
                run_id TEXT NOT NULL,
                prompt_id INTEGER NOT NULL,
                media_name TEXT NOT NULL,
                domain TEXT NOT NULL,
                cluster TEXT NOT NULL,
                source_url TEXT NOT NULL,
                source_title TEXT,
                source_snippet TEXT,
                source_position INTEGER NOT NULL,
                is_top3 INTEGER NOT NULL,
                cited_at TEXT NOT NULL,
                FOREIGN KEY (answer_id) REFERENCES answers(answer_id),
                FOREIGN KEY (run_id) REFERENCES runs(run_id),
                UNIQUE(answer_id, source_url)
            );

            CREATE TABLE IF NOT EXISTS citation_audits (
                citation_id INTEGER PRIMARY KEY,
                http_status INTEGER NOT NULL DEFAULT 0,
                access_status TEXT NOT NULL,
                final_url TEXT,
                content_type TEXT,
                article_title TEXT,
                article_text TEXT,
                article_word_count INTEGER NOT NULL DEFAULT 0,
                published_at TEXT,
                author TEXT,
                fetched_at TEXT NOT NULL,
                content_hash TEXT,
                tls_fallback INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                FOREIGN KEY (citation_id) REFERENCES citations(citation_id)
            );

            CREATE TABLE IF NOT EXISTS citation_deep_assessments (
                citation_id INTEGER PRIMARY KEY,
                model TEXT NOT NULL,
                assessed_at TEXT NOT NULL,
                support_score REAL NOT NULL,
                supported_claims_json TEXT NOT NULL,
                unsupported_claims_json TEXT NOT NULL,
                contradictions_json TEXT NOT NULL,
                rationale TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                FOREIGN KEY (citation_id) REFERENCES citations(citation_id)
            );

            CREATE TABLE IF NOT EXISTS gt_articles (
                article_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_section TEXT NOT NULL,
                source_listing_url TEXT NOT NULL,
                article_url TEXT NOT NULL UNIQUE,
                title TEXT,
                published_at TEXT,
                author TEXT,
                article_text TEXT,
                article_word_count INTEGER NOT NULL DEFAULT 0,
                content_hash TEXT,
                fetched_at TEXT NOT NULL,
                primary_topic TEXT NOT NULL,
                classification_score REAL NOT NULL DEFAULT 0,
                classification_terms TEXT,
                is_original INTEGER NOT NULL DEFAULT 0,
                access_status TEXT NOT NULL,
                http_status INTEGER NOT NULL DEFAULT 0,
                error_message TEXT
            );

            CREATE TABLE IF NOT EXISTS topic_weight_snapshots (
                snapshot_date TEXT NOT NULL,
                topic TEXT NOT NULL,
                article_count INTEGER NOT NULL,
                original_count INTEGER NOT NULL,
                volume_share REAL NOT NULL,
                original_share REAL NOT NULL,
                strategic_importance REAL NOT NULL,
                calculated_weight REAL NOT NULL,
                sample_urls_json TEXT,
                PRIMARY KEY (snapshot_date, topic)
            );

            CREATE INDEX IF NOT EXISTS idx_answers_captured_at ON answers(captured_at);
            CREATE INDEX IF NOT EXISTS idx_answers_prompt_id ON answers(prompt_id);
            CREATE INDEX IF NOT EXISTS idx_citations_media_name ON citations(media_name);
            CREATE INDEX IF NOT EXISTS idx_citations_domain ON citations(domain);
            CREATE INDEX IF NOT EXISTS idx_gt_articles_topic ON gt_articles(primary_topic);
            CREATE INDEX IF NOT EXISTS idx_gt_articles_published ON gt_articles(published_at);
            """
        )
    return path


def create_run(
    run_id: str,
    started_at: str,
    platform: str,
    model: str,
    total_prompts: int,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> None:
    initialize_database(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO runs (
                run_id, started_at, platform, model, status, total_prompts,
                success_count, error_count
            ) VALUES (?, ?, ?, ?, 'running', ?, 0, 0)
            """,
            (run_id, started_at, platform, model, total_prompts),
        )


def record_answer(
    run_id: str,
    prompt: dict[str, Any],
    platform: str,
    model: str,
    captured_at: str,
    latency_ms: int,
    status: str,
    answer_text: str = "",
    error_message: str = "",
    raw_response: dict[str, Any] | None = None,
    citations: list[dict[str, Any]] | None = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> int:
    initialize_database(db_path)
    raw_json = json.dumps(raw_response or {}, ensure_ascii=False)
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO answers (
                run_id, prompt_id, topic, query_intent, language, ai_platform,
                model, question, answer_text, captured_at, latency_ms, status,
                error_message, raw_response_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                int(prompt["prompt_id"]),
                str(prompt["topic"]),
                str(prompt["query_intent"]),
                str(prompt["language"]),
                platform,
                model,
                str(prompt["question"]),
                answer_text,
                captured_at,
                latency_ms,
                status,
                error_message,
                raw_json,
            ),
        )
        answer_id = int(cursor.lastrowid)
        for citation in citations or []:
            conn.execute(
                """
                INSERT OR IGNORE INTO citations (
                    answer_id, run_id, prompt_id, media_name, domain, cluster,
                    source_url, source_title, source_snippet, source_position,
                    is_top3, cited_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    answer_id,
                    run_id,
                    int(prompt["prompt_id"]),
                    citation["media_name"],
                    citation["domain"],
                    citation["cluster"],
                    citation["source_url"],
                    citation.get("source_title", ""),
                    citation.get("source_snippet", ""),
                    int(citation["source_position"]),
                    int(citation["source_position"] <= 3),
                    captured_at,
                ),
            )
    return answer_id


def complete_run(
    run_id: str,
    completed_at: str,
    success_count: int,
    error_count: int,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> None:
    status = "completed" if error_count == 0 else "completed_with_errors"
    if success_count == 0:
        status = "failed"
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE runs
            SET completed_at = ?, status = ?, success_count = ?, error_count = ?
            WHERE run_id = ?
            """,
            (completed_at, status, success_count, error_count, run_id),
        )


def load_real_data(
    db_path: Path | str = DEFAULT_DB_PATH,
    platform: str | None = None,
) -> dict[str, pd.DataFrame]:
    initialize_database(db_path)
    with _connect(db_path) as conn:
        runs = pd.read_sql_query("SELECT * FROM runs ORDER BY started_at DESC", conn)
        answers = pd.read_sql_query("SELECT * FROM answers ORDER BY captured_at DESC, answer_id DESC", conn)
        citations = pd.read_sql_query(
            "SELECT * FROM citations ORDER BY cited_at DESC, answer_id DESC, source_position ASC",
            conn,
        )
        citation_audits = pd.read_sql_query("SELECT * FROM citation_audits", conn)
        deep_assessments = pd.read_sql_query("SELECT * FROM citation_deep_assessments", conn)
        gt_articles = pd.read_sql_query(
            "SELECT * FROM gt_articles ORDER BY published_at DESC, article_id DESC", conn
        )
        topic_weights = pd.read_sql_query(
            "SELECT * FROM topic_weight_snapshots ORDER BY snapshot_date DESC, calculated_weight DESC", conn
        )
    if platform:
        platform_aliases = {platform}
        if platform == "ChatGPT":
            platform_aliases.add("ChatGPT via ZenMux")
        runs = runs[runs["platform"].isin(platform_aliases)].copy()
        answers = answers[answers["ai_platform"].isin(platform_aliases)].copy()
        runs.loc[:, "platform"] = platform
        answers.loc[:, "ai_platform"] = platform
        answer_ids = set(answers["answer_id"].tolist())
        citations = citations[citations["answer_id"].isin(answer_ids)].copy()
        citation_audits = citation_audits[citation_audits["citation_id"].isin(citations["citation_id"])].copy()
    if not citations.empty:
        citations = citations.merge(citation_audits, on="citation_id", how="left")
        citations = citations.merge(deep_assessments, on="citation_id", how="left")
        article_word_counts = pd.to_numeric(citations["article_word_count"], errors="coerce").fillna(0)
        citations["valid_evidence"] = (
            citations["access_status"].isin(["verified", "verified_tls_fallback"])
            & (article_word_counts >= 80)
        )
    else:
        citations["valid_evidence"] = pd.Series(dtype=bool)
    prompts = load_pilot_prompts()
    sources = _build_source_frame(answers, citations)
    latest_weights = _latest_topic_weights(topic_weights)
    content_matches = build_content_matches(sources)
    scores, topic_authority = build_real_scores(
        answers,
        sources,
        latest_weights,
        content_matches,
    )
    topic_diagnostics = build_topic_diagnostics(
        answers,
        sources,
        content_matches,
        topic_authority,
        latest_weights,
    )
    prompt_outcomes = build_prompt_outcomes(answers, sources)
    daily_trend = build_daily_trend(answers, sources, latest_weights)
    return {
        "runs": runs,
        "prompts": prompts,
        "answers": answers,
        "citations": citations,
        "citation_audits": citation_audits,
        "deep_assessments": deep_assessments,
        "gt_articles": gt_articles,
        "topic_weights": topic_weights,
        "sources": sources,
        "scores": scores,
        "topic_authority": topic_authority,
        "content_matches": content_matches,
        "topic_diagnostics": topic_diagnostics,
        "prompt_outcomes": prompt_outcomes,
        "daily_trend": daily_trend,
    }


def real_summary(data: dict[str, pd.DataFrame]) -> dict[str, Any]:
    answers = data["answers"]
    successful = answers[answers["status"] == "success"] if not answers.empty else answers
    citations = data["citations"]
    completed_runs = data["runs"][data["runs"]["status"].isin(["completed", "completed_with_errors"])]
    captured_dates = pd.to_datetime(successful["captured_at"], errors="coerce").dt.date if not successful.empty else []
    return {
        "completed_runs": int(len(completed_runs)),
        "monitoring_days": int(pd.Series(captured_dates).nunique()) if len(captured_dates) else 0,
        "successful_answers": int(len(successful)),
        "citations": int(len(citations)),
        "verified_citations": int(citations["valid_evidence"].sum()) if "valid_evidence" in citations else 0,
        "content_extracted": int((citations["article_word_count"].fillna(0) >= 80).sum()) if "article_word_count" in citations else 0,
        "unique_domains": int(citations["domain"].nunique()) if not citations.empty else 0,
        "last_captured_at": successful["captured_at"].max() if not successful.empty else "",
    }


def build_real_scores(
    answers: pd.DataFrame,
    sources: pd.DataFrame,
    strategic_weights: dict[str, float] | None = None,
    content_matches: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    successful = answers[answers["status"] == "success"].copy() if not answers.empty else answers.copy()
    if successful.empty or sources.empty:
        return _empty_scores(), _empty_topic_authority()

    weights = strategic_weights or STRATEGIC_WEIGHTS
    total_answers = successful["answer_id"].nunique()
    answer_ids = set(successful["answer_id"])
    sources = sources[sources["answer_id"].isin(answer_ids)].copy()
    matches = content_matches if content_matches is not None else build_content_matches(sources)
    verified_matches = _valid_sources(matches)
    media_names = sources["media_name"].drop_duplicates().tolist()
    topic_rows: list[dict[str, Any]] = []
    score_rows: list[dict[str, Any]] = []

    for media_name in media_names:
        media_sources = sources[sources["media_name"] == media_name]
        verified_sources = _valid_sources(media_sources)
        media_matches = verified_matches[verified_matches["media_name"] == media_name]
        cited_prompt_count = int(media_sources["answer_id"].nunique())
        top3_prompt_count = int(media_sources[media_sources["source_position"] <= 3]["answer_id"].nunique())
        verified_prompt_count = int(verified_sources["answer_id"].nunique())
        supported_prompt_count = int(
            media_matches[media_matches["content_match_score"] >= 45]["answer_id"].nunique()
        ) if not media_matches.empty else 0
        visibility = _pct(cited_prompt_count, total_answers)
        top3_rate = _pct(top3_prompt_count, total_answers)
        evidence_rate = _pct(verified_prompt_count, total_answers)
        supported_prompt_rate = _pct(supported_prompt_count, total_answers)
        content_support = (
            float(media_matches["content_match_score"].mean())
            if not media_matches.empty
            else 0.0
        )

        media_topic_rows: list[dict[str, Any]] = []
        for topic in successful["topic"].drop_duplicates().tolist():
            topic_answers = successful[
                (successful["topic"] == topic)
                & (successful["query_intent"].isin(CORE_QUERY_INTENTS))
            ]
            topic_sources = media_sources[
                (media_sources["topic"] == topic)
                & (media_sources["query_intent"].isin(CORE_QUERY_INTENTS))
            ]
            topic_verified = _valid_sources(topic_sources)
            topic_matches = media_matches[
                (media_matches["topic"] == topic)
                & (media_matches["query_intent"].isin(CORE_QUERY_INTENTS))
            ]
            topic_coverage = _pct(topic_sources["answer_id"].nunique(), topic_answers["answer_id"].nunique())
            topic_top3_rate = _pct(
                topic_sources[topic_sources["source_position"] <= 3]["answer_id"].nunique(),
                topic_answers["answer_id"].nunique(),
            )
            topic_evidence_rate = _pct(
                topic_verified["answer_id"].nunique(),
                topic_answers["answer_id"].nunique(),
            )
            topic_content_support = (
                float(topic_matches["content_match_score"].mean())
                if not topic_matches.empty
                else 0.0
            )
            # This internal value only supports status and priority rules. It is not a public score.
            authority = topic_coverage * 0.30 + topic_top3_rate * 0.50 + topic_evidence_rate * 0.20
            row = {
                "media_name": media_name,
                "topic": topic,
                "topic_coverage": round(float(topic_coverage), 1),
                "topic_source_preference": round(float(topic_top3_rate), 1),
                "topic_content_evidence_rate": round(float(topic_evidence_rate), 1),
                "topic_content_support_score": round(float(topic_content_support), 1),
                "topic_authority_score": round(float(authority), 1),
                "strategic_weight": float(weights.get(topic, 0)),
                "status": _topic_status(authority),
            }
            topic_rows.append(row)
            media_topic_rows.append(row)

        score_rows.append(
            {
                "media_name": media_name,
                "total_prompt_count": int(total_answers),
                "cited_prompt_count": cited_prompt_count,
                "top3_prompt_count": top3_prompt_count,
                "ai_visibility": round(float(visibility), 1),
                "top3_rate": round(float(top3_rate), 1),
                "citation_count": int(len(media_sources)),
                "average_position": round(float(media_sources["source_position"].mean()), 2),
                "verified_prompt_count": verified_prompt_count,
                "verified_citation_count": int(len(verified_sources)),
                "content_evidence_rate": round(float(evidence_rate), 1),
                "supported_prompt_count": supported_prompt_count,
                "supported_prompt_rate": round(float(supported_prompt_rate), 1),
                "content_support_score": round(float(content_support), 1),
            }
        )

    scores = pd.DataFrame(score_rows)
    # This ordering value is never displayed; the report stays focused on the four observable metrics.
    scores["_report_order"] = (
        scores["top3_rate"] * 0.50
        + scores["ai_visibility"] * 0.25
        + scores["content_evidence_rate"] * 0.20
        + scores["content_support_score"] * 0.05
    )
    scores = scores.sort_values(
        ["_report_order", "top3_rate", "ai_visibility", "content_evidence_rate"],
        ascending=[False, False, False, False],
    ).drop(columns="_report_order").reset_index(drop=True)
    topic_authority = pd.DataFrame(topic_rows)
    return scores, topic_authority


def build_daily_trend(
    answers: pd.DataFrame,
    sources: pd.DataFrame,
    strategic_weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    successful = answers[answers["status"] == "success"].copy() if not answers.empty else answers.copy()
    if successful.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "runs",
                "answers",
                "citation_count",
                "coverage_rate",
                "organic_top3_rate",
                "content_evidence_rate",
                "content_support_score",
                "avg_position",
            ]
        )
    successful["date"] = pd.to_datetime(successful["captured_at"], errors="coerce").dt.strftime("%Y-%m-%d")
    source_dates = sources.merge(successful[["answer_id", "date"]], on="answer_id", how="left", suffixes=("", "_answer"))
    rows: list[dict[str, Any]] = []
    for date, day_answers in successful.groupby("date"):
        day_sources = source_dates[source_dates["date"] == date]
        target = day_sources[day_sources["media_name"] == TARGET_MEDIA]
        verified_target = _valid_sources(target)
        coverage = _pct(target["answer_id"].nunique(), day_answers["answer_id"].nunique())
        top3_rate = _pct(
            target[target["source_position"] <= 3]["answer_id"].nunique(),
            day_answers["answer_id"].nunique(),
        )
        evidence_rate = _pct(
            verified_target["answer_id"].nunique(),
            day_answers["answer_id"].nunique(),
        )
        target_matches = _valid_sources(build_content_matches(verified_target))
        content_support = (
            float(target_matches["content_match_score"].mean())
            if not target_matches.empty
            else 0.0
        )
        rows.append(
            {
                "date": date,
                "runs": int(day_answers["run_id"].nunique()),
                "answers": int(day_answers["answer_id"].nunique()),
                "citation_count": int(len(target)),
                "coverage_rate": round(float(coverage), 1),
                "organic_top3_rate": round(float(top3_rate), 1),
                "content_evidence_rate": round(float(evidence_rate), 1),
                "content_support_score": round(float(content_support), 1),
                "avg_position": round(float(target["source_position"].mean()), 2) if not target.empty else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values("date")


def build_content_matches(sources: pd.DataFrame) -> pd.DataFrame:
    """Compare each AI answer with the extracted full text of its cited article."""
    columns = list(sources.columns) + [
        "query_match_score",
        "answer_match_score",
        "support_coverage",
        "topic_match_score",
        "content_match_score",
        "match_level",
        "evidence_scope",
        "best_matching_passage",
    ]
    if sources.empty:
        return pd.DataFrame(columns=columns)

    matches = sources.copy().reset_index(drop=True)
    analyses = matches.apply(_full_text_alignment, axis=1, result_type="expand")
    for column in analyses.columns:
        matches[column] = analyses[column]
    return matches[columns]


def build_topic_diagnostics(
    answers: pd.DataFrame,
    sources: pd.DataFrame,
    content_matches: pd.DataFrame,
    topic_authority: pd.DataFrame,
    strategic_weights: dict[str, float] | None = None,
    target_media: str = TARGET_MEDIA,
) -> pd.DataFrame:
    columns = [
        "topic",
        "prompt_count",
        "target_cited_prompts",
        "target_top3_prompts",
        "competitor_top3_prompts",
        "topic_coverage",
        "topic_source_preference",
        "content_evidence_prompts",
        "content_evidence_rate",
        "content_match_score",
        "topic_authority_score",
        "dominant_competitor",
        "competition_gap",
        "status",
        "sample_strength",
        "priority",
        "finding",
        "recommendation",
    ]
    successful = answers[answers["status"] == "success"].copy() if not answers.empty else answers.copy()
    if "valid_evidence" in content_matches:
        content_matches = content_matches[content_matches["valid_evidence"]].copy()
    configured_topics = load_pilot_prompts()["topic"].drop_duplicates().tolist()
    observed_topics = successful["topic"].drop_duplicates().tolist() if not successful.empty else []
    topics = list(dict.fromkeys(configured_topics + observed_topics))
    rows: list[dict[str, Any]] = []

    for topic in topics:
        topic_answers = successful[
            (successful["topic"] == topic)
            & (successful["query_intent"].isin(CORE_QUERY_INTENTS))
        ]
        topic_sources = sources[
            (sources["topic"] == topic)
            & (sources["query_intent"].isin(CORE_QUERY_INTENTS))
        ]
        target_sources = topic_sources[topic_sources["media_name"] == target_media]
        verified_target_sources = _valid_sources(target_sources)
        competitor_sources = topic_sources[topic_sources["media_name"] != target_media]
        competitor_top3 = competitor_sources[competitor_sources["source_position"] <= 3]
        prompt_count = int(topic_answers["answer_id"].nunique())
        cited_prompts = int(target_sources["answer_id"].nunique())
        target_top3 = int(target_sources[target_sources["source_position"] <= 3]["answer_id"].nunique())
        competitor_top3_count = int(competitor_top3["answer_id"].nunique())
        coverage = _pct(cited_prompts, prompt_count)
        preference = _pct(target_top3, prompt_count)
        evidence_prompts = int(verified_target_sources["answer_id"].nunique())
        evidence_rate = _pct(evidence_prompts, prompt_count)
        match_rows = content_matches[
            (content_matches["topic"] == topic)
            & (content_matches["media_name"] == target_media)
            & (content_matches["query_intent"].isin(CORE_QUERY_INTENTS))
        ]
        content_match = float(match_rows["content_match_score"].mean()) if not match_rows.empty else 0.0
        authority_row = topic_authority[
            (topic_authority["topic"] == topic)
            & (topic_authority["media_name"] == target_media)
        ]
        authority = (
            float(authority_row.iloc[0]["topic_authority_score"])
            if not authority_row.empty
            else coverage * 0.30 + preference * 0.50 + evidence_rate * 0.20
        )
        dominant = ""
        if not competitor_top3.empty:
            dominant = str(
                competitor_top3.groupby("media_name")
                .agg(top3_prompts=("answer_id", "nunique"), avg_position=("source_position", "mean"))
                .sort_values(["top3_prompts", "avg_position"], ascending=[False, True])
                .index[0]
            )
        status = _topic_status(authority) if prompt_count else "No Data"
        sample_strength = (
            "较稳定的阶段性结论" if prompt_count >= 30
            else "方向性判断" if prompt_count >= 10
            else "小样本信号" if prompt_count >= 5
            else "证据不足"
        )
        weights = strategic_weights or STRATEGIC_WEIGHTS
        priority = _topic_priority(authority, prompt_count, float(weights.get(topic, 0)))
        finding = _topic_finding(topic, prompt_count, coverage, preference, content_match, dominant)
        recommendation = _topic_recommendation(
            topic,
            prompt_count,
            coverage,
            preference,
            content_match,
            dominant,
        )
        rows.append(
            {
                "topic": topic,
                "prompt_count": prompt_count,
                "target_cited_prompts": cited_prompts,
                "target_top3_prompts": target_top3,
                "competitor_top3_prompts": competitor_top3_count,
                "topic_coverage": round(float(coverage), 1),
                "topic_source_preference": round(float(preference), 1),
                "content_evidence_prompts": evidence_prompts,
                "content_evidence_rate": round(float(evidence_rate), 1),
                "content_match_score": round(float(content_match), 1),
                "topic_authority_score": round(float(authority), 1),
                "dominant_competitor": dominant,
                "competition_gap": competitor_top3_count - target_top3,
                "status": status,
                "sample_strength": sample_strength,
                "priority": priority,
                "finding": finding,
                "recommendation": recommendation,
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["prompt_count", "topic_authority_score"], ascending=[False, False]
    )


def build_prompt_outcomes(
    answers: pd.DataFrame,
    sources: pd.DataFrame,
    target_media: str = TARGET_MEDIA,
) -> pd.DataFrame:
    columns = [
        "answer_id",
        "captured_at",
        "topic",
        "query_intent",
        "question",
        "winner",
        "target_position",
        "best_competitor",
        "best_competitor_position",
        "competition_result",
        "citation_count",
    ]
    successful = answers[answers["status"] == "success"].copy() if not answers.empty else answers.copy()
    rows: list[dict[str, Any]] = []
    for answer in successful.to_dict("records"):
        answer_sources = sources[sources["answer_id"] == answer["answer_id"]].sort_values("source_position")
        target = answer_sources[answer_sources["media_name"] == target_media]
        competitors = answer_sources[answer_sources["media_name"] != target_media]
        target_position = int(target["source_position"].min()) if not target.empty else None
        best_competitor = str(competitors.iloc[0]["media_name"]) if not competitors.empty else ""
        best_competitor_position = int(competitors.iloc[0]["source_position"]) if not competitors.empty else None
        winner = str(answer_sources.iloc[0]["media_name"]) if not answer_sources.empty else ""
        if target_position == 1:
            result = "GT Win"
        elif target_position is not None and target_position <= 3:
            result = "GT Top3"
        elif target_position is not None:
            result = "Weak Citation"
        elif best_competitor_position is not None and best_competitor_position <= 3:
            result = "Competitor Win"
        else:
            result = "No Effective Competition"
        rows.append(
            {
                "answer_id": int(answer["answer_id"]),
                "captured_at": answer["captured_at"],
                "topic": answer["topic"],
                "query_intent": answer["query_intent"],
                "question": answer["question"],
                "winner": winner,
                "target_position": target_position,
                "best_competitor": best_competitor,
                "best_competitor_position": best_competitor_position,
                "competition_result": result,
                "citation_count": int(len(answer_sources)),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def media_metadata(media_name: str) -> dict[str, str]:
    for item in MEDIA:
        if item["media_name"] == media_name:
            return {
                "domain": str(item["domain"]),
                "cluster": str(item["cluster"]),
            }
    return {"domain": "", "cluster": "Other Web Source"}


def _build_source_frame(answers: pd.DataFrame, citations: pd.DataFrame) -> pd.DataFrame:
    if answers.empty or citations.empty:
        return pd.DataFrame(
            columns=[
                "record_id",
                "answer_id",
                "run_id",
                "prompt_id",
                "topic",
                "query_intent",
                "language",
                "ai_platform",
                "media_name",
                "domain",
                "source_position",
                "is_top3",
                "cluster",
                "source_url",
                "source_title",
                "captured_at",
            ]
        )
    answer_fields = answers[
        ["answer_id", "topic", "query_intent", "language", "ai_platform", "question", "answer_text", "captured_at"]
    ]
    frame = citations.merge(answer_fields, on="answer_id", how="inner")
    frame = frame.rename(columns={"citation_id": "record_id"})
    frame["is_top3"] = frame["is_top3"].astype(bool)
    return frame


def _connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(db_path), timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _position_score(position: int) -> float:
    if int(position) == 1:
        return 100.0
    if int(position) == 2:
        return 80.0
    if int(position) == 3:
        return 60.0
    return 30.0


def _pct(numerator: int, denominator: int) -> float:
    return numerator / denominator * 100 if denominator else 0.0


def _valid_sources(sources: pd.DataFrame) -> pd.DataFrame:
    if sources.empty:
        return sources.copy()
    if "valid_evidence" not in sources:
        return sources.copy()
    return sources[sources["valid_evidence"].fillna(False).astype(bool)].copy()


def _latest_topic_weights(snapshots: pd.DataFrame) -> dict[str, float]:
    if snapshots.empty:
        return STRATEGIC_WEIGHTS.copy()
    latest_date = snapshots["snapshot_date"].max()
    latest = snapshots[snapshots["snapshot_date"] == latest_date]
    weights = {
        str(row["topic"]): float(row["calculated_weight"])
        for row in latest.to_dict("records")
    }
    return weights or STRATEGIC_WEIGHTS.copy()


def _similarity_score(similarity: float) -> float:
    value = max(0.0, min(1.0, float(similarity)))
    return value**0.5 * 100


def _topic_match_score(row: pd.Series, article_text: str = "") -> float:
    text = f"{row.get('article_title', '')} {row.get('source_title', '')} {article_text}".lower()
    tokens = [
        token.lower()
        for token in str(row.get("topic", "")).replace("/", " ").replace("&", " ").split()
        if token.lower() not in {"china", "and", "ai"} and len(token) > 2
    ]
    if "china" in str(row.get("topic", "")).lower():
        tokens.append("china")
    if not tokens:
        return 0.0
    return round(sum(token in text for token in set(tokens)) / len(set(tokens)) * 100, 1)


def _full_text_alignment(row: pd.Series) -> pd.Series:
    valid = bool(row.get("valid_evidence", False))
    article_text = str(row.get("article_text") or "").strip()
    access_status = str(row.get("access_status") or "not_audited")
    if not valid or len(article_text.split()) < 80:
        return pd.Series(
            {
                "query_match_score": pd.NA,
                "answer_match_score": pd.NA,
                "support_coverage": pd.NA,
                "topic_match_score": pd.NA,
                "content_match_score": pd.NA,
                "match_level": "Unverified",
                "evidence_scope": access_status,
                "best_matching_passage": "",
            }
        )

    question = f"{row.get('question', '')} {row.get('topic', '')}".strip()
    answer = str(row.get("answer_text") or "").strip()
    article_sentences = _split_sentences(article_text, max_sentences=500)
    answer_sentences = _split_sentences(answer, max_sentences=80)
    if not article_sentences or not answer_sentences:
        return pd.Series(
            {
                "query_match_score": 0.0,
                "answer_match_score": 0.0,
                "support_coverage": 0.0,
                "topic_match_score": _topic_match_score(row, article_text),
                "content_match_score": 0.0,
                "match_level": "Low Match",
                "evidence_scope": "全文已抓取但无法切分",
                "best_matching_passage": "",
            }
        )

    corpus = [question, *answer_sentences, *article_sentences]
    try:
        vectors = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            max_features=12000,
            sublinear_tf=True,
        ).fit_transform(corpus)
        question_vector = vectors[0]
        answer_vectors = vectors[1 : 1 + len(answer_sentences)]
        article_vectors = vectors[1 + len(answer_sentences) :]
        query_raw = float(cosine_similarity(question_vector, article_vectors).max())
        sentence_similarity = cosine_similarity(answer_vectors, article_vectors)
        best_scores = sentence_similarity.max(axis=1)
        best_indices = sentence_similarity.argmax(axis=1)
        support_coverage = float((best_scores >= 0.18).mean() * 100)
        mean_support = float(best_scores.mean())
        answer_support = support_coverage * 0.65 + _similarity_score(mean_support) * 0.35
        strongest_answer_index = int(best_scores.argmax())
        best_passage = article_sentences[int(best_indices[strongest_answer_index])]
    except ValueError:
        query_raw = 0.0
        support_coverage = 0.0
        answer_support = 0.0
        best_passage = ""
    query_score = _similarity_score(query_raw)
    topic_score = _topic_match_score(row, article_text)
    content_score = query_score * 0.30 + answer_support * 0.55 + topic_score * 0.15
    deep_score = row.get("support_score")
    has_deep_review = pd.notna(deep_score)
    final_score = float(deep_score) if has_deep_review else content_score
    return pd.Series(
        {
            "query_match_score": round(query_score, 1),
            "answer_match_score": round(answer_support, 1),
            "support_coverage": round(support_coverage, 1),
            "topic_match_score": round(topic_score, 1),
            "content_match_score": round(final_score, 1),
            "match_level": _match_level(final_score),
            "evidence_scope": (
                f"LLM 逐项主张核验 + 文章全文 {len(article_text.split())} 词"
                if has_deep_review
                else f"逐句检索匹配 + 文章全文 {len(article_text.split())} 词"
            ),
            "best_matching_passage": best_passage[:800],
        }
    )


def _split_sentences(text: str, max_sentences: int) -> list[str]:
    raw_parts = re.split(r"(?<=[.!?。！？])\s+|\n+", text)
    sentences = [re.sub(r"\s+", " ", part).strip() for part in raw_parts]
    return [sentence for sentence in sentences if len(sentence.split()) >= 6][:max_sentences]


def _match_level(score: float) -> str:
    if score >= 70:
        return "High Match"
    if score >= 45:
        return "Medium Match"
    return "Low Match"


def _topic_priority(authority: float, prompt_count: int, strategic_weight: float) -> str:
    if prompt_count == 0:
        return "Collect First"
    if authority < 40 and strategic_weight > 0:
        return "High Priority"
    if authority < 60 or strategic_weight > 0.10:
        return "Medium Priority"
    return "Maintain"


def _topic_finding(
    topic: str,
    prompt_count: int,
    coverage: float,
    preference: float,
    content_match: float,
    dominant_competitor: str,
) -> str:
    if prompt_count == 0:
        return "尚未完成该议题的真实采集，当前不能判断媒体权威表现。"
    competitor_note = f"，主要 Top3 竞品为 {dominant_competitor}" if dominant_competitor else ""
    if coverage == 0:
        return f"在 {prompt_count} 条自然查询中目标媒体尚未被引用{competitor_note}。"
    return (
        f"AI 引用覆盖率 {coverage:.1f}%，全部问题中的 Top3 率 {preference:.1f}%，"
        f"引用内容匹配度 {content_match:.1f} 分{competitor_note}。"
    )


def _topic_recommendation(
    topic: str,
    prompt_count: int,
    coverage: float,
    preference: float,
    content_match: float,
    dominant_competitor: str,
) -> str:
    if prompt_count == 0:
        return "先完成该 Topic 的固定 Prompt 采集；样本不足时不做内容策略结论。"
    actions: list[str] = []
    if coverage < 35:
        actions.append("补齐英文常青解释稿、事件时间线和可被搜索发现的 Topic 专页")
    if preference < 60:
        actions.append("在开头增加可直接引用的事实摘要、关键数据和具名专家观点")
    if 0 < content_match < 50:
        actions.append("统一标题、摘要与核心问题的实体和关键词，并让结论直接回答用户问题")
    if dominant_competitor:
        actions.append(f"逐条拆解 {dominant_competitor} 的 Top3 胜出页面，补强其领先的事实与语境")
    if not actions:
        actions.append("保持更新频率，并围绕已胜出的 Prompt 扩展相邻问题和多语种版本")
    return "；".join(actions) + "。"


def _weighted_topic_score(topic_frame: pd.DataFrame) -> float:
    strategic = topic_frame[topic_frame["strategic_weight"] > 0].copy()
    if strategic.empty:
        return 0.0
    total_weight = float(strategic["strategic_weight"].sum())
    return float((strategic["topic_authority_score"] * strategic["strategic_weight"]).sum() / total_weight)


def _topic_status(score: float) -> str:
    if score >= 80:
        return "Strong Advantage"
    if score >= 60:
        return "Stable Advantage"
    if score >= 40:
        return "Needs Improvement"
    return "Clear Weakness"


def _empty_scores() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "media_name",
            "total_prompt_count",
            "cited_prompt_count",
            "top3_prompt_count",
            "ai_visibility",
            "top3_rate",
            "citation_count",
            "average_position",
            "verified_prompt_count",
            "verified_citation_count",
            "content_evidence_rate",
            "supported_prompt_count",
            "supported_prompt_rate",
            "content_support_score",
        ]
    )


def _empty_topic_authority() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "media_name",
            "topic",
            "topic_coverage",
            "topic_source_preference",
            "topic_content_evidence_rate",
            "topic_content_support_score",
            "topic_authority_score",
            "strategic_weight",
            "status",
        ]
    )
