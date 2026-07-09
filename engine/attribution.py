import numpy as np
import pandas as pd
from typing import Optional

from engine.config import TARGET_MEDIA


LOSS_REASONS = {
    "Reuters": "Reuters wins because its simulated article contains more timely event facts and neutral international framing.",
    "Bloomberg": "Bloomberg wins on market data, business context, and cleaner quantitative explanation.",
    "SCMP": "SCMP wins because it translates China-topic complexity into an international-reader context.",
    "Xinhua": "Xinhua wins through official-source proximity and broad multilingual distribution.",
    "China Daily": "China Daily wins with structured English summaries and policy-friendly explainers.",
    "CGTN": "CGTN wins with multimedia-style summaries and cross-language availability.",
    "CSIS": "CSIS wins through specialist security analysis and named expert framing.",
    "CFR": "CFR wins because AI treats it as a concise explainer for diplomatic context.",
}


def generate_deep_attribution_cases(
    competition_cases: pd.DataFrame, sources: pd.DataFrame, answers: pd.DataFrame, seed: int = 7
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    if competition_cases.empty:
        return pd.DataFrame()

    candidates = competition_cases[
        competition_cases["competitive_status"].isin(["Absence Loss", "Competitive", "Weak Presence"])
    ].copy()
    if len(candidates) < 30:
        candidates = competition_cases.copy()

    sample_size = min(45, len(candidates))
    candidates = candidates.sample(n=sample_size, random_state=seed).reset_index(drop=True)
    answer_lookup = answers.set_index("prompt_id")["answer_text"].to_dict()

    rows = []
    for idx, case in candidates.iterrows():
        competitor = case["best_competitor"]
        topic = case["topic"]
        gt_present = bool(case["gt_present"])
        topic_strength = _gt_topic_strength(topic)
        status_penalty = 18 if case["competitive_status"] == "Absence Loss" else 8

        fact = _clip(rng.normal(topic_strength - status_penalty, 8))
        freshness = _clip(rng.normal(topic_strength - status_penalty + 4, 9))
        data_density = _clip(rng.normal(topic_strength - 14, 10))
        narrative = _clip(rng.normal(topic_strength + (5 if gt_present else -10), 8))
        authority = _clip(rng.normal(topic_strength - (8 if not gt_present else 0), 8))

        if competitor in ["Reuters", "Bloomberg", "SCMP", "CSIS", "CFR"]:
            data_density = max(25, data_density - 7)
            freshness = max(25, freshness - 4)

        final_score = (
            fact * 0.25
            + freshness * 0.15
            + data_density * 0.20
            + narrative * 0.25
            + authority * 0.15
        )
        loss_reason = LOSS_REASONS.get(
            competitor,
            f"{competitor} wins because the simulated answer treats it as more citation-ready for this query.",
        )
        recommendation = _case_recommendation(topic, competitor, case["competitive_status"])
        comp_position = int(case["best_competitor_position"])
        gt_position = int(case["gt_position"]) if pd.notna(case["gt_position"]) else None

        rows.append(
            {
                "case_id": idx + 1,
                "prompt_id": int(case["prompt_id"]),
                "topic": topic,
                "query_intent": case["query_intent"],
                "ai_platform": case["ai_platform"],
                "selection_reason": _selection_reason(case),
                "prompt": case["question"],
                "ai_answer_summary": answer_lookup.get(
                    int(case["prompt_id"]),
                    f"The AI answer summarizes recent developments in {topic} and cites several sources.",
                ),
                "gt_source_summary": _gt_summary(topic, gt_present, gt_position),
                "competitor_source_summary": _competitor_summary(topic, competitor, comp_position),
                "winning_source": competitor if case["competitive_status"] != "Strong Win" else TARGET_MEDIA,
                "gt_position": gt_position,
                "competitor_position": comp_position,
                "fact_contribution_score": round(fact, 1),
                "freshness_score": round(freshness, 1),
                "data_density_score": round(data_density, 1),
                "narrative_contribution_score": round(narrative, 1),
                "content_authority_score": round(authority, 1),
                "final_attribution_score": round(final_score, 1),
                "loss_reason": loss_reason,
                "recommendation": recommendation,
            }
        )
    return pd.DataFrame(rows)


def _gt_topic_strength(topic: str) -> float:
    strengths = {
        "China Military": 88,
        "China Diplomacy": 84,
        "South China Sea": 80,
        "Taiwan Strait": 76,
        "US-China Relations": 58,
        "China Economy": 50,
        "China EV": 34,
        "China Technology/AI": 30,
        "Climate & Green Transition": 42,
        "Global Governance": 50,
        "Science & Society": 20,
        "Public Health": 22,
    }
    return strengths.get(topic, 45)


def _selection_reason(case: pd.Series) -> str:
    status = case["competitive_status"]
    competitor = case["best_competitor"]
    if status == "Absence Loss":
        return "Absence Loss"
    if status == "Weak Presence":
        return "Weak Citation"
    if status == "Competitive":
        return "GT Top3 But Not Winning"
    if competitor == "Reuters":
        return "Lost to Reuters"
    if pd.notna(case.get("position_gap")) and float(case["position_gap"]) >= 3:
        return "Abnormal Drop"
    return f"Lost to {competitor}"


def _clip(value: float) -> float:
    return float(np.clip(value, 15, 95))


def _gt_summary(topic: str, present: bool, position: Optional[int]) -> str:
    if not present:
        return f"Global Times is absent from the simulated answer for {topic}, so it contributes no direct facts or framing."
    return (
        f"Global Times appears at citation position {position} and contributes perspective-oriented framing on {topic}, "
        "but the demo often gives competitors stronger data density or neutral sourcing."
    )


def _competitor_summary(topic: str, competitor: str, position: int) -> str:
    return (
        f"{competitor} appears at citation position {position} and is treated as a citation-ready source for {topic}, "
        "with clearer facts, context, or expert-style explanation."
    )


def _case_recommendation(topic: str, competitor: str, status: str) -> str:
    if status == "Absence Loss":
        return (
            f"Prioritize English, structured explainers for {topic}; AI is selecting {competitor} while Global Times is absent."
        )
    if competitor in ["Reuters", "Bloomberg"]:
        return "Add more original data, timelines, and market or policy evidence so the article becomes citation-ready."
    if competitor in ["SCMP", "The Diplomat", "Nikkei Asia"]:
        return "Improve international-reader context and explain why the topic matters outside China."
    return "Strengthen expert quotes, factual summaries, and entity consistency to improve source preference."
