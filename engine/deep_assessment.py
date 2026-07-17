from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.real_collector import DEFAULT_ZENMUX_MODEL, ZENMUX_BASE_URL, _post_json, load_local_env
from engine.real_store import DEFAULT_DB_PATH, initialize_database


def assess_citations(
    db_path: Path | str = DEFAULT_DB_PATH,
    run_id: str | None = None,
    media_name: str = "Global Times",
    model: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    load_local_env()
    api_key = os.getenv("CHATGPT_API_KEY", os.getenv("ZENMUX_API_KEY", "")).strip()
    if not api_key:
        raise ValueError("Missing ChatGPT API key")
    selected_model = model or os.getenv("CHATGPT_MODEL", os.getenv("ZENMUX_MODEL", DEFAULT_ZENMUX_MODEL)).strip() or DEFAULT_ZENMUX_MODEL
    initialize_database(db_path)
    with sqlite3.connect(Path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT c.citation_id, c.run_id, c.source_url, c.source_position,
                   a.question, a.answer_text, ca.article_title, ca.article_text
            FROM citations c
            JOIN answers a ON a.answer_id = c.answer_id
            JOIN citation_audits ca ON ca.citation_id = c.citation_id
            LEFT JOIN citation_deep_assessments da ON da.citation_id = c.citation_id
            WHERE c.media_name = ?
              AND ca.access_status IN ('verified', 'verified_tls_fallback')
              AND ca.article_word_count >= 80
              AND (? IS NULL OR c.run_id = ?)
              AND (? = 1 OR da.citation_id IS NULL)
            ORDER BY c.citation_id
            """,
            (media_name, run_id, run_id, int(force)),
        ).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        assessment = _judge(row, api_key, selected_model)
        results.append({"citation_id": row["citation_id"], **assessment})
    _save(results, selected_model, db_path)
    return {
        "assessed": len(results),
        "media_name": media_name,
        "model": selected_model,
        "average_support_score": round(
            sum(float(item["support_score"]) for item in results) / len(results), 1
        ) if results else None,
    }


def _judge(row: sqlite3.Row, api_key: str, model: str) -> dict[str, Any]:
    article = str(row["article_text"])[:30000]
    answer = str(row["answer_text"])[:16000]
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an evidence auditor. Compare the AI answer only against the supplied article. "
                    "Break the answer into factual claims and decide which claims this article supports, does not support, "
                    "or contradicts. Do not use outside knowledge. Return strict JSON with keys support_score (0-100), "
                    "supported_claims (array), unsupported_claims (array), contradictions (array), and rationale (string). "
                    "A high score requires the article to support most material claims, not merely discuss the same topic."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"QUESTION:\n{row['question']}\n\nAI ANSWER:\n{answer}\n\n"
                    f"CITED ARTICLE TITLE:\n{row['article_title']}\n\nCITED ARTICLE FULL TEXT:\n{article}"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    base_url = os.getenv("CHATGPT_BASE_URL", os.getenv("ZENMUX_BASE_URL", ZENMUX_BASE_URL)).strip().rstrip("/") or ZENMUX_BASE_URL
    response, _ = _post_json(
        endpoint=f"{base_url}/chat/completions",
        payload=payload,
        api_key=api_key,
        provider_name="ChatGPT",
    )
    content = str(response["choices"][0]["message"]["content"])
    parsed = _parse_json(content)
    score = max(0.0, min(100.0, float(parsed.get("support_score", 0))))
    return {
        "support_score": round(score, 1),
        "supported_claims": _as_list(parsed.get("supported_claims")),
        "unsupported_claims": _as_list(parsed.get("unsupported_claims")),
        "contradictions": _as_list(parsed.get("contradictions")),
        "rationale": str(parsed.get("rationale", ""))[:4000],
        "raw": parsed,
    }


def _parse_json(content: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise RuntimeError("Deep assessment did not return JSON")
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise RuntimeError("Deep assessment JSON must be an object")
    return value


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:1000] for item in value]


def _save(results: list[dict[str, Any]], model: str, db_path: Path | str) -> None:
    assessed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with sqlite3.connect(Path(db_path)) as conn:
        for item in results:
            conn.execute(
                """
                INSERT INTO citation_deep_assessments (
                    citation_id, model, assessed_at, support_score, supported_claims_json,
                    unsupported_claims_json, contradictions_json, rationale, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(citation_id) DO UPDATE SET
                    model=excluded.model, assessed_at=excluded.assessed_at,
                    support_score=excluded.support_score,
                    supported_claims_json=excluded.supported_claims_json,
                    unsupported_claims_json=excluded.unsupported_claims_json,
                    contradictions_json=excluded.contradictions_json,
                    rationale=excluded.rationale, raw_json=excluded.raw_json
                """,
                (
                    item["citation_id"], model, assessed_at, item["support_score"],
                    json.dumps(item["supported_claims"], ensure_ascii=False),
                    json.dumps(item["unsupported_claims"], ensure_ascii=False),
                    json.dumps(item["contradictions"], ensure_ascii=False),
                    item["rationale"], json.dumps(item["raw"], ensure_ascii=False),
                ),
            )
        conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run claim-level answer/article support assessment")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--media", default="Global Times")
    parser.add_argument("--model", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = assess_citations(run_id=args.run_id, media_name=args.media, model=args.model, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
