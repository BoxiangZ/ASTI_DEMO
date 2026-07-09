from __future__ import annotations

import pandas as pd

from engine.config import CHINESE_SITE, TARGET_MEDIA


def compute_visibility_summary(prompts: pd.DataFrame, sources: pd.DataFrame) -> dict:
    total_prompts = len(prompts)
    total_answers = prompts["prompt_id"].nunique()
    target_sources = sources[sources["media_name"] == TARGET_MEDIA]
    target_prompt_count = target_sources["prompt_id"].nunique()

    return {
        "total_prompts": int(total_prompts),
        "total_ai_answers": int(total_answers),
        "total_citations": int(len(sources)),
        "unique_sources": int(sources["media_name"].nunique()),
        "target_media_citations": int(len(target_sources)),
        "target_media_coverage_rate": _pct(target_prompt_count, total_prompts),
        "average_citation_position": round(float(target_sources["source_position"].mean()), 2)
        if not target_sources.empty
        else 0.0,
        "top3_citation_rate": _pct(int(target_sources["is_top3"].sum()), len(target_sources)),
    }


def media_citation_ranking(sources: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    ranking = (
        sources.groupby(["media_name", "domain", "cluster"], as_index=False)
        .agg(
            citations=("record_id", "count"),
            cited_prompts=("prompt_id", "nunique"),
            avg_position=("source_position", "mean"),
            top3_rate=("is_top3", "mean"),
        )
        .sort_values("citations", ascending=False)
        .head(top_n)
    )
    ranking["avg_position"] = ranking["avg_position"].round(2)
    ranking["top3_rate"] = (ranking["top3_rate"] * 100).round(1)
    return ranking


def target_site_split(sources: pd.DataFrame) -> pd.DataFrame:
    subset = sources[sources["media_name"].isin([TARGET_MEDIA, CHINESE_SITE])]
    if subset.empty:
        return pd.DataFrame(columns=["media_name", "citations", "coverage_prompts", "avg_position"])
    result = (
        subset.groupby(["media_name", "domain"], as_index=False)
        .agg(
            citations=("record_id", "count"),
            coverage_prompts=("prompt_id", "nunique"),
            avg_position=("source_position", "mean"),
        )
        .sort_values("citations", ascending=False)
    )
    result["avg_position"] = result["avg_position"].round(2)
    return result


def target_breakdown(prompts: pd.DataFrame, sources: pd.DataFrame, dimension: str) -> pd.DataFrame:
    target_prompts = sources[sources["media_name"] == TARGET_MEDIA][["prompt_id"]].drop_duplicates()
    base = prompts.groupby(dimension, as_index=False).agg(total_prompts=("prompt_id", "nunique"))
    hit = (
        prompts.merge(target_prompts, on="prompt_id")
        .groupby(dimension, as_index=False)
        .agg(target_hits=("prompt_id", "nunique"))
    )
    result = base.merge(hit, on=dimension, how="left").fillna({"target_hits": 0})
    result["coverage_rate"] = (result["target_hits"] / result["total_prompts"] * 100).round(1)
    return result.sort_values("coverage_rate", ascending=False)


def target_query_intent_coverage(prompts: pd.DataFrame, sources: pd.DataFrame) -> pd.DataFrame:
    return target_breakdown(prompts, sources, "query_intent")


def _pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 2) if denominator else 0.0

