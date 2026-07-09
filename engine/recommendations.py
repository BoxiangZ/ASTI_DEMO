from __future__ import annotations

import pandas as pd


def generate_recommendations(topic_authority: pd.DataFrame, competition_cases: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for topic_row in topic_authority.to_dict("records"):
        topic = topic_row["topic"]
        coverage = topic_row["topic_coverage"]
        preference = topic_row["topic_source_preference"]
        citation = topic_row["topic_citation_quality"]
        attribution = topic_row["topic_attribution_score"]
        topic_cases = competition_cases[competition_cases["topic"] == topic]
        absence_count = int((topic_cases["competitive_status"] == "Absence Loss").sum()) if not topic_cases.empty else 0

        if absence_count >= 5 or coverage < 12:
            rows.append(_row(topic, "High Priority", "Coverage", "自然覆盖不足，战略问题中 AI 不稳定发现 GT。", "上线英文专题页，补齐常青解释稿、关键实体页和事件时间线，并保持标题/日期/机构名一致。", "AI 可见度、领域覆盖率"))
        if preference < 45:
            rows.append(_row(topic, "High Priority", "Source Preference", "被召回后进入 Top3 的比例偏低。", "每篇重点稿增加原创数据、具名专家、3-5 条可引用事实和中立比较段落。", "信源偏好、Top3 引用率"))
        if citation < 55:
            rows.append(_row(topic, "Medium Priority", "Citation Quality", "引用位置靠后，AI 更偏好结构更清晰的竞品来源。", "在正文前置 Key Facts、时间线、数据表和来源说明，让核心事实更容易被抽取。", "引用质量、平均引用位置"))
        if attribution < 50:
            rows.append(_row(topic, "Medium Priority", "Attribution", "AI 回答较少借用 GT 的事实、数据或叙事框架。", "推出带独家数据点、可复用解释框架和专家引语的深度稿。", "深度归因分、叙事贡献"))
        if absence_count > 0:
            rows.append(_row(topic, "High Priority", "Absence Loss", "核心竞品进入 Top3 但 GT 缺席。", "为缺席损失 prompt 建立内容缺口清单，优先补强 Reuters/SCMP/Xinhua 高频胜出的子议题。", "缺席损失率、有效竞争胜率"))
        if not rows or len([r for r in rows if r["topic"] == topic]) < 3:
            rows.append(_row(topic, "Low Priority", "Monitoring", "当前表现相对稳定，但需要防止竞品抢占新事件。", "每周刷新 prompt 集群表现，监控竞品 Top3 增长和 GT 位置下降。", "趋势稳定性、位置波动"))

    overall = [
        _row("Overall", "High Priority", "Organic Visibility", "品牌指定查询抬高表面可见度。", "所有报告拆分 brand_search 与自然查询，并把中立/比较/事件查询作为核心 ASTI 样本。", "自然覆盖率、信源偏好"),
        _row("Overall", "High Priority", "Content Packaging", "内容没有被充分包装成 AI 易抽取信源。", "统一实体、日期、摘要、数据表、FAQ 和议题标签，形成 AI 友好的结构化稿件模板。", "引用质量、归因分"),
        _row("Overall", "Medium Priority", "Competitive Benchmark", "单一总排名无法解释具体输给谁。", "按 Topic 对比 Reuters、Xinhua、China Daily、SCMP、CSIS 等核心竞品，输出对位胜率。", "对位胜率、位置差"),
        _row("Overall", "Medium Priority", "Deep Attribution", "全量深度归因成本高，且不必要。", "只对缺席损失、弱引用和高价值战略事件做 LLM 归因，形成案例库。", "归因效率、改进优先级"),
    ]
    return pd.DataFrame(overall + rows)


def _row(topic: str, priority: str, category: str, issue: str, action: str, expected_metric: str) -> dict:
    return {
        "topic": topic,
        "priority": priority,
        "category": category,
        "issue": issue,
        "action": action,
        "expected_metric": expected_metric,
        "recommendation": action,
    }
