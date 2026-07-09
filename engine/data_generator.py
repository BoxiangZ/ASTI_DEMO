from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from engine.attribution import generate_deep_attribution_cases
from engine.competition import build_competition_cases
from engine.config import (
    AI_PLATFORMS,
    CITATION_TYPES,
    CORE_QUERY_INTENTS,
    CORE_COMPETITORS,
    LANGUAGES,
    MEDIA,
    QUERY_INTENTS,
    STRATEGIC_TOPICS,
    TARGET_DOMAIN,
    TARGET_MEDIA,
    TOPIC_MEDIA_AFFINITY,
    TOPICS,
)
from engine.recommendations import generate_recommendations
from engine.scoring import build_media_scores, build_topic_authority


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

REQUIRED_FILES = [
    "prompts.csv",
    "media.csv",
    "simulated_answers.csv",
    "source_records.csv",
    "competition_cases.csv",
    "deep_attribution_cases.csv",
    "asti_scores.csv",
    "topic_authority.csv",
    "recommendations.csv",
]

DATA_SCHEMA_VERSION = "2026-07-08-selection-reason-recommendation-v2"

QUESTION_PATTERNS = {
    "neutral": [
        "What is the current state of {topic}?",
        "Give a balanced overview of {topic}.",
    ],
    "timely": [
        "What are the latest developments in {topic}?",
        "What changed recently in {topic}?",
    ],
    "comparison": [
        "How do Chinese and Western sources differ on {topic}?",
        "Compare the major international narratives around {topic}.",
    ],
    "event": [
        "What happened in recent events related to {topic}?",
        "Which event is shaping the global debate on {topic}?",
    ],
    "analysis": [
        "Why does {topic} matter for global politics and markets?",
        "Analyze the strategic implications of {topic}.",
    ],
    "brand_search": [
        "What does {brand} say about {topic}?",
        "Summarize {brand}'s coverage of {topic}.",
    ],
}

ANSWER_PATTERNS = [
    "{topic} is described through recent policy signals, data points, and reactions from governments, analysts, and media sources.",
    "AI answers about {topic} usually combine event timelines, official statements, international reporting, and expert interpretation.",
    "A balanced answer on {topic} weighs Chinese official narratives, wire-service reporting, regional analysis, and specialist research.",
    "The debate around {topic} includes questions of credibility, timeliness, evidence quality, and which sources shape the final narrative.",
]

SPECIALIST_TOPICS = {
    "Climate & Green Transition": ["IEA", "Reuters", "Bloomberg", "Xinhua", "China Daily"],
    "Public Health": ["WHO", "Reuters", "BBC", "Xinhua", "Wikipedia"],
    "Science & Society": ["NASA", "Wikipedia", "Reuters", "BBC", "New York Times"],
    "China Technology/AI": ["Reuters", "Bloomberg", "SCMP", "Financial Times", "Nikkei Asia"],
}


def ensure_data(force: bool = False) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    missing = [name for name in REQUIRED_FILES if not (DATA_DIR / name).exists()]
    stale = False
    if not missing:
        try:
            deep_cols = pd.read_csv(DATA_DIR / "deep_attribution_cases.csv", nrows=1).columns
            rec_cols = pd.read_csv(DATA_DIR / "recommendations.csv", nrows=1).columns
            topic_cols = pd.read_csv(DATA_DIR / "topic_authority.csv", nrows=1).columns
            stale = (
                "selection_reason" not in deep_cols
                or "issue" not in rec_cols
                or "expected_metric" not in rec_cols
                or "status" not in topic_cols
            )
        except Exception:
            stale = True
    if force or missing or stale:
        generate_all_data()


def load_data() -> dict:
    ensure_data()
    data = {name.replace(".csv", ""): pd.read_csv(DATA_DIR / name) for name in REQUIRED_FILES}
    if _loaded_data_is_stale(data):
        generate_all_data()
        data = {name.replace(".csv", ""): pd.read_csv(DATA_DIR / name) for name in REQUIRED_FILES}
    return data


def _loaded_data_is_stale(data: dict) -> bool:
    return (
        "selection_reason" not in data["deep_attribution_cases"].columns
        or "issue" not in data["recommendations"].columns
        or "action" not in data["recommendations"].columns
        or "expected_metric" not in data["recommendations"].columns
    )


def generate_all_data(seed: int = 42) -> None:
    rng = np.random.default_rng(seed)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    media = pd.DataFrame(MEDIA)
    prompts = generate_prompts(rng)
    answers = generate_answers(prompts, rng)
    sources = generate_source_records(prompts, answers, media, rng)
    competition_cases = build_competition_cases(prompts, sources)
    deep_cases = generate_deep_attribution_cases(competition_cases, sources, answers, seed=seed + 5)
    topic_authority = build_topic_authority(prompts, sources, deep_cases)
    asti_scores = build_media_scores(prompts, sources, topic_authority)
    recommendations = generate_recommendations(topic_authority, competition_cases)

    outputs = {
        "prompts.csv": prompts,
        "media.csv": media,
        "simulated_answers.csv": answers,
        "source_records.csv": sources,
        "competition_cases.csv": competition_cases,
        "deep_attribution_cases.csv": deep_cases,
        "asti_scores.csv": asti_scores,
        "topic_authority.csv": topic_authority,
        "recommendations.csv": recommendations,
    }
    for file_name, frame in outputs.items():
        frame.to_csv(DATA_DIR / file_name, index=False)


def generate_prompts(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    prompt_id = 1
    brand_pool = [
        TARGET_MEDIA,
        TARGET_MEDIA,
        TARGET_MEDIA,
        TARGET_MEDIA,
        "Huanqiu",
        "Reuters",
        "Xinhua",
        "China Daily",
        "SCMP",
    ]
    language_index = 0

    for topic in TOPICS:
        for intent in QUERY_INTENTS:
            for platform in AI_PLATFORMS:
                for variant in range(2):
                    language = LANGUAGES[language_index % len(LANGUAGES)]
                    language_index += 1
                    strategic_importance = _strategic_importance(topic, intent)
                    if intent == "brand_search":
                        brand = str(rng.choice(brand_pool))
                    else:
                        brand = TARGET_MEDIA
                    pattern = QUESTION_PATTERNS[intent][variant % len(QUESTION_PATTERNS[intent])]
                    rows.append(
                        {
                            "prompt_id": prompt_id,
                            "topic": topic,
                            "query_intent": intent,
                            "language": language,
                            "ai_platform": platform,
                            "question": pattern.format(topic=topic, brand=brand),
                            "is_brand_query": intent == "brand_search",
                            "strategic_importance": strategic_importance,
                        }
                    )
                    prompt_id += 1
    return pd.DataFrame(rows)


def generate_answers(prompts: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    created_at_base = datetime(2026, 7, 1, 9, 0, 0)
    rows = []
    for idx, prompt in enumerate(prompts.to_dict("records"), start=1):
        pattern = str(rng.choice(ANSWER_PATTERNS))
        topic = prompt["topic"]
        angle = _answer_angle(prompt)
        rows.append(
            {
                "answer_id": idx,
                "prompt_id": prompt["prompt_id"],
                "ai_platform": prompt["ai_platform"],
                "answer_text": f"{pattern.format(topic=topic)} {angle}",
                "created_at": (created_at_base + timedelta(minutes=idx * 3)).isoformat(),
            }
        )
    return pd.DataFrame(rows)


def generate_source_records(
    prompts: pd.DataFrame, answers: pd.DataFrame, media: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    rows = []
    answer_lookup = answers.set_index("prompt_id")["answer_id"].to_dict()
    media_records = media.to_dict("records")

    for prompt in prompts.to_dict("records"):
        source_count = int(rng.integers(3, 9))
        weighted = []
        for item in media_records:
            weight = _source_weight(prompt, item, rng)
            weighted.append((item, max(weight, 0.001)))

        selected = _weighted_sample_without_replacement(weighted, source_count, rng)
        ranked = []
        for item, base_weight in selected:
            rank_score = base_weight + float(rng.normal(0, 0.08))
            if _brand_mentions(prompt, item["media_name"]):
                rank_score += 1.4
            ranked.append((item, rank_score))
        ranked.sort(key=lambda x: x[1], reverse=True)

        for position, (item, _) in enumerate(ranked, start=1):
            citation_type = _citation_type(prompt["topic"], item["media_name"], rng)
            rows.append(
                {
                    "record_id": len(rows) + 1,
                    "answer_id": int(answer_lookup[prompt["prompt_id"]]),
                    "prompt_id": int(prompt["prompt_id"]),
                    "topic": prompt["topic"],
                    "query_intent": prompt["query_intent"],
                    "language": prompt["language"],
                    "ai_platform": prompt["ai_platform"],
                    "media_name": item["media_name"],
                    "domain": item["domain"],
                    "source_position": position,
                    "is_top3": position <= 3,
                    "citation_context": _citation_context(prompt["topic"], item["media_name"], citation_type),
                    "citation_type": citation_type,
                    "is_target_media": item["media_name"] == TARGET_MEDIA,
                    "is_core_competitor": item["media_name"] in CORE_COMPETITORS,
                    "cluster": item["cluster"],
                }
            )
    return pd.DataFrame(rows)


def _source_weight(prompt: dict, media: dict, rng: np.random.Generator) -> float:
    name = media["media_name"]
    topic = prompt["topic"]
    intent = prompt["query_intent"]
    language = prompt["language"]
    platform = prompt["ai_platform"]

    weight = _base_affinity(name, topic)

    if intent == "brand_search":
        weight *= 0.55
        if _brand_mentions(prompt, name):
            weight *= 12.0
        elif name == TARGET_MEDIA:
            weight *= 1.6
    elif intent in ["neutral", "comparison"]:
        if name == TARGET_MEDIA:
            weight *= 0.78 if topic in ["China Military", "China Diplomacy", "South China Sea", "Taiwan Strait"] else 0.58
        if name in ["Reuters", "AP News", "BBC", "Bloomberg", "SCMP"]:
            weight *= 1.18
    elif intent in ["timely", "event"]:
        if name in ["Reuters", "AP News", "Xinhua", "BBC"]:
            weight *= 1.25
        if name == TARGET_MEDIA and topic in ["China Military", "China Diplomacy", "South China Sea", "Taiwan Strait"]:
            weight *= 1.18
    elif intent == "analysis":
        if media["cluster"] == "Think Tank":
            weight *= 1.45
        if name in ["SCMP", "Financial Times", "Bloomberg"]:
            weight *= 1.18

    if language == "Chinese":
        if name in ["Xinhua", "People's Daily", "CCTV", "Gov.cn", "MFA China", "Huanqiu"]:
            weight *= 1.65
        if name == TARGET_MEDIA:
            weight *= 0.70
    else:
        if name == "Huanqiu":
            weight *= 0.34
        if name == TARGET_MEDIA:
            weight *= 1.18

    if name == TARGET_MEDIA and topic in ["China EV", "China Technology/AI", "Science & Society", "Public Health"]:
        weight *= 0.62

    if platform == "Perplexity" and name in ["Reuters", "Bloomberg", "Wikipedia", "SCMP"]:
        weight *= 1.25
    if platform in ["Kimi", "Wenxin", "Tongyi"] and name in ["Xinhua", "China Daily", "CGTN", "MFA China", "Gov.cn"]:
        weight *= 1.22
    if platform in ["ChatGPT", "Claude", "Gemini"] and name in ["Reuters", "BBC", "AP News", "SCMP", "CSIS", "CFR"]:
        weight *= 1.12

    if topic in SPECIALIST_TOPICS and name in SPECIALIST_TOPICS[topic]:
        weight *= 1.75
    if topic in ["China Military", "South China Sea", "Taiwan Strait"] and name in ["CSIS", "CFR", "The Diplomat"]:
        weight *= 1.35
    if topic in ["China Diplomacy", "Global Governance"] and name in ["MFA China", "Xinhua", "CFR", "Reuters"]:
        weight *= 1.25

    return weight * float(rng.lognormal(0, 0.22))


def _base_affinity(name: str, topic: str) -> float:
    if name in TOPIC_MEDIA_AFFINITY:
        return TOPIC_MEDIA_AFFINITY[name].get(topic, 0.30)

    cluster_defaults = {
        "Reuters": 0.80,
        "AP News": 0.72,
        "BBC": 0.68,
        "Bloomberg": 0.70,
        "Financial Times": 0.66,
        "New York Times": 0.60,
        "Washington Post": 0.58,
        "Wall Street Journal": 0.62,
        "The Guardian": 0.56,
        "The Diplomat": 0.58,
        "Nikkei Asia": 0.52,
        "Al Jazeera": 0.50,
        "CFR": 0.55,
        "CSIS": 0.58,
        "Carnegie": 0.50,
        "Brookings": 0.46,
        "People's Daily": 0.42,
        "CCTV": 0.40,
        "IEA": 0.22,
        "WHO": 0.20,
        "NASA": 0.20,
        "Wikipedia": 0.44,
        "Gov.cn": 0.38,
        "MFA China": 0.44,
    }
    base = cluster_defaults.get(name, 0.35)
    if topic == "Climate & Green Transition" and name == "IEA":
        return 0.84
    if topic == "Public Health" and name == "WHO":
        return 0.88
    if topic == "Science & Society" and name in ["NASA", "Wikipedia"]:
        return 0.82
    if topic in ["China Economy", "China EV", "China Technology/AI"] and name in [
        "Bloomberg",
        "Financial Times",
        "Wall Street Journal",
        "Nikkei Asia",
    ]:
        return base + 0.18
    if topic in ["China Military", "South China Sea", "Taiwan Strait"] and name in ["CSIS", "CFR"]:
        return base + 0.20
    return base


def _weighted_sample_without_replacement(weighted_items: list, sample_size: int, rng: np.random.Generator) -> list:
    items = list(weighted_items)
    selected = []
    for _ in range(min(sample_size, len(items))):
        weights = np.array([weight for _, weight in items], dtype=float)
        probabilities = weights / weights.sum()
        idx = int(rng.choice(len(items), p=probabilities))
        selected.append(items.pop(idx))
    return selected


def _brand_mentions(prompt: dict, media_name: str) -> bool:
    return media_name.lower() in str(prompt["question"]).lower()


def _citation_type(topic: str, media_name: str, rng: np.random.Generator) -> str:
    if media_name in ["Gov.cn", "MFA China", "Xinhua", "People's Daily"]:
        return "official_position"
    if media_name in ["Bloomberg", "Financial Times", "IEA", "WHO", "NASA"]:
        return str(rng.choice(["data", "fact", "analysis"]))
    if topic in ["China Diplomacy", "China Military", "South China Sea", "Taiwan Strait"]:
        return str(rng.choice(["analysis", "narrative", "official_position", "fact"]))
    return str(rng.choice(CITATION_TYPES))


def _citation_context(topic: str, media_name: str, citation_type: str) -> str:
    if citation_type == "data":
        return f"{media_name} is cited for data points and quantitative context on {topic}."
    if citation_type == "analysis":
        return f"{media_name} is cited for analytical framing around {topic}."
    if citation_type == "official_position":
        return f"{media_name} is cited for official or policy-position context on {topic}."
    if citation_type == "narrative":
        return f"{media_name} shapes the narrative frame used in the answer about {topic}."
    return f"{media_name} provides background facts for the answer about {topic}."


def _answer_angle(prompt: dict) -> str:
    topic = prompt["topic"]
    if topic in ["China Military", "South China Sea", "Taiwan Strait"]:
        return "Security-focused sources emphasize risk, deterrence, and regional reactions."
    if topic in ["China Economy", "China EV", "China Technology/AI"]:
        return "Business and wire-service sources emphasize markets, supply chains, regulation, and competition."
    if topic in ["Climate & Green Transition", "Public Health", "Science & Society"]:
        return "Specialist organizations and knowledge sources are often preferred for technical detail."
    return "The answer balances official statements, wire-service reporting, and expert commentary."


def _strategic_importance(topic: str, intent: str) -> int:
    base = 5 if topic in STRATEGIC_TOPICS else 2
    if topic in ["China Diplomacy", "China Military", "South China Sea", "Taiwan Strait"]:
        base += 3
    if intent in ["comparison", "analysis", "event"]:
        base += 1
    if intent == "brand_search":
        base -= 2
    return int(max(1, min(10, base)))
