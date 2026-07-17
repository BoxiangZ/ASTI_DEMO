from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from engine.config import TOPICS
from engine.gt_corpus import classify_article_topics
from engine.real_collector import (
    DEFAULT_ZENMUX_MODEL,
    ZENMUX_BASE_URL,
    _post_json,
    canonicalize_url,
    load_local_env,
)
from engine.real_store import DEFAULT_DB_PATH, initialize_database


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_PATH = PROJECT_ROOT / "config" / "researched_longtails.json"
RAW_RESEARCH_DIR = PROJECT_ROOT / "data" / "prompt_research_raw"
HIGH_VALUE_PATTERN = re.compile(
    r"\b(first|new|debut|unveil|launch|test|trial|enter service|exclusive|on the spot|"
    r"type\s*\d+|submarine|destroyer|warship|fighter|missile|vessel|robot|chip|surgery|"
    r"patrol|exercise|drill|delegation|visit|agreement|arbitration|cross-strait)\b|\d",
    re.IGNORECASE,
)

TOPIC_RESEARCH_GUIDANCE = {
    "China Economy": "Prefer newly released official data, sector-level changes, and measurable policy effects.",
    "China Technology/AI": "Prefer named products or models, first demonstrations, test results, and concrete capability limits.",
    "China Diplomacy": "Prefer concrete visits, agreements, protests, joint actions, and first-hand official responses over general positioning.",
    "China Military": (
        "At least two questions must concern a named platform, model, test, deployment, or newly revealed capability. "
        "Prioritize ships, aircraft, missiles, exercises, and observable readiness indicators."
    ),
    "US-China Relations": "Prefer specific tariff, trade, technology-control, meeting, or Taiwan-related developments with measurable consequences.",
    "Taiwan Strait": "Prefer named exercises, vessels, drones, arms activity, patrol patterns, or concrete cross-Strait exchanges.",
    "South China Sea": "Prefer named shoals, vessels, patrols, legal evidence, protests, and observable maritime actions.",
    "China EV": "Prefer named vehicle models, launch specifications, delivery or sales data, overseas market moves, and battery advances.",
}


def research_longtail_prompts(
    db_path: Path | str = DEFAULT_DB_PATH,
    model: str | None = None,
    recent_days: int = 21,
    per_topic: int = 4,
    selected_topics: list[str] | None = None,
    use_raw: bool = False,
) -> dict[str, Any]:
    load_local_env()
    api_key = os.getenv("CHATGPT_API_KEY", os.getenv("ZENMUX_API_KEY", "")).strip()
    if not api_key and not use_raw:
        raise ValueError("Missing ChatGPT API key")
    selected_model = model or os.getenv("CHATGPT_MODEL", os.getenv("ZENMUX_MODEL", DEFAULT_ZENMUX_MODEL)).strip() or DEFAULT_ZENMUX_MODEL
    articles = _load_articles(db_path, recent_days)
    existing_topics: dict[str, list[dict[str, Any]]] = {}
    if RESEARCH_PATH.exists():
        try:
            existing_topics = json.loads(RESEARCH_PATH.read_text(encoding="utf-8")).get("topics", {})
        except (OSError, json.JSONDecodeError, AttributeError):
            existing_topics = {}
    topics: dict[str, list[dict[str, Any]]] = dict(existing_topics)
    errors: dict[str, str] = {}
    run_topics = selected_topics or TOPICS
    for topic in run_topics:
        if topic not in TOPICS:
            raise ValueError(f"Unknown topic: {topic}")
        candidates = _topic_candidates(topic, articles, limit=18)
        try:
            if use_raw:
                raw_path = RAW_RESEARCH_DIR / (_raw_name(topic))
                if not raw_path.exists():
                    raise FileNotFoundError(f"Missing raw prompt research: {raw_path}")
                parsed = _parse_json(raw_path.read_text(encoding="utf-8"))
                generated = _normalize_generated_items(candidates, parsed, per_topic)
            else:
                generated = _generate_topic_questions(
                    topic=topic,
                    candidates=candidates,
                    per_topic=per_topic,
                    api_key=api_key,
                    model=selected_model,
                )
            if generated:
                topics[topic] = generated
            elif topic not in topics:
                topics[topic] = []
        except Exception as exc:
            errors[topic] = f"{type(exc).__name__}: {exc}"[:500]
            topics.setdefault(topic, existing_topics.get(topic, []))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": selected_model,
        "recent_days": recent_days,
        "method": "full-text candidate research + model event synthesis",
        "topics": topics,
        "errors": errors,
    }
    RESEARCH_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    from engine.topic_strategy import refresh_prompt_config_from_corpus

    refresh_prompt_config_from_corpus()
    return payload


def _load_articles(db_path: Path | str, recent_days: int) -> list[dict[str, Any]]:
    initialize_database(db_path)
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=recent_days)).isoformat()
    with sqlite3.connect(Path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT article_url, title, published_at, source_section, article_text,
                   article_word_count, classification_score
            FROM gt_articles
            WHERE access_status IN ('verified', 'verified_tls_fallback')
              AND article_word_count >= 80
              AND published_at >= ?
            ORDER BY published_at DESC
            """,
            (cutoff,),
        ).fetchall()
    return [dict(row) for row in rows]


def _topic_candidates(
    topic: str,
    articles: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for article in articles:
        if topic not in classify_article_topics(
            str(article["title"]),
            str(article["article_text"]),
            str(article["source_section"]),
        ):
            continue
        title = str(article["title"])
        intelligence_score = len(HIGH_VALUE_PATTERN.findall(title)) * 8
        intelligence_score += min(int(article["article_word_count"]) / 250, 8)
        if re.search(r"exclusive|on the spot|reporter|learned", str(article["article_text"])[:1600], re.I):
            intelligence_score += 10
        candidates.append(
            {
                "url": article["article_url"],
                "title": title,
                "published_at": str(article["published_at"]),
                "section": article["source_section"],
                "lead": _clean_lead(str(article["article_text"]))[:520],
                "intelligence_score": round(float(intelligence_score), 1),
            }
        )
    return sorted(candidates, key=lambda item: (item["intelligence_score"], item["published_at"]), reverse=True)[:limit]


def _generate_topic_questions(
    topic: str,
    candidates: list[dict[str, Any]],
    per_topic: int,
    api_key: str,
    model: str,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    candidate_json = json.dumps(candidates, ensure_ascii=False)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You design realistic AI-search monitoring questions from a supplied news corpus. "
                    "Find concrete, high-information developments: named equipment/models, first deployments, "
                    "tests, launches, field reporting, exclusive details, official data, or a theme covered repeatedly. "
                    "Never copy an article title into a question. Never mention Global Times, a publisher, an article, "
                    "or a source. Extract the underlying fact and write a natural standalone question a knowledgeable "
                    "user might ask. Prefer how/why/significance/capability questions over 'what did X report'. "
                    "Use only supplied material. Return strict JSON with key items, an array. Each item must include "
                    "question, core_fact, intelligence_value, primary_url, supporting_urls, and cluster_size."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"TOPIC: {topic}\nCreate up to {per_topic} distinct questions. Prioritize repeated themes and "
                    f"first-hand intelligence value. TOPIC-SPECIFIC RULE: {TOPIC_RESEARCH_GUIDANCE[topic]} "
                    f"CANDIDATE ARTICLES JSON:\n{candidate_json}"
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
    RAW_RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_RESEARCH_DIR / _raw_name(topic)).write_text(content, encoding="utf-8")
    parsed = _parse_json(content)
    return _normalize_generated_items(candidates, parsed, per_topic)


def _normalize_generated_items(
    candidates: list[dict[str, Any]],
    parsed: dict[str, Any],
    per_topic: int,
) -> list[dict[str, Any]]:
    allowed_urls = {canonicalize_url(str(item["url"])): item for item in candidates}
    results: list[dict[str, Any]] = []
    generated_items = parsed.get("items") or parsed.get("key_items") or parsed.get("questions") or []
    for item in generated_items:
        if not isinstance(item, dict):
            continue
        question = " ".join(str(item.get("question", "")).split())
        if question and not question.endswith("?"):
            question += "?"
        primary_url = canonicalize_url(str(item.get("primary_url", "")))
        if not _valid_question(question) or primary_url not in allowed_urls:
            continue
        supporting = [
            canonicalize_url(str(url))
            for url in item.get("supporting_urls", [])
            if canonicalize_url(str(url)) in allowed_urls
        ]
        source = allowed_urls[primary_url]
        results.append(
            {
                "question": question,
                "core_fact": str(item.get("core_fact", ""))[:1000],
                "intelligence_value": str(item.get("intelligence_value", ""))[:1000],
                "seed_article_title": source["title"],
                "seed_article_url": primary_url,
                "seed_published_at": source["published_at"],
                "supporting_article_urls": list(dict.fromkeys([primary_url, *supporting])),
                "cluster_size": max(1, int(item.get("cluster_size", len(supporting) + 1))),
                "generation_method": "researched_event_synthesis",
            }
        )
        if len(results) >= per_topic:
            break
    return results


def _raw_name(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_") + ".json"


def _clean_lead(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    useful = [line for line in lines if len(line.split()) >= 8 and not line.lower().startswith("photo:")]
    return " ".join(useful[:3])


def _valid_question(question: str) -> bool:
    lowered = question.lower()
    return (
        len(question.split()) >= 8
        and question.endswith("?")
        and "global times" not in lowered
        and "the article" not in lowered
    )


def _parse_json(content: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise RuntimeError("Prompt research did not return JSON")
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise RuntimeError("Prompt research JSON must be an object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate researched long-tail prompts from recent GT full text")
    parser.add_argument("--days", type=int, default=21)
    parser.add_argument("--per-topic", type=int, default=4)
    parser.add_argument("--model", default=None)
    parser.add_argument("--topics", default="", help="Comma-separated topic names; defaults to all")
    parser.add_argument("--from-raw", action="store_true", help="Rebuild from saved raw responses without API calls")
    args = parser.parse_args()
    selected = [item.strip() for item in args.topics.split(",") if item.strip()] or None
    result = research_longtail_prompts(
        model=args.model,
        recent_days=args.days,
        per_topic=args.per_topic,
        selected_topics=selected,
        use_raw=args.from_raw,
    )
    counts = {topic: len(items) for topic, items in result["topics"].items()}
    print(json.dumps({"generated_at": result["generated_at"], "model": result["model"], "counts": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
