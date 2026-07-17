from __future__ import annotations

import re
from typing import Any

import pandas as pd

from engine.config import CORE_QUERY_INTENTS, TARGET_MEDIA


TOPIC_ACTIONS = {
    "China Economy": [
        ("经济数据快报页", "重要数据发布后 2 小时内上线英文页，把总量、同比、环比、行业贡献和统计口径放入首屏，并提供 CSV。", "数据型 Prompt 的 Top3 覆盖率达到 40%", "1-2 周"),
        ("产业指标对照表", "按制造业、外贸、消费、投资建立月度表格，保留历史版本、数据来源和修订记录。", "结构化数据页每月获得 3 个以上 AI 引用", "2-4 周"),
        ("政策影响时间线", "把政策发布日期、执行节点、受影响行业、已观察结果和下一观察点放在同一持续更新页。", "事件类问题 GT 覆盖率提升 15 个百分点", "2-3 周"),
        ("企业与供应链案例库", "用具名企业、地区、订单和采访补充宏观数字，明确事实、企业判断和专家预测的边界。", "全文支持分稳定达到 70", "持续"),
    ],
    "China Technology/AI": [
        ("型号级产品档案", "为机器人、芯片和算力设施建立独立英文页，列出型号、参数、演示日期、能力边界和更新日志。", "具体型号长尾命中率达到 35%", "1-2 周"),
        ("演示证据包", "同步发布视频转录、逐图图注、测试条件、成功与失败项，避免只有宣传性结论。", "产品演示页全文支持分达到 75", "1-2 周"),
        ("基准与竞品表", "使用统一口径比较国内外同类产品，公开基准来源、样本条件和不可比项。", "comparison Prompt Top3 覆盖率达到 30%", "2-4 周"),
        ("市场预测方法页", "预测数字必须附模型、基期、数据源、假设和敏感性区间，并允许下载底表。", "数字预测被引用时原文直接命中率达到 80%", "2 周"),
    ],
    "China Diplomacy": [
        ("外交事件档案", "把访问、会谈、协议、抗议和后续行动整理为时间线，并链接正式文件与完整引语。", "事件类 Prompt 覆盖率达到 30%", "1-2 周"),
        ("双边关系常青页", "每个重点国家维护关键机制、最近会晤、合作项目、争议点和下一节点，不让信息散落在单篇快讯中。", "常青页每月进入 Top3 至少 3 次", "3-6 周"),
        ("表态与事实分层", "首屏分别列出已发生行动、官方原话、环球采访和分析判断，避免评论替代证据。", "全文支持分达到 70", "1 周"),
        ("具名专家连续追踪", "同一事件至少保留两位具名专家、机构和判断日期，后续报道回链并验证此前判断。", "分析类引用覆盖提升 15 个百分点", "持续"),
    ],
    "China Military": [
        ("装备型号事实页", "为舰船、战机、导弹建立独立英文档案，集中参数、建造/试验节点、服役状态、高清图注和更新日志。", "型号长尾 Prompt 覆盖率达到 35%", "1-3 周"),
        ("可观察战备指标表", "把甲板标线、弹射器、试航、编队、载荷等观察事实与推断分栏，并标记证据日期和可信级别。", "军事文章全文支持分达到 75", "2 周"),
        ("演习行动时间线", "按日期列出参演平台、海空域、科目、首次出现能力和官方说明，附原始视频转录。", "event Prompt Top3 覆盖率达到 30%", "1-2 周"),
        ("专业媒体对标页", "针对防务媒体已覆盖的型号，用同口径参数表补齐其事实项，同时增加环球现场采访和中国专家原话。", "对主要防务竞品的平均位置差缩小 1 位", "持续"),
    ],
    "US-China Relations": [
        ("关税与管制追踪器", "按生效日期、政策文件、产品类别、税率和受影响企业维护可筛选英文表格。", "政策类 Prompt 覆盖率达到 30%", "2-4 周"),
        ("双边数据仪表页", "统一展示贸易额、份额、投资和行业变化，附原始来源、计算方法和下载文件。", "数据型回答原文命中率达到 40%", "2-3 周"),
        ("会晤与制裁时间线", "将会谈、声明、制裁、反制与实际结果串联，并区分宣布、执行和撤销。", "timely/event Prompt Top3 覆盖率达到 30%", "2 周"),
        ("争议问题 FAQ", "用中性问题直接回答政策目的、影响范围、双方分歧和不确定性，链接官方文件而非只做立场转述。", "comparison Prompt 全文支持分达到 70", "2-4 周"),
    ],
    "Taiwan Strait": [
        ("台海事件时间线", "记录演训、巡航、军售和政党交流的日期、参与方、平台、地点和后续变化，保留来源层级。", "事件类 Prompt 覆盖率达到 35%", "2 周"),
        ("装备与行动档案", "为无人机、舰艇和演训代号建立型号页，区分已确认能力、官方表述和专家推断。", "具体装备长尾命中率达到 30%", "2-3 周"),
        ("两岸交流数据库", "持续记录访问主体、组织、议题、成果和后续渠道，提供可检索历史对照。", "交流类 Prompt Top3 覆盖率达到 40%", "3-6 周"),
        ("多方原话对照", "同页并列大陆、台湾及外部参与者完整引语与时间，减少 AI 转向区域媒体补齐语境。", "平均引用位置提升 1 位", "持续"),
    ],
    "South China Sea": [
        ("岛礁与舰船事实页", "为黄岩岛等具体地点维护地理、法律主张、近期舰船活动和事件时间线。", "地点长尾 Prompt 覆盖率达到 40%", "2-4 周"),
        ("法律原始材料库", "逐项链接裁决、条款、照会和正式抗议，提供中英文摘要并区分原文与评论。", "法律问题全文支持分达到 75", "3-6 周"),
        ("海上事件证据包", "统一发布时间、坐标、船名、照片/视频图注、双方说法和可确认事实。", "事件页种子原文命中率达到 40%", "1-2 周"),
        ("论点证据矩阵", "每个主张对应原始文件、事实证据、反方论点和环球回应，避免把法律判断与巡航事实混写。", "过度解释主张减少 50%", "2-4 周"),
    ],
    "China EV": [
        ("车型参数数据库", "按车型维护价格、续航、充电、上市日期、月销量和海外市场，并保留版本历史。", "车型 Prompt 覆盖率达到 35%", "3-6 周"),
        ("月度销量与份额表", "发布品牌、车型、动力类型和出口目的地数据，标明统计口径并提供 CSV。", "销量类回答原文命中率达到 40%", "2-3 周"),
        ("海外政策影响页", "逐国记录关税、调查、认证、当地售价和企业应对，区分宣布与生效。", "海外市场 Prompt Top3 覆盖率达到 30%", "2-4 周"),
        ("电池技术基准表", "按能量密度、充电倍率、循环寿命、量产时间和测试条件比较技术，不只引用企业口号。", "技术 comparison 全文支持分达到 75", "3-6 周"),
    ],
}

TOPIC_REQUIRED_FIELDS = {
    "China Economy": "总量、同比/环比、行业贡献、统计口径、原始数据链接、修订日期",
    "China Technology/AI": "具体型号、参数、测试条件、演示日期、能力边界、视频转录、更新日志",
    "China Diplomacy": "参与方、行动日期、正式文件、完整原话、已发生结果、下一外交节点",
    "China Military": "装备型号、公开参数、试验/演训节点、可观察事实、专家推断边界、图片与视频证据",
    "US-China Relations": "政策文件、生效日期、影响行业、双方行动、量化影响、后续节点",
    "Taiwan Strait": "事件日期、参与方、平台/装备、地点、各方原话、已确认事实与推断边界",
    "South China Sea": "具体岛礁、舰船名称、时间坐标、法律文件、双方说法、照片/视频证据",
    "China EV": "车型、价格、续航、销量、统计口径、竞品参数、海外政策与生效日期",
}


def build_topic_playbook(
    topic: str,
    prompts: pd.DataFrame,
    answers: pd.DataFrame,
    sources: pd.DataFrame,
    content_matches: pd.DataFrame,
    target_media: str = TARGET_MEDIA,
) -> dict[str, Any]:
    topic_answers = answers[
        (answers["topic"] == topic)
        & (answers["status"] == "success")
        & (answers["query_intent"].isin(CORE_QUERY_INTENTS))
    ].copy()
    answer_ids = set(topic_answers["answer_id"])
    topic_sources = sources[sources["answer_id"].isin(answer_ids)].copy()
    topic_matches = content_matches[
        content_matches["answer_id"].isin(answer_ids) & content_matches["valid_evidence"].fillna(False)
    ].copy()
    dominant = _dominant_competitor(topic_sources, target_media)
    total = int(topic_answers["answer_id"].nunique())
    target_metrics = _media_metrics(target_media, topic_sources, topic_matches, total)
    competitor_metrics = _media_metrics(dominant, topic_sources, topic_matches, total)
    comparison = _comparison_frame(target_metrics, competitor_metrics, dominant)
    gaps = _gap_frame(target_metrics, competitor_metrics, dominant)
    examples = _competitor_examples(topic_matches, dominant)
    lost_prompts = _lost_prompt_frame(topic, topic_answers, topic_matches, prompts, target_media)
    actions = _action_frame(topic, dominant, lost_prompts, gaps)
    prompt_actions = _prompt_action_frame(topic, lost_prompts)
    return {
        "topic": topic,
        "dominant_competitor": dominant,
        "tested_questions": total,
        "target_metrics": target_metrics,
        "competitor_metrics": competitor_metrics,
        "competitor_ranking": _competitor_ranking(topic_sources, topic_matches, total, target_media),
        "comparison": comparison,
        "gaps": gaps,
        "observations": _competitor_observations(target_metrics, competitor_metrics, dominant, total),
        "competitor_examples": examples,
        "lost_prompts": lost_prompts,
        "prompt_actions": prompt_actions,
        "actions": actions,
        "roadmap": _roadmap_frame(topic, lost_prompts),
    }


def _competitor_observations(
    target: dict[str, float], competitor: dict[str, float], competitor_name: str, total: int
) -> list[str]:
    if not competitor_name:
        return ["当前没有足够的全文有效竞品样本，不能判断别人如何胜出。"]
    observations = [
        f"在累计 {total} 个回答样本中，{competitor_name} 被引用 {int(competitor['coverage_count'])} 次、进入 Top3 {int(competitor['top3_count'])} 次；环球分别为 {int(target['coverage_count'])} 次和 {int(target['top3_count'])} 次。"
    ]
    if competitor["avg_position"] and (not target["avg_position"] or competitor["avg_position"] < target["avg_position"]):
        gt_position = f"{target['avg_position']:.1f}" if target["avg_position"] else "未形成有效位置"
        observations.append(f"{competitor_name} 的平均引用位置为 {competitor['avg_position']:.1f}，环球为 {gt_position}，说明其页面更常被模型优先选择。")
    if competitor["content_match"] > target["content_match"] + 5:
        observations.append(f"竞品正文与 AI 回答的平均匹配分高 {competitor['content_match'] - target['content_match']:.1f} 分，回答所需事实更集中地出现在同一页面。")
    if not target["avg_words"] and competitor["avg_words"]:
        observations.append(f"{competitor_name} 已形成平均约 {competitor['avg_words']:.0f} 词的有效页面样本；环球尚无有效引用页，当前首要差距是被发现和被召回，而不是篇幅。")
    elif competitor["avg_words"] > target["avg_words"] * 1.25 and competitor["avg_words"] > 0:
        observations.append(f"竞品有效页面平均约 {competitor['avg_words']:.0f} 词，环球约 {target['avg_words']:.0f} 词；竞品在当前样本中提供了更完整的背景与语境。")
    if target["avg_words"] and competitor["numbers_per_1k"] > target["numbers_per_1k"] * 1.2 and competitor["numbers_per_1k"] > 0:
        observations.append(f"竞品每千词数字标记为 {competitor['numbers_per_1k']:.1f}，环球为 {target['numbers_per_1k']:.1f}，参数、规模和变化更便于模型抽取。")
    if target["avg_words"] and competitor["quotes_per_1k"] > target["quotes_per_1k"] * 1.2 and competitor["quotes_per_1k"] > 0:
        observations.append(f"竞品每千词引语标记为 {competitor['quotes_per_1k']:.1f}，环球为 {target['quotes_per_1k']:.1f}，可直接归因的原话更密集。")
    return observations


def _dominant_competitor(sources: pd.DataFrame, target_media: str) -> str:
    competitors = sources[sources["media_name"] != target_media]
    if competitors.empty:
        return ""
    per_prompt = (
        competitors.groupby(["media_name", "answer_id"], as_index=False)["source_position"]
        .min()
        .assign(top3=lambda frame: (frame["source_position"] <= 3).astype(int))
    )
    ranking = (
        per_prompt.groupby("media_name")
        .agg(top3_prompts=("top3", "sum"), covered_prompts=("answer_id", "nunique"), avg_position=("source_position", "mean"))
        .sort_values(["top3_prompts", "covered_prompts", "avg_position"], ascending=[False, False, True])
    )
    return str(ranking.index[0])


def _media_metrics(media: str, sources: pd.DataFrame, matches: pd.DataFrame, total: int) -> dict[str, float]:
    frame = sources[sources["media_name"] == media] if media else sources.iloc[0:0]
    match_frame = matches[matches["media_name"] == media] if media else matches.iloc[0:0]
    covered = int(frame["answer_id"].nunique())
    top3 = int(frame[frame["source_position"] <= 3]["answer_id"].nunique())
    features = _article_features(match_frame)
    return {
        "coverage_count": covered,
        "coverage_rate": covered / total * 100 if total else 0.0,
        "top3_count": top3,
        "top3_rate": top3 / total * 100 if total else 0.0,
        "avg_position": float(frame["source_position"].mean()) if not frame.empty else 0.0,
        "content_match": float(match_frame["content_match_score"].mean()) if not match_frame.empty else 0.0,
        "avg_words": float(match_frame["article_word_count"].mean()) if not match_frame.empty else 0.0,
        **features,
    }


def _competitor_ranking(
    sources: pd.DataFrame,
    matches: pd.DataFrame,
    total: int,
    target_media: str,
) -> pd.DataFrame:
    rows = []
    for media in sources.loc[sources["media_name"] != target_media, "media_name"].dropna().unique():
        metrics = _media_metrics(str(media), sources, matches, total)
        rows.append(
            {
                "领先信源": str(media),
                "覆盖回答": int(metrics["coverage_count"]),
                "覆盖率": round(metrics["coverage_rate"], 1),
                "Top3 回答": int(metrics["top3_count"]),
                "平均位置": round(metrics["avg_position"], 1),
                "全文匹配": round(metrics["content_match"], 1),
                "平均正文词数": round(metrics["avg_words"]),
                "数字/千词": round(metrics["numbers_per_1k"], 1),
                "引语/千词": round(metrics["quotes_per_1k"], 1),
                "归因/千词": round(metrics["attributions_per_1k"], 1),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["领先信源", "覆盖回答", "覆盖率", "Top3 回答", "平均位置", "全文匹配"])
    return pd.DataFrame(rows).sort_values(
        ["Top3 回答", "覆盖回答", "平均位置"], ascending=[False, False, True]
    ).head(5)


def _article_features(frame: pd.DataFrame) -> dict[str, float]:
    if frame.empty:
        return {"numbers_per_1k": 0.0, "quotes_per_1k": 0.0, "attributions_per_1k": 0.0}
    unique = frame.drop_duplicates("source_url")
    totals = {"numbers": 0, "quotes": 0, "attributions": 0, "words": 0}
    for row in unique.to_dict("records"):
        text = str(row.get("article_text") or "")
        words = max(1, int(row.get("article_word_count") or len(text.split()) or 1))
        totals["words"] += words
        totals["numbers"] += len(re.findall(r"(?<!\w)\d[\d,.%:-]*", text))
        totals["quotes"] += text.count('"') + text.count("“") + text.count("”")
        totals["attributions"] += len(re.findall(r"\b(?:according to|said|told|reported|data from|statement by)\b", text, re.I))
    scale = 1000 / totals["words"] if totals["words"] else 0.0
    return {
        "numbers_per_1k": totals["numbers"] * scale,
        "quotes_per_1k": totals["quotes"] * scale,
        "attributions_per_1k": totals["attributions"] * scale,
    }


def _comparison_frame(target: dict[str, float], competitor: dict[str, float], competitor_name: str) -> pd.DataFrame:
    rows = [
        ("覆盖回答", target["coverage_count"], competitor["coverage_count"], "高者更好"),
        ("Top3 回答", target["top3_count"], competitor["top3_count"], "高者更好"),
        ("平均引用位置", target["avg_position"], competitor["avg_position"], "低者更好"),
        ("全文匹配分", target["content_match"], competitor["content_match"], "高者更好"),
        ("平均正文词数", target["avg_words"], competitor["avg_words"], "仅作结构观察"),
        ("数字证据/千词", target["numbers_per_1k"], competitor["numbers_per_1k"], "高值表示数字更密集"),
        ("引语标记/千词", target["quotes_per_1k"], competitor["quotes_per_1k"], "高值表示直接引语更密集"),
        ("归因表达/千词", target["attributions_per_1k"], competitor["attributions_per_1k"], "高值表示来源归因更密集"),
    ]
    return pd.DataFrame(
        [
            {"对比维度": name, "环球时报": round(float(gt), 1), competitor_name or "主要竞品": round(float(comp), 1), "口径": note}
            for name, gt, comp, note in rows
        ]
    )


def _gap_frame(target: dict[str, float], competitor: dict[str, float], competitor_name: str) -> pd.DataFrame:
    definitions = [
        ("AI 召回覆盖", "coverage_rate", False, "让更多当前 Prompt 能发现环球", "优先补齐竞品胜出问题对应的独立事实页"),
        ("Top3 竞争", "top3_rate", False, "决定 AI 是否优先使用该来源", "把可引用结论、关键数字和原始证据前置到首屏"),
        ("引用位置", "avg_position", True, "越靠前通常贡献越高", "围绕同一实体提供比竞品更完整的事实档案与持续更新"),
        ("全文匹配", "content_match", False, "衡量正文是否直接支持 AI 回答", "把事实、证据、边界和结论写在同一页面"),
        ("数字证据密度", "numbers_per_1k", False, "帮助模型抽取参数、规模和变化", "增加带来源与口径的参数表和可下载数据"),
        ("直接引语密度", "quotes_per_1k", False, "提升第一手信息和可归因性", "增加具名采访、完整原话和采访日期"),
    ]
    rows = []
    for label, key, lower_better, impact, action in definitions:
        gt = float(target[key]); comp = float(competitor[key])
        if not competitor_name:
            status = "尚无有效竞品样本"
        elif key == "avg_position" and (gt == 0 or comp == 0):
            status = "一方尚未被有效引用"
        else:
            delta = gt - comp
            lead = delta < -0.05 if lower_better else delta > 0.05
            behind = delta > 0.05 if lower_better else delta < -0.05
            status = "环球领先" if lead else f"{competitor_name} 领先" if behind else "基本接近"
        rows.append({"差距维度": label, "环球": round(gt, 1), "主要竞品": round(comp, 1), "判断": status, "为什么重要": impact, "直接动作": action})
    return pd.DataFrame(rows)


def _competitor_examples(matches: pd.DataFrame, competitor: str) -> pd.DataFrame:
    if not competitor:
        return pd.DataFrame(columns=["问题", "竞品位置", "竞品文章", "正文词数", "全文匹配", "支持 AI 回答的原文片段", "竞品链接"])
    frame = matches[matches["media_name"] == competitor].copy()
    if frame.empty:
        return pd.DataFrame(columns=["问题", "竞品位置", "竞品文章", "正文词数", "全文匹配", "支持 AI 回答的原文片段", "竞品链接"])
    if "question" not in frame:
        frame["question"] = ""
    if "best_matching_passage" not in frame:
        frame["best_matching_passage"] = ""
    frame["best_matching_passage"] = frame["best_matching_passage"].fillna("").str.slice(0, 420)
    frame = frame.sort_values(["source_position", "content_match_score"], ascending=[True, False]).drop_duplicates("source_url")
    return frame.head(8).rename(columns={
        "question": "问题", "source_position": "竞品位置", "article_title": "竞品文章",
        "article_word_count": "正文词数", "content_match_score": "全文匹配",
        "best_matching_passage": "支持 AI 回答的原文片段", "source_url": "竞品链接",
    })[["问题", "竞品位置", "竞品文章", "正文词数", "全文匹配", "支持 AI 回答的原文片段", "竞品链接"]]


def _lost_prompt_frame(
    topic: str,
    answers: pd.DataFrame,
    sources: pd.DataFrame,
    prompts: pd.DataFrame,
    target_media: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    prompt_kind = prompts.set_index("question")["prompt_kind"].to_dict()
    for answer in answers.to_dict("records"):
        frame = sources[sources["answer_id"] == answer["answer_id"]].sort_values("source_position")
        target = frame[frame["media_name"] == target_media]
        competitor = frame[frame["media_name"] != target_media]
        if competitor.empty:
            continue
        gt_pos = int(target["source_position"].min()) if not target.empty else None
        best = competitor.iloc[0]
        competitor_pos = int(best["source_position"])
        if gt_pos is not None and gt_pos <= competitor_pos:
            continue
        kind = str(prompt_kind.get(answer["question"], "broad"))
        page_type = _page_type(str(answer["query_intent"]), kind)
        rows.append({
            "未赢问题": answer["question"],
            "胜出竞品": best["media_name"],
            "竞品位置": competitor_pos,
            "GT 位置": gt_pos,
            "竞品文章": best["article_title"] or best["source_title"],
            "竞品怎么做": _observed_page_practice(best),
            "建议页面": page_type,
            "环球怎么提升": f"建设{page_type}；必须包含：{TOPIC_REQUIRED_FIELDS[topic]}。首屏直接回答该问题并链接原始证据。",
            "验收指标": "连续 3 次监测至少 2 次进入 Top3，且全文匹配分达到 70",
            "支持片段": str(best.get("best_matching_passage") or "")[:420],
            "竞品链接": best["source_url"],
        })
    return pd.DataFrame(rows, columns=[
        "未赢问题", "胜出竞品", "竞品位置", "GT 位置", "竞品文章", "竞品怎么做",
        "建议页面", "环球怎么提升", "验收指标", "支持片段", "竞品链接",
    ])


def _observed_page_practice(row: pd.Series) -> str:
    features = _article_features(pd.DataFrame([row]))
    practices = []
    words = int(row.get("article_word_count") or 0)
    match = float(row.get("content_match_score") or 0)
    if words >= 1200:
        practices.append(f"长篇背景页（{words} 词）")
    elif words:
        practices.append(f"聚焦正文（{words} 词）")
    if features["numbers_per_1k"] >= 12:
        practices.append("数字/参数密集")
    if features["quotes_per_1k"] >= 4:
        practices.append("直接引语密集")
    if features["attributions_per_1k"] >= 8:
        practices.append("来源归因清晰")
    if match >= 65:
        practices.append(f"与回答高度匹配（{match:.0f} 分）")
    return "、".join(practices) or "页面被 AI 优先发现并引用，需打开原文逐项拆解"


def _page_type(intent: str, kind: str) -> str:
    if kind == "gt_longtail":
        return "具体实体/事件事实页 + 原始证据包"
    return {
        "comparison": "统一口径对比表 + 方法说明",
        "event": "持续更新事件时间线",
        "timely": "最新进展 Live Page",
        "analysis": "常青解释页 + FAQ",
        "neutral": "Topic 权威总览页",
    }.get(intent, "独立事实页")


def _prompt_action_frame(topic: str, lost: pd.DataFrame) -> pd.DataFrame:
    columns = ["优先级", "目标问题", "对标竞品", "竞品做法", "立即交付", "必备内容", "验收 KPI", "对标链接"]
    if lost.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    ordered = lost.sort_values(["竞品位置", "GT 位置"], na_position="last")
    for item in ordered.to_dict("records"):
        gt_missing = pd.isna(item["GT 位置"]) or item["GT 位置"] is None
        priority = "P0" if int(item["竞品位置"]) == 1 and gt_missing else "P1"
        rows.append({
            "优先级": priority,
            "目标问题": item["未赢问题"],
            "对标竞品": item["胜出竞品"],
            "竞品做法": item["竞品怎么做"],
            "立即交付": item["建议页面"],
            "必备内容": TOPIC_REQUIRED_FIELDS[topic],
            "验收 KPI": item["验收指标"],
            "对标链接": item["竞品链接"],
        })
    return pd.DataFrame(rows, columns=columns)


def _roadmap_frame(topic: str, lost: pd.DataFrame) -> pd.DataFrame:
    assets = [item[0] for item in TOPIC_ACTIONS.get(topic, [])]
    lost_count = len(lost)
    return pd.DataFrame([
        {
            "阶段": "0-30 天",
            "目标": "修复当前真实输掉的问题",
            "具体交付": f"完成 {min(lost_count, 5)} 个逐 Prompt 补位页；上线{assets[0]}和{assets[1]}",
            "阶段 KPI": "P0 问题连续复测 3 次，至少 2 次进入 Top3",
        },
        {
            "阶段": "31-60 天",
            "目标": "形成可持续 Topic 内容资产",
            "具体交付": f"上线{assets[2]}和{assets[3]}；全部页面补 FAQ、结构化数据、更新时间和内链",
            "阶段 KPI": "Topic 覆盖率提升至少 15 个百分点，正文抓取成功率达到 95%",
        },
        {
            "阶段": "61-90 天",
            "目标": "验证策略并扩大有效问题簇",
            "具体交付": "围绕已进入 Top3 的问题扩展相邻长尾；每周复盘 Top 5 领先信源和胜出 URL",
            "阶段 KPI": "累计至少 30 个有效回答；全文匹配分达到 70；关联原文命中率达到 35%",
        },
    ])


def _action_frame(topic: str, competitor: str, lost: pd.DataFrame, gaps: pd.DataFrame) -> pd.DataFrame:
    competitor_label = competitor or "当前领先信源"
    lead_prompt = str(lost.iloc[0]["未赢问题"]) if not lost.empty else "当前未覆盖的核心问题"
    rows = [
        {
            "优先级": "P0",
            "交付物": "竞品胜出 Prompt 补位",
            "对标差距": f"{competitor_label} 在具体问题中先于环球被引用",
            "怎么做": f"先围绕“{lead_prompt[:90]}”建设独立英文事实页，并链接原始文件、数据和持续更新记录。",
            "验收指标": "该问题连续 3 次监测至少 2 次进入 Top3",
            "周期": "3-7 天",
        }
    ]
    leading_gaps = gaps[gaps["判断"].str.contains("领先") & ~gaps["判断"].str.startswith("环球")]
    gap_text = "；".join(leading_gaps["差距维度"].head(2).tolist()) or "召回覆盖与引用位置"
    for index, (deliverable, execution, metric, cycle) in enumerate(TOPIC_ACTIONS.get(topic, [])):
        rows.append({
            "优先级": "P0" if index < 2 else "P1",
            "交付物": deliverable,
            "对标差距": f"当前重点差距：{gap_text}；主要对标 {competitor_label}",
            "怎么做": execution,
            "验收指标": metric,
            "周期": cycle,
        })
    rows.extend([
        {
            "优先级": "P1",
            "交付物": "GEO 页面工程",
            "对标差距": "模型需要稳定解析实体、日期、数字和证据关系",
            "怎么做": "增加 80-120 字事实摘要、目录、FAQ、Article/NewsArticle 结构化数据、规范 URL、更新时间和相关报道内链。",
            "验收指标": "正文抓取成功率 95%，种子/关联原文命中率达到 35%",
            "周期": "2 周",
        },
        {
            "优先级": "P2",
            "交付物": "按周竞品复盘",
            "对标差距": "单次结果可能受模型和时点波动影响",
            "怎么做": f"每周复测相同 Prompt，记录 {competitor_label} 胜出 URL、位置和内容结构；连续三次后再判断策略有效性。",
            "验收指标": "每 Topic 累积至少 30 个有效回答，再调整长期 KPI",
            "周期": "每周",
        },
    ])
    return pd.DataFrame(rows)
