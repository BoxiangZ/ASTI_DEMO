from __future__ import annotations

import pandas as pd

from engine.config import CORE_COMPETITORS, STRATEGIC_TOPICS, TARGET_MEDIA


def build_competition_cases(prompts: pd.DataFrame, sources: pd.DataFrame) -> pd.DataFrame:
    strategic = prompts[
        (prompts["topic"].isin(STRATEGIC_TOPICS)) & (prompts["query_intent"] != "brand_search")
    ].copy()
    rows = []
    grouped = sources[sources["prompt_id"].isin(strategic["prompt_id"])].groupby("prompt_id")

    for prompt in strategic.to_dict("records"):
        if prompt["prompt_id"] not in grouped.groups:
            continue
        prompt_sources = grouped.get_group(prompt["prompt_id"]).copy()
        gt_rows = prompt_sources[prompt_sources["media_name"] == TARGET_MEDIA]
        competitor_rows = prompt_sources[prompt_sources["media_name"].isin(CORE_COMPETITORS)]
        if competitor_rows.empty:
            continue

        gt_position = int(gt_rows["source_position"].min()) if not gt_rows.empty else None
        best_comp = competitor_rows.sort_values("source_position").iloc[0]
        best_comp_position = int(best_comp["source_position"])
        best_competitor = best_comp["media_name"]

        gt_top3 = gt_position is not None and gt_position <= 3
        comp_top3 = best_comp_position <= 3
        both_top5 = gt_position is not None and gt_position <= 5 and best_comp_position <= 5
        valid = gt_top3 or comp_top3 or both_top5
        if not valid:
            continue

        if gt_top3 and gt_position < best_comp_position:
            status = "Strong Win"
        elif gt_top3:
            status = "Competitive"
        elif gt_position is not None:
            status = "Weak Presence"
        elif comp_top3:
            status = "Absence Loss"
        else:
            status = "No Strategic Competition"

        rows.append(
            {
                "case_id": len(rows) + 1,
                "prompt_id": prompt["prompt_id"],
                "topic": prompt["topic"],
                "query_intent": prompt["query_intent"],
                "language": prompt["language"],
                "ai_platform": prompt["ai_platform"],
                "question": prompt["question"],
                "gt_present": bool(gt_position is not None),
                "gt_position": gt_position,
                "best_competitor": best_competitor,
                "best_competitor_position": best_comp_position,
                "position_gap": (gt_position - best_comp_position) if gt_position is not None else None,
                "competitive_status": status,
            }
        )
    return pd.DataFrame(rows)


def source_win_rate(competition_cases: pd.DataFrame, sources: pd.DataFrame) -> pd.DataFrame:
    valid_prompt_ids = competition_cases["prompt_id"].unique()
    valid_sources = sources[sources["prompt_id"].isin(valid_prompt_ids)].copy()
    total_cases = competition_cases["prompt_id"].nunique()
    if total_cases == 0:
        return pd.DataFrame(columns=["media_name", "top3_cases", "source_win_rate"])
    top3 = valid_sources[valid_sources["source_position"] <= 3]
    result = (
        top3.groupby("media_name", as_index=False)
        .agg(top3_cases=("prompt_id", "nunique"))
        .sort_values("top3_cases", ascending=False)
    )
    result["source_win_rate"] = (result["top3_cases"] / total_cases * 100).round(1)
    return result


def head_to_head(sources: pd.DataFrame, competitors: list[str]) -> pd.DataFrame:
    rows = []
    for competitor in competitors:
        gt = sources[sources["media_name"] == TARGET_MEDIA][["prompt_id", "source_position"]].rename(
            columns={"source_position": "gt_position"}
        )
        comp = sources[sources["media_name"] == competitor][["prompt_id", "source_position"]].rename(
            columns={"source_position": "competitor_position"}
        )
        shared = gt.merge(comp, on="prompt_id")
        shared_count = len(shared)
        gt_wins = int((shared["gt_position"] < shared["competitor_position"]).sum())
        comp_wins = int((shared["competitor_position"] < shared["gt_position"]).sum())
        ties = shared_count - gt_wins - comp_wins
        rows.append(
            {
                "competitor": competitor,
                "shared_cases": shared_count,
                "gt_wins": gt_wins,
                "competitor_wins": comp_wins,
                "ties": ties,
                "gt_head_to_head_win_rate": round(gt_wins / shared_count * 100, 1)
                if shared_count
                else 0.0,
                "avg_position_gap": round(
                    float((shared["gt_position"] - shared["competitor_position"]).mean()), 2
                )
                if shared_count
                else 0.0,
            }
        )
    return pd.DataFrame(rows)


def absence_loss_by_topic(competition_cases: pd.DataFrame) -> pd.DataFrame:
    if competition_cases.empty:
        return pd.DataFrame(columns=["topic", "absence_losses", "effective_cases", "absence_loss_rate"])
    total = competition_cases.groupby("topic", as_index=False).agg(effective_cases=("case_id", "count"))
    loss = (
        competition_cases[competition_cases["competitive_status"] == "Absence Loss"]
        .groupby("topic", as_index=False)
        .agg(absence_losses=("case_id", "count"))
    )
    result = total.merge(loss, on="topic", how="left").fillna({"absence_losses": 0})
    result["absence_loss_rate"] = (result["absence_losses"] / result["effective_cases"] * 100).round(1)
    return result.sort_values("absence_loss_rate", ascending=False)


def topic_competitor_heatmap(competition_cases: pd.DataFrame) -> pd.DataFrame:
    if competition_cases.empty:
        return pd.DataFrame(columns=["topic", "best_competitor", "cases"])
    return (
        competition_cases.groupby(["topic", "best_competitor"], as_index=False)
        .agg(cases=("case_id", "count"))
        .sort_values("cases", ascending=False)
    )

