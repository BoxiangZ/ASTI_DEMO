from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from engine.config import CORE_QUERY_INTENTS, TARGET_MEDIA
from engine.real_collector import DEFAULT_PROVIDER, PROVIDER_LABELS, collect_prompts, provider_environment
from engine.real_store import DEFAULT_DB_PATH, load_pilot_prompts, load_real_data, real_summary
from engine.topic_playbook import build_topic_playbook
from engine.topic_strategy import PROMPT_CONFIG_VERSION, TOPIC_STRATEGY, ensure_prompt_config


st.set_page_config(
    page_title="环球时报 AI 信源监测报告",
    page_icon="AI",
    layout="wide",
)


REPORT_PLATFORM = "ChatGPT"


TOPIC_ZH = {item["topic"]: item["topic_zh"] for item in TOPIC_STRATEGY}
INTENT_ZH = {
    "neutral": "现状",
    "timely": "最新进展",
    "comparison": "对比",
    "event": "事件",
    "analysis": "分析",
    "article_longtail": "文章长尾",
}
MEDIA_ZH = {
    "Global Times": "环球时报英文站",
    "Reuters": "路透社",
    "BBC": "英国广播公司",
    "AP News": "美联社",
    "Bloomberg": "彭博社",
    "Financial Times": "金融时报",
    "Xinhua": "新华社",
    "China Daily": "中国日报",
    "CGTN": "中国国际电视台",
    "People's Daily": "人民日报",
    "SCMP": "南华早报",
    "The Diplomat": "外交学者",
    "CFR": "美国外交关系协会",
    "CSIS": "战略与国际研究中心",
    "Gov.cn": "中国政府网",
    "MFA China": "中国外交部",
    "worldbank.org": "世界银行",
    "whitehouse.gov": "美国白宫",
    "focustaiwan.tw": "中央社 Focus Taiwan",
    "internazionale.it": "Internazionale",
    "IEA": "国际能源署",
    "janes.com": "Janes 防务",
    "chinamil.com.cn": "中国军网",
    "eng.chinamil.com.cn": "中国军网英文站",
    "sipri.org": "斯德哥尔摩国际和平研究所",
}
STATUS_ZH = {
    "Strong Advantage": "强优势",
    "Stable Advantage": "稳定优势",
    "Needs Improvement": "有待提升",
    "Clear Weakness": "明显短板",
    "No Data": "待采集",
    "GT Win": "环球位列第一",
    "GT Top3": "环球进入 Top3",
    "Weak Citation": "环球已引用但未进 Top3",
    "Competitor Win": "竞品胜出",
    "No Effective Competition": "未形成有效竞争",
    "High Match": "高匹配",
    "Medium Match": "中等匹配",
    "Low Match": "低匹配",
    "Unverified": "未验证",
    "running": "运行中",
    "completed": "已完成",
    "completed_with_errors": "完成但有错误",
    "failed": "失败",
}
ACCESS_ZH = {
    "verified": "原文可读取",
    "verified_tls_fallback": "原文可读取",
    "blocked": "网站限制访问",
    "network_error": "暂时无法连接",
    "http_error": "页面返回错误",
    "unsupported_pdf": "PDF 暂未读取",
    "no_article_text": "未取得有效正文",
    "extract_error": "正文读取失败",
    "not_audited": "等待检查",
}
ACCESS_HELP = {
    "verified": "页面可以打开，并已取得足够的文章正文，可用于判断文章与 AI 回答是否匹配。",
    "verified_tls_fallback": "页面可以打开，并已取得足够的文章正文，可用于内容匹配。",
    "blocked": "目标网站返回 401、403 或 429，通常是反爬、登录、限流或地区访问策略导致。",
    "network_error": "检查时未能连接目标网站；引用仍然保留，只是暂时无法读取原文。",
    "http_error": "目标网站返回非 2xx 状态，例如跳转异常、404 或服务端错误。",
    "unsupported_pdf": "AI 引用了 PDF，当前版本保留引用记录，暂不解析 PDF 正文。",
    "no_article_text": "页面能打开，但抽取出的正文少于 80 个词，常见于索引页、脚本渲染页或需要二次加载的页面。",
    "extract_error": "页面返回了内容，但正文解析器处理失败。",
    "not_audited": "引用已经记录，原文读取任务尚未完成。",
}
PRIORITY_ZH = {
    "High Priority": "高优先级",
    "Medium Priority": "中优先级",
    "Maintain": "保持优势",
    "Collect First": "优先采集",
}


@st.cache_data(show_spinner=False, ttl=30)
def get_real_data(db_version: int, platform: str) -> dict[str, pd.DataFrame]:
    _ = db_version
    return load_real_data(platform=platform)


def real_db_version() -> int:
    return DEFAULT_DB_PATH.stat().st_mtime_ns if DEFAULT_DB_PATH.exists() else 0


def configured_provider() -> str:
    provider = os.getenv("ASTI_PROVIDER", DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
    return provider if provider in PROVIDER_LABELS else DEFAULT_PROVIDER


def configured_value(env_name: str, default: str = "") -> str:
    value = os.getenv(env_name, "").strip()
    if value:
        return value
    try:
        return str(st.secrets.get(env_name, default)).strip()
    except (FileNotFoundError, KeyError):
        return default


def zh_topic(value: object) -> str:
    return TOPIC_ZH.get(str(value), str(value))


def zh_media(value: object) -> str:
    text = str(value)
    return MEDIA_ZH.get(text, text)


def pct(value: float) -> str:
    return f"{float(value):.1f}%"


def display_position(value: object) -> str:
    return "未出现" if pd.isna(value) or value in {None, ""} else str(int(float(value)))


def metric_row(items: list[tuple[str, str, str]]) -> None:
    columns = st.columns(len(items))
    for column, (label, value, help_text) in zip(columns, items):
        column.metric(label, value, help=help_text)


def status_text(value: object) -> str:
    return STATUS_ZH.get(str(value), str(value))


def priority_text(value: object) -> str:
    return PRIORITY_ZH.get(str(value), str(value))


def access_text(value: object) -> str:
    return ACCESS_ZH.get(str(value), str(value))


def longtail_advice(topic: str, cited_count: int, deep_score: float, dominant: str) -> str:
    if cited_count and deep_score >= 70:
        return "保持具体型号、数字和场景化细节，并增加可索引参数表与连续更新入口。"
    if cited_count and deep_score >= 55:
        return "原文已具召回力；补足因果依据、边界条件和可引用数据，减少 AI 自行延伸。"
    if cited_count:
        return "召回成功但支撑偏弱；把核心主张、证据和结论写在同一正文页，并明确哪些是事实、哪些是专家判断。"
    topic_actions = {
        "China Military": "为具体型号建立英文专题页，集中参数、试验节点、高清图注、视频转录和更新日志，争夺专业防务来源位置。",
        "China Diplomacy": "把表态型报道整理成事件时间线、涉及国家、正式行动和原文引述，降低纯评论比重。",
        "US-China Relations": "围绕双边贸易和政策变化提供可下载数据表、方法说明与 FAQ，增强对政府和智库来源的竞争力。",
        "China EV": "增加车型级销量、技术参数、价格和海外市场对比表，避免关键数字只能由行业转载站二次组织。",
        "Taiwan Strait": "强化现场采访、参与者原话和事件后续，形成可持续更新的跨海峡事件页。",
        "South China Sea": "将法律论证、原始文件、巡航事实和时间线分层呈现，避免把观点与行动证据混在一起。",
    }
    fallback = f"当前更偏好 {zh_media(dominant)}；补充可验证的一手事实、结构化数据和持续更新页面。"
    return topic_actions.get(topic, fallback)


def latest_capture_text(data: dict[str, pd.DataFrame]) -> str:
    answers = data["answers"]
    successful = answers[answers["status"] == "success"] if not answers.empty else answers
    if successful.empty:
        return "尚未采集"
    value = pd.to_datetime(successful["captured_at"].max(), errors="coerce", utc=True)
    if pd.isna(value):
        return str(successful["captured_at"].max())
    return value.tz_convert("Asia/Shanghai").strftime("%Y-%m-%d %H:%M")


def target_score_row(data: dict[str, pd.DataFrame]) -> pd.Series | None:
    scores = data["scores"]
    target = scores[scores["media_name"] == TARGET_MEDIA] if not scores.empty else scores
    return None if target.empty else target.iloc[0]


def topic_chart(diagnostics: pd.DataFrame) -> None:
    view = diagnostics.copy()
    view["领域"] = view["topic"].map(zh_topic)
    view = view.sort_values(["topic_source_preference", "topic_coverage"], ascending=[True, True])
    plot_data = view.melt(
        id_vars=["领域"],
        value_vars=["topic_coverage", "topic_source_preference", "content_evidence_rate"],
        var_name="指标",
        value_name="比例",
    )
    plot_data["指标"] = plot_data["指标"].map(
        {
            "topic_coverage": "AI 引用覆盖率",
            "topic_source_preference": "Top3 率",
            "content_evidence_rate": "原文引用覆盖率",
        }
    )
    fig = px.bar(
        plot_data,
        x="比例",
        y="领域",
        color="指标",
        orientation="h",
        barmode="group",
        text_auto=".0f",
        color_discrete_map={
            "任意引用位覆盖率": "#3b82f6",
            "Top3 率": "#0f766e",
            "原文引用覆盖率": "#d97706",
        },
        labels={"比例": "占该领域成功回答的比例（%）"},
    )
    fig.update_xaxes(range=[0, 100])
    fig.update_layout(height=510, legend_title_text="报告指标", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)


def render_overview(data: dict[str, pd.DataFrame], summary: dict) -> None:
    score = target_score_row(data)
    diagnostics = data["topic_diagnostics"].copy()
    st.markdown("### 核心结论")
    st.caption("本报告从是否被 AI 引用、是否进入引用前三位，以及被引文章是否真正支持回答三个层面评估环球时报英文站的信源表现。")
    if score is None:
        metric_row(
            [
                ("有效回答", str(summary["successful_answers"]), "ChatGPT 成功返回并入库的回答；不同日期的复测分别计入。"),
                ("环球 AI 覆盖率", "0.0%", "环球时报出现在任意引用位置的回答数 / 全部成功回答。"),
                ("环球 Top3 率", "0.0%", "环球时报位于引用位置 1–3 的回答数 / 全部成功回答。"),
                ("原文引用覆盖率", "0.0%", "引用环球时报且能读取原文的回答数 / 全部成功回答。"),
                ("内容匹配度", "待形成", "比较环球时报原文与 AI 回答内容的一致程度。"),
            ]
        )
        st.warning("当前真实样本尚未在引用源中发现环球时报。这个结果本身就是监测信号。")
    else:
        metric_row(
            [
                ("有效回答", str(int(score["total_prompt_count"])), "ChatGPT 成功返回并入库的回答；所有媒体使用同一个分母。"),
                ("环球 AI 覆盖率", pct(score["ai_visibility"]), f"环球时报在 {int(score['cited_prompt_count'])} 个回答的任意引用位置出现。"),
                ("环球 Top3 率", pct(score["top3_rate"]), f"环球时报在 {int(score['top3_prompt_count'])} 个回答中位于引用位置 1–3。"),
                ("原文引用覆盖率", pct(score["content_evidence_rate"]), f"{int(score['verified_prompt_count'])} 个回答中的环球引用可以读取原文。"),
                ("内容匹配度", f"{score['content_support_score']:.1f}", "衡量被引环球原文与 AI 回答内容的平均匹配程度。"),
            ]
        )

    observed = diagnostics[diagnostics["prompt_count"] > 0].copy()
    if observed.empty:
        st.warning("尚未完成固定问题矩阵采集，暂时无法形成领域判断。")
    else:
        strongest = observed.sort_values(
            ["topic_source_preference", "topic_coverage", "content_evidence_rate"], ascending=False
        ).iloc[0]
        priority = observed.sort_values(
            ["topic_source_preference", "topic_coverage", "content_evidence_rate"], ascending=True
        ).iloc[0]
        leader = zh_media(priority["dominant_competitor"]) if priority["dominant_competitor"] else "尚未识别"
        st.markdown(
            f"""
            <div class="report-conclusion">
              <div><span>表现最强</span><b>{zh_topic(strongest['topic'])}</b><small>Top3 {strongest['topic_source_preference']:.1f}%</small></div>
              <div><span>优先补强</span><b>{zh_topic(priority['topic'])}</b><small>AI 覆盖 {priority['topic_coverage']:.1f}%</small></div>
              <div><span>主要对标</span><b>{leader}</b><small>当前弱项领域的领先信源</small></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.info(f"**本期首要行动：** {priority['recommendation']}")

    st.subheader("八大领域表现")
    topic_chart(diagnostics)

    st.subheader("媒体表现排名")
    scores = data["scores"].copy()
    if scores.empty:
        st.caption("暂无真实信源排名。")
    else:
        top_scores = scores.head(8).copy()
        chart_data = top_scores.melt(
            id_vars=["media_name"],
            value_vars=["ai_visibility", "top3_rate", "content_evidence_rate"],
            var_name="指标",
            value_name="比例",
        )
        chart_data["信源"] = chart_data["media_name"].map(zh_media)
        chart_data["指标"] = chart_data["指标"].map(
            {"ai_visibility": "AI 引用覆盖率", "top3_rate": "Top3 率", "content_evidence_rate": "原文引用覆盖率"}
        )
        fig = px.bar(
            chart_data,
            x="信源",
            y="比例",
            color="指标",
            barmode="group",
            color_discrete_map={"AI 引用覆盖率": "#3b82f6", "Top3 率": "#0f766e", "原文引用覆盖率": "#d97706"},
        )
        fig.update_yaxes(range=[0, 100], title="占全部成功回答的比例（%）")
        fig.update_layout(legend_title_text="报告指标", height=430)
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("查看完整媒体排名与统计口径", expanded=False):
            scores.insert(0, "排名", range(1, len(scores) + 1))
            scores["信源"] = scores["media_name"].map(zh_media)
            scores["AI 引用回答"] = scores.apply(lambda row: f"{int(row['cited_prompt_count'])} / {int(row['total_prompt_count'])}", axis=1)
            scores["Top3 回答"] = scores.apply(lambda row: f"{int(row['top3_prompt_count'])} / {int(row['total_prompt_count'])}", axis=1)
            scores["有原文引用的回答"] = scores.apply(lambda row: f"{int(row['verified_prompt_count'])} / {int(row['total_prompt_count'])}", axis=1)
            view = scores.rename(
                columns={
                    "ai_visibility": "AI 引用覆盖率",
                    "top3_rate": "Top3 率",
                    "content_evidence_rate": "原文引用覆盖率",
                    "content_support_score": "内容匹配度",
                    "citation_count": "原始引用次数",
                }
            )
            st.dataframe(
                view[["排名", "信源", "AI 引用回答", "AI 引用覆盖率", "Top3 回答", "Top3 率", "有原文引用的回答", "原文引用覆盖率", "内容匹配度", "原始引用次数"]],
                hide_index=True,
                use_container_width=True,
            )
            st.caption(
                "排序用于阅读顺序，不输出难以解释的综合分：Top3 率 50%、AI 引用覆盖率 25%、"
                "原文引用覆盖率 20%、内容匹配度 5%。所有媒体使用相同的全量回答分母。"
            )

    trend = data["daily_trend"].copy()
    st.subheader("按日趋势")
    if trend.empty:
        st.caption("完成至少一天采集后显示趋势。")
    else:
        trend = trend.rename(
            columns={
                "date": "日期",
                "coverage_rate": "环球 AI 引用覆盖率",
                "organic_top3_rate": "环球 Top3 率",
                "content_evidence_rate": "环球原文引用覆盖率",
                "content_support_score": "环球内容匹配度",
            }
        )
        fig = px.line(trend, x="日期", y=["环球 AI 引用覆盖率", "环球 Top3 率", "环球原文引用覆盖率", "环球内容匹配度"], markers=True)
        fig.update_yaxes(range=[0, 100], title="比例 / 支持度")
        fig.update_layout(legend_title_text="指标")
        st.plotly_chart(fig, use_container_width=True)


def render_topics(data: dict[str, pd.DataFrame]) -> None:
    diagnostics = data["topic_diagnostics"].copy()
    st.caption("每次选择一个领域，按“表现结论 → 竞品差距 → 提升动作 → 原始样本”完成一次诊断。")
    selected_topic = st.selectbox("选择领域", diagnostics["topic"].tolist(), format_func=zh_topic, key="topic_detail")
    row = diagnostics[diagnostics["topic"] == selected_topic].iloc[0]
    metric_row(
        [
            ("回答样本", str(int(row["prompt_count"])), "该领域已成功采集的全部回答；比例均以此为分母。"),
            ("环球 AI 覆盖率", pct(row["topic_coverage"]), f"环球时报在 {int(row['target_cited_prompts'])} 个回答的任意引用位置出现。"),
            ("环球 Top3 率", pct(row["topic_source_preference"]), f"环球时报在 {int(row['target_top3_prompts'])} 个回答中位于引用位置 1–3。"),
            ("原文引用覆盖率", pct(row["content_evidence_rate"]), f"{int(row['content_evidence_prompts'])} 个回答中的环球引用可以读取原文。"),
            ("内容匹配度", f"{row['content_match_score']:.1f}", "比较被引环球原文与 AI 回答内容的一致程度。"),
        ]
    )
    conclusion_col, advice_col = st.columns(2)
    with conclusion_col:
        st.markdown("#### 监测结论")
        st.info(row["finding"])
        st.caption(f"样本判断：{row['sample_strength']}。问题明细可在本页底部按需展开。")
    with advice_col:
        st.markdown("#### 提升方向")
        st.success(row["recommendation"])
        st.caption(f"优先级：{priority_text(row['priority'])}")

    st.subheader("该领域的媒体表现对比")
    sources = data["sources"]
    topic_sources = sources[
        (sources["topic"] == selected_topic)
        & (sources["query_intent"].isin(CORE_QUERY_INTENTS))
    ].copy()
    if topic_sources.empty:
        st.caption("该领域尚无真实引用。")
    else:
        per_prompt = (
            topic_sources.groupby(["media_name", "answer_id"], as_index=False)
            .agg(引用次数=("record_id", "count"), 最佳位置=("source_position", "min"))
        )
        competition = (
            per_prompt.assign(进入Top3=lambda frame: (frame["最佳位置"] <= 3).astype(int))
            .groupby("media_name")
            .agg(引用次数=("引用次数", "sum"), 覆盖问题=("answer_id", "nunique"), Top3问题=("进入Top3", "sum"), 平均位置=("最佳位置", "mean"))
            .reset_index()
            .sort_values(["Top3问题", "覆盖问题", "平均位置"], ascending=[False, False, True])
        )
        total_topic_answers = max(1, int(row["prompt_count"]))
        competition["AI 引用覆盖率"] = competition["覆盖问题"] / total_topic_answers * 100
        competition["Top3 率"] = competition["Top3问题"] / total_topic_answers * 100
        topic_matches = data["content_matches"][
            (data["content_matches"]["topic"] == selected_topic)
            & (data["content_matches"]["query_intent"].isin(CORE_QUERY_INTENTS))
            & (data["content_matches"]["valid_evidence"].fillna(False))
        ]
        if not topic_matches.empty:
            evidence = (
                topic_matches.groupby("media_name")
                .agg(有原文的问题=("answer_id", "nunique"), 内容匹配度=("content_match_score", "mean"))
                .reset_index()
            )
            competition = competition.merge(evidence, on="media_name", how="left")
        else:
            competition["有原文的问题"] = 0
            competition["内容匹配度"] = 0.0
        competition["有原文的问题"] = pd.to_numeric(competition["有原文的问题"], errors="coerce").fillna(0).astype(int)
        competition["内容匹配度"] = pd.to_numeric(competition["内容匹配度"], errors="coerce").fillna(0.0)
        competition["原文引用覆盖率"] = competition["有原文的问题"] / total_topic_answers * 100
        competition["信源"] = competition["media_name"].map(zh_media)
        plot_data = competition.head(12).melt(
            id_vars=["信源"],
            value_vars=["AI 引用覆盖率", "Top3 率", "原文引用覆盖率"],
            var_name="指标",
            value_name="比例",
        )
        fig = px.bar(
            plot_data,
            x="信源",
            y="比例",
            color="指标",
            barmode="group",
            color_discrete_map={"AI 引用覆盖率": "#3b82f6", "Top3 率": "#0f766e", "原文引用覆盖率": "#d97706"},
        )
        fig.update_yaxes(range=[0, 100], title="占该领域全部回答的比例（%）")
        st.plotly_chart(fig, use_container_width=True)
        with st.expander("查看媒体表现数据", expanded=False):
            st.dataframe(
                competition[["信源", "引用次数", "覆盖问题", "AI 引用覆盖率", "Top3问题", "Top3 率", "有原文的问题", "原文引用覆盖率", "内容匹配度", "平均位置"]],
                hide_index=True,
                use_container_width=True,
            )

    st.subheader("主要竞品差距与提升方案")
    report = build_topic_playbook(
        selected_topic,
        data["prompts"],
        data["answers"],
        data["sources"],
        data["content_matches"],
    )
    competitor_name = str(report["dominant_competitor"] or "")
    if not competitor_name:
        st.info("当前领域尚未形成足够的竞品样本；完成更多真实采集后再生成差距方案。")
    else:
        gt_metrics = report["target_metrics"]
        competitor_metrics = report["competitor_metrics"]
        average_position = f"{gt_metrics['avg_position']:.1f}" if gt_metrics["avg_position"] else "未出现"
        metric_row(
            [
                ("累计回答样本", str(report["tested_questions"]), "纳入该领域的全部成功回答；同一问题在不同日期的回答会分别统计。"),
                ("主要竞品", zh_media(competitor_name), "按 Top3 回答数、覆盖回答数和平均位置识别。"),
                ("环球当前覆盖", pct(gt_metrics["coverage_rate"]), "环球时报出现在当前领域 AI 引用源中的比例，不要求原文抓取成功。"),
                ("竞品当前覆盖", pct(competitor_metrics["coverage_rate"]), f"{zh_media(competitor_name)} 出现在 AI 引用源中的比例。"),
                ("环球平均位置", average_position, "按 AI 返回的原始引用位置计算，越接近 1 越好。"),
            ]
        )
        st.caption(
            "对比使用该领域累计的全部真实回答；文章结构对比只使用成功取得正文的引用。数字、引语和归因密度是页面结构观察指标，"
            "不等同于事实正确性。"
        )
        gap_tab, evidence_tab, action_tab = st.tabs(["差在哪", "证据是什么", "怎么提升"])
        with gap_tab:
            st.markdown("#### 本轮观察到竞品怎么做")
            for observation in report["observations"]:
                st.write(f"- {observation.replace(competitor_name, zh_media(competitor_name))}")
            st.markdown("#### Top 5 领先信源矩阵")
            competitor_ranking = report["competitor_ranking"].copy()
            competitor_ranking["领先信源"] = competitor_ranking["领先信源"].map(zh_media)
            st.dataframe(competitor_ranking, hide_index=True, use_container_width=True)
            comparison = report["comparison"].rename(columns={competitor_name: zh_media(competitor_name)})
            st.markdown("#### 环球与主要竞品直接对照")
            st.dataframe(comparison, hide_index=True, use_container_width=True)
            st.markdown("#### 差距诊断")
            gaps = report["gaps"].copy()
            gaps["判断"] = gaps["判断"].str.replace(competitor_name, zh_media(competitor_name), regex=False)
            st.dataframe(gaps, hide_index=True, use_container_width=True)
        with evidence_tab:
            st.markdown("#### AI 为什么优先引用这些竞品文章")
            st.caption(
                "文章视角：这里展示主要竞品被 AI 实际引用、并排在环球时报之前的文章。"
                "“支持 AI 回答的原文片段”是该页面中与回答最相关的正文，可用来观察竞品提供了哪些事实、数字和语境。"
            )
            examples = report["competitor_examples"]
            if examples.empty:
                st.caption("暂时没有可验证的竞品全文样本。")
            else:
                examples = examples.rename(
                    columns={
                        "问题": "用户问了什么",
                        "竞品位置": "AI 引用排名",
                        "竞品文章": "AI 选择的竞品文章",
                        "正文词数": "文章长度",
                        "全文匹配": "对回答的支持分",
                        "竞品链接": "查看竞品原文",
                    }
                )
                with st.expander(f"查看竞品胜出文章（{len(examples)}）", expanded=False):
                    st.dataframe(
                        examples,
                        hide_index=True,
                        use_container_width=True,
                        column_config={"查看竞品原文": st.column_config.LinkColumn("查看竞品原文", display_text="打开原文")},
                    )
            st.markdown("#### 环球时报下一步应该补哪些内容")
            st.caption(
                "问题视角：每一行代表一个当前没有赢过竞品的用户问题。系统把这个问题直接转成内容任务，"
                "告诉编辑应该新建或改造什么页面、补哪些证据，以及下一轮如何验收。"
            )
            lost = report["lost_prompts"].copy()
            if lost.empty:
                st.success("当前样本中没有竞品排在环球之前的问题。")
            else:
                lost["胜出竞品"] = lost["胜出竞品"].map(zh_media)
                lost["GT 位置"] = lost["GT 位置"].map(display_position)
                lost = lost.rename(
                    columns={
                        "未赢问题": "用户问了什么",
                        "胜出竞品": "AI 优先引用谁",
                        "竞品位置": "竞品排名",
                        "GT 位置": "环球排名",
                        "竞品文章": "竞品用哪篇文章赢",
                        "竞品怎么做": "竞品页面有什么",
                        "建议页面": "建议建设页面",
                        "环球怎么提升": "页面必须补什么",
                        "验收指标": "下一轮怎么验收",
                        "支持片段": "竞品关键证据",
                        "竞品链接": "查看竞品原文",
                    }
                )
                with st.expander(f"查看未赢问题与内容机会（{len(lost)}）", expanded=False):
                    st.dataframe(
                        lost,
                        hide_index=True,
                        use_container_width=True,
                        column_config={"查看竞品原文": st.column_config.LinkColumn("查看竞品原文", display_text="打开原文")},
                    )
        with action_tab:
            st.markdown("#### 逐题改进任务")
            prompt_actions = report["prompt_actions"].copy()
            if prompt_actions.empty:
                st.success("当前没有需要针对竞品补位的问题。")
            else:
                prompt_actions["对标竞品"] = prompt_actions["对标竞品"].map(zh_media)
                with st.expander(f"查看逐题改进任务（{len(prompt_actions)}）", expanded=False):
                    st.dataframe(
                        prompt_actions,
                        hide_index=True,
                        use_container_width=True,
                        column_config={"对标链接": st.column_config.LinkColumn("对标链接", display_text="打开竞品页")},
                    )
            st.markdown("#### 领域专属内容资产")
            st.caption("P0 先补当前输掉的具体问题，P1 建设该领域的可持续内容资产，P2 用连续监测验证效果。")
            actions = report["actions"].copy()
            for column in ["对标差距", "怎么做"]:
                actions[column] = actions[column].str.replace(competitor_name, zh_media(competitor_name), regex=False)
            st.dataframe(actions, hide_index=True, use_container_width=True)
            st.markdown("#### 30/60/90 天路线图")
            st.dataframe(report["roadmap"], hide_index=True, use_container_width=True)
            export_csv = (
                "[逐题改进任务]\n"
                + prompt_actions.to_csv(index=False)
                + "\n[领域专属内容资产]\n"
                + actions.to_csv(index=False)
                + "\n[30/60/90 天路线图]\n"
                + report["roadmap"].to_csv(index=False)
            )
            st.download_button(
                "下载本领域竞品提升方案",
                data=export_csv.encode("utf-8-sig"),
                file_name=f"asti_{selected_topic.lower().replace(' ', '_').replace('/', '_')}_playbook.csv",
                mime="text/csv",
            )

    outcomes = data["prompt_outcomes"][data["prompt_outcomes"]["topic"] == selected_topic].copy()
    if outcomes.empty:
        st.caption("该领域尚无成功回答样本。")
    else:
        sample_view = outcomes.sort_values("captured_at", ascending=False).copy()
        sample_view["类型"] = sample_view["query_intent"].map(INTENT_ZH)
        sample_view["结果"] = sample_view["competition_result"].map(status_text)
        sample_view["第一信源"] = sample_view["winner"].map(zh_media).fillna("-")
        sample_view["环球是否出现"] = sample_view["target_position"].notna().map({True: "是", False: "否"})
        sample_view["环球位置"] = sample_view["target_position"].map(display_position)
        with st.expander(f"查看该领域全部回答样本（{len(sample_view)}）", expanded=False):
            st.caption("同一问题在不同日期的回答分别计入，不按问题去重。")
            st.dataframe(
                sample_view[["answer_id", "captured_at", "类型", "question", "citation_count", "环球是否出现", "环球位置", "结果", "第一信源"]].rename(
                    columns={
                        "answer_id": "回答 ID",
                        "captured_at": "采集时间",
                        "question": "问题",
                        "citation_count": "全部引用数",
                    }
                ),
                hide_index=True,
                use_container_width=True,
            )

    prompts = data["prompts"][data["prompts"]["topic"] == selected_topic].copy()
    with st.expander(f"查看固定问题池（{len(prompts)} 个问题）", expanded=False):
        prompt_config = prompts.copy()
        prompt_config["类型"] = prompt_config["query_intent"].map(INTENT_ZH)
        st.dataframe(
            prompt_config[["prompt_id", "类型", "question"]].rename(columns={"prompt_id": "问题 ID", "question": "固定问题"}),
            hide_index=True,
            use_container_width=True,
        )

    st.subheader("全部领域对照")
    comparison = diagnostics.copy()
    comparison["领域"] = comparison["topic"].map(zh_topic)
    comparison["主要竞品"] = comparison["dominant_competitor"].map(zh_media)
    comparison["状态"] = comparison["status"].map(status_text)
    comparison["优先级"] = comparison["priority"].map(priority_text)
    st.dataframe(
        comparison[["领域", "prompt_count", "target_cited_prompts", "topic_coverage", "target_top3_prompts", "topic_source_preference", "content_evidence_prompts", "content_evidence_rate", "content_match_score", "主要竞品", "状态", "优先级"]].rename(
            columns={
                "prompt_count": "回答样本",
                "target_cited_prompts": "AI 引用回答",
                "topic_coverage": "AI 引用覆盖率",
                "target_top3_prompts": "Top3 回答",
                "topic_source_preference": "Top3 率",
                "content_evidence_prompts": "有原文引用的回答",
                "content_evidence_rate": "原文引用覆盖率",
                "content_match_score": "内容匹配度",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )


def render_prompts(data: dict[str, pd.DataFrame]) -> None:
    outcomes = data["prompt_outcomes"].copy()
    if outcomes.empty:
        st.info("尚无问题结果。完成一次采集后，本页将逐题展示环球时报与主要竞品的引用表现。")
        return
    topic_options = ["全部"] + outcomes["topic"].drop_duplicates().tolist()
    result_options = ["全部"] + outcomes["competition_result"].drop_duplicates().tolist()
    topic_col, result_col = st.columns(2)
    selected_topic = topic_col.selectbox("领域", topic_options, format_func=lambda value: value if value == "全部" else zh_topic(value), key="prompt_topic")
    selected_result = result_col.selectbox("引用结果", result_options, format_func=lambda value: value if value == "全部" else status_text(value))
    filtered = outcomes.copy()
    if selected_topic != "全部":
        filtered = filtered[filtered["topic"] == selected_topic]
    if selected_result != "全部":
        filtered = filtered[filtered["competition_result"] == selected_result]

    metric_row(
        [
            ("环球被 AI 引用", str(int(outcomes["target_position"].notna().sum())), "环球时报出现在任意引用位置，包括位置 4 以后。"),
            ("环球进入 Top3", str(int(outcomes["competition_result"].isin(["GT Win", "GT Top3"]).sum())), "环球时报位于引用位置 1–3。"),
            ("环球第一信源", str(int((outcomes["competition_result"] == "GT Win").sum())), "环球时报位于引用位置 1。"),
            ("环球未被引用", str(int(outcomes["target_position"].isna().sum())), "该回答的全部引用源中没有环球时报。"),
        ]
    )
    view = filtered.copy()
    view["领域"] = view["topic"].map(zh_topic)
    view["类型"] = view["query_intent"].map(INTENT_ZH)
    view["结果"] = view["competition_result"].map(status_text)
    view["第一信源"] = view["winner"].map(zh_media)
    view["环球是否出现"] = view["target_position"].notna().map({True: "是", False: "否"})
    view["环球位置"] = view["target_position"].map(display_position)
    view["最强竞品"] = view["best_competitor"].map(zh_media)
    with st.expander(f"查看逐题结果（{len(view)}）", expanded=False):
        st.dataframe(
            view[["captured_at", "领域", "类型", "question", "citation_count", "环球是否出现", "环球位置", "结果", "第一信源", "最强竞品"]].rename(
                columns={"captured_at": "采集时间", "question": "问题", "citation_count": "全部引用数"}
            ),
            hide_index=True,
            use_container_width=True,
        )

    if filtered.empty:
        return
    with st.expander("查看单条 AI 回答及全部引用", expanded=False):
        labels = {int(row["answer_id"]): f"{zh_topic(row['topic'])} | {status_text(row['competition_result'])} | {row['question'][:70]}" for row in filtered.to_dict("records")}
        selected_answer_id = st.selectbox("选择一条回答", list(labels), format_func=lambda value: labels[value])
        answer = data["answers"][data["answers"]["answer_id"] == selected_answer_id].iloc[0]
        st.markdown(f"**问题：** {answer['question']}")
        st.markdown("**AI 回答：**")
        st.write(answer["answer_text"])
        citations = data["citations"][data["citations"]["answer_id"] == selected_answer_id].sort_values("source_position")
        st.caption(f"该回答共记录 {len(citations)} 条唯一引用，按 AI 返回顺序展示。")
        for citation in citations.to_dict("records"):
            title = citation.get("article_title") or citation["source_title"] or citation["domain"]
            status = access_text(citation.get("access_status") or "not_audited")
            raw_words = citation.get("article_word_count")
            words = int(raw_words) if pd.notna(raw_words) else 0
            st.markdown(
                f"{int(citation['source_position'])}. [{title}]({citation['source_url']}) · "
                f"{zh_media(citation['media_name'])} · {citation['domain']} · {status} · {words} 词"
            )


def render_citations(data: dict[str, pd.DataFrame]) -> None:
    matches = data["content_matches"].copy()
    st.caption(
        "系统读取 AI 给出的引用文章，并比较文章正文与回答内容。无法打开的链接仍计入 AI 引用覆盖率和 Top3 率，"
        "但不计入原文引用覆盖率和内容匹配度。"
    )
    if matches.empty:
        st.info("暂无真实引用。")
        return
    topic_options = ["全部"] + matches["topic"].drop_duplicates().tolist()
    media_options = ["全部"] + matches["media_name"].drop_duplicates().tolist()
    access_options = ["全部"] + matches["access_status"].fillna("not_audited").drop_duplicates().tolist()
    topic_col, media_col, access_col = st.columns(3)
    selected_topic = topic_col.selectbox("领域", topic_options, format_func=lambda value: value if value == "全部" else zh_topic(value), key="citation_topic")
    selected_media = media_col.selectbox("信源", media_options, format_func=lambda value: value if value == "全部" else zh_media(value))
    selected_access = access_col.selectbox("访问状态", access_options, format_func=lambda value: value if value == "全部" else access_text(value))
    filtered = matches.copy()
    if selected_topic != "全部":
        filtered = filtered[filtered["topic"] == selected_topic]
    if selected_media != "全部":
        filtered = filtered[filtered["media_name"] == selected_media]
    if selected_access != "全部":
        filtered = filtered[filtered["access_status"].fillna("not_audited") == selected_access]

    status_summary = (
        filtered.assign(access_status=filtered["access_status"].fillna("not_audited"))
        .groupby("access_status")
        .agg(引用数=("record_id", "count"))
        .reset_index()
    )
    if not status_summary.empty:
        status_summary["访问状态"] = status_summary["access_status"].map(access_text)
        status_summary["是否可比较内容"] = status_summary["access_status"].isin(["verified", "verified_tls_fallback"]).map({True: "是", False: "否"})
        with st.expander("查看链接读取情况", expanded=False):
            st.dataframe(
                status_summary[["访问状态", "引用数", "是否可比较内容"]].sort_values("引用数", ascending=False),
                use_container_width=True,
                hide_index=True,
            )
            selected_statuses = status_summary.sort_values("引用数", ascending=False)["access_status"].tolist()
            for status in selected_statuses:
                st.markdown(f"**{access_text(status)}**：{ACCESS_HELP.get(status, '暂无说明。')}")

    verified = filtered[filtered["valid_evidence"].fillna(False)].copy()
    average_match = float(verified["content_match_score"].mean()) if not verified.empty else 0.0
    verified_rate = len(verified) / len(filtered) * 100 if len(filtered) else 0.0
    metric_row(
        [
            ("原始引用", str(len(filtered)), "ChatGPT 返回且已写入数据库的引用记录。"),
            ("可读取原文", str(len(verified)), "可以打开并取得有效正文的引用数。"),
            ("原文可读率", pct(verified_rate), "可读取原文的引用占当前筛选引用的比例。"),
            ("内容匹配度", f"{average_match:.1f}", "被引文章正文与 AI 回答内容的平均匹配程度。"),
        ]
    )
    ranking = (
        verified.groupby("media_name")
        .agg(
            可读原文=("record_id", "count"),
            内容匹配度=("content_match_score", "mean"),
            平均位置=("source_position", "mean"),
            涉及域名=("domain", lambda values: ", ".join(sorted(set(str(v) for v in values if pd.notna(v)))[:5])),
        )
        .reset_index()
        .sort_values("可读原文", ascending=False)
    )
    if not ranking.empty:
        ranking["信源"] = ranking["media_name"].map(zh_media)
        fig = px.bar(
            ranking.head(15),
            x="信源",
            y="可读原文",
            color="内容匹配度",
            color_continuous_scale="Blues",
            range_color=[0, 100],
            hover_data=["涉及域名", "平均位置"],
        )
        fig.update_layout(xaxis_title="信源（已按媒体合并，子域名放在悬浮信息里）")
        st.plotly_chart(fig, use_container_width=True)

    view = filtered.sort_values(["valid_evidence", "content_match_score"], ascending=[False, False], na_position="last").copy()
    view["领域"] = view["topic"].map(zh_topic)
    view["信源"] = view["media_name"].map(zh_media)
    view["访问状态"] = view["access_status"].fillna("not_audited").map(access_text)
    view["匹配等级"] = view["match_level"].map(status_text)
    with st.expander(f"查看文章内容匹配明细（{len(view)}）", expanded=False):
        st.dataframe(
            view[["领域", "question", "信源", "article_title", "source_position", "访问状态", "article_word_count", "content_match_score", "匹配等级", "best_matching_passage", "source_url"]].rename(
                columns={
                    "question": "问题",
                    "article_title": "文章标题",
                    "source_position": "引用位置",
                    "article_word_count": "正文词数",
                    "content_match_score": "内容匹配度",
                    "best_matching_passage": "与回答最相关的原文片段",
                    "source_url": "引用原文",
                }
            ),
            hide_index=True,
            use_container_width=True,
            column_config={"引用原文": st.column_config.LinkColumn("引用原文", display_text="打开原文")},
        )


def render_collection(
    data: dict[str, pd.DataFrame],
    provider: str,
    platform: str,
    model: str,
    api_key: str,
    key_env: str,
) -> None:
    with st.expander("查看每日监测问题", expanded=False):
        selected_topic = st.selectbox("选择领域", [item["topic"] for item in TOPIC_STRATEGY], format_func=zh_topic, key="collection_topic")
        prompts = data["prompts"][data["prompts"]["topic"] == selected_topic].copy()
        prompts["问题类型"] = prompts["query_intent"].map(INTENT_ZH)
        prompts["问题来源"] = prompts["prompt_kind"].map({"broad": "通用问题", "gt_longtail": "近期文章长尾"})
        st.dataframe(
            prompts[["prompt_id", "问题来源", "问题类型", "question", "core_fact", "intelligence_value", "cluster_size", "seed_article_url"]].rename(
                columns={
                    "prompt_id": "ID",
                    "question": "问题",
                    "core_fact": "核心事实",
                    "intelligence_value": "信息价值",
                    "cluster_size": "关联报道数",
                    "seed_article_url": "来源文章",
                }
            ),
            hide_index=True,
            use_container_width=True,
            column_config={"来源文章": st.column_config.LinkColumn("来源文章", display_text="查看原文")},
        )

    st.subheader("采集状态")
    if api_key:
        st.success("ChatGPT 采集连接已配置")
    else:
        st.error("ChatGPT 采集连接未配置；当前只能查看历史数据。")
    action_col, command_col = st.columns([1, 2])
    with action_col:
        if st.button("测试采集 1 条", type="primary", disabled=not bool(api_key)):
            with st.spinner("正在调用联网模型并保存回答与引用..."):
                result = collect_prompts(api_key=api_key, provider=provider, model=model, limit=1, delay_seconds=0)
            get_real_data.clear()
            if result["error_count"]:
                st.error("测试采集失败，请查看下方错误记录。")
            else:
                st.success("测试采集成功。")
            st.rerun()
    with command_col:
        st.caption("完整一轮包含 8 个领域、80 个问题：")
        st.code("./scripts/collect_daily.sh", language="bash")

    st.subheader("每日自动运行")
    st.write("安装后，macOS 会每天上午 9 点运行完整监测；电脑需处于开机和唤醒状态。")
    install_col, uninstall_col = st.columns(2)
    install_col.code("./scripts/install_daily_schedule.sh", language="bash")
    uninstall_col.code("./scripts/uninstall_daily_schedule.sh", language="bash")
    st.caption("页面不会自动创建定时任务，避免未经确认产生调用费用。")

    st.subheader("采集批次")
    runs = data["runs"].copy()
    if runs.empty:
        st.caption("暂无采集批次。")
    else:
        runs["状态"] = runs["status"].map(status_text)
        st.dataframe(
            runs[["started_at", "completed_at", "状态", "total_prompts", "success_count", "error_count"]].rename(
                columns={
                    "started_at": "开始时间",
                    "completed_at": "完成时间",
                    "total_prompts": "问题数",
                    "success_count": "成功",
                    "error_count": "失败",
                }
            ),
            hide_index=True,
            use_container_width=True,
        )
    failed = data["answers"][data["answers"]["status"] == "error"]
    if not failed.empty:
        with st.expander("采集错误", expanded=True):
            st.dataframe(failed[["captured_at", "prompt_id", "question", "error_message"]], hide_index=True, use_container_width=True)


def render_corpus(data: dict[str, pd.DataFrame]) -> None:
    articles = data["gt_articles"].copy()
    weights = data["topic_weights"].copy()
    verified = articles[
        articles["access_status"].isin(["verified", "verified_tls_fallback"])
        & (articles["article_word_count"] >= 80)
    ].copy() if not articles.empty else articles
    if articles.empty or weights.empty:
        st.warning("尚未建立官网文章数据，完成文章采集后将显示领域权重和长尾问题。")
        return

    latest_date = weights["snapshot_date"].max()
    latest = weights[weights["snapshot_date"] == latest_date].copy()
    weighted_article_count = int(latest["article_count"].sum())
    metric_row(
        [
            ("抓取官网栏目", "7", "Source、Economy、China、Diplomacy、Military、World、Opinion。"),
            ("本轮抓取", str(len(articles)), "本地 SQLite 中保存的官网文章记录。"),
            ("取得全文", str(len(verified)), "成功提取至少 80 词文章正文并保存内容哈希。"),
            ("领域命中数", str(weighted_article_count), "近 21 天文章的多领域命中总数，一篇文章可能属于多个领域。"),
            ("权重日期", str(latest_date), "最新一版领域权重。"),
        ]
    )
    st.caption(
        "权重依据为环球时报官网公开文章语料。公式：近期发稿量 55% + 可验证第一手报道信号 20% + 战略重要性 25%，"
        "最后归一化为 100%。一篇文章可以进入多个领域。"
    )

    latest["领域"] = latest["topic"].map(zh_topic)
    latest["权重"] = latest["calculated_weight"] * 100
    latest["发稿占比"] = latest["volume_share"] * 100
    fig = px.bar(
        latest.sort_values("权重"),
        x="权重",
        y="领域",
        orientation="h",
        text=latest.sort_values("权重")["权重"].map(lambda value: f"{value:.1f}%"),
        color="权重",
        color_continuous_scale="Blues",
    )
    fig.update_layout(height=430, coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("查看领域权重数据", expanded=False):
        st.dataframe(
            latest[["领域", "article_count", "original_count", "发稿占比", "strategic_importance", "权重"]].rename(
                columns={
                    "article_count": "近期命中文章（可跨领域）",
                    "original_count": "第一手报道信号",
                    "strategic_importance": "重要性（1-5）",
                }
            ),
            hide_index=True,
            use_container_width=True,
        )

    st.subheader("近期文章样本")
    topic_options = latest.sort_values("calculated_weight", ascending=False)["topic"].tolist()
    selected_topic = st.selectbox("查看官网文章", topic_options, format_func=zh_topic, key="corpus_topic")
    sample_value = latest[latest["topic"] == selected_topic].iloc[0]["sample_urls_json"]
    sample_urls = json.loads(sample_value) if sample_value else []
    article_view = verified[verified["article_url"].isin(sample_urls)].sort_values(
        ["classification_score", "published_at"], ascending=False
    ).copy()
    article_view["访问状态"] = article_view["access_status"].map(access_text)
    with st.expander(f"查看{zh_topic(selected_topic)}文章（{len(article_view)}）", expanded=False):
        st.dataframe(
            article_view[["published_at", "source_section", "title", "article_word_count", "访问状态", "article_url"]].rename(
                columns={
                    "published_at": "发布时间",
                    "source_section": "官网栏目",
                    "title": "文章标题",
                    "article_word_count": "正文词数",
                    "article_url": "原文",
                }
            ),
            hide_index=True,
            use_container_width=True,
            column_config={"原文": st.column_config.LinkColumn("原文", display_text="打开")},
        )

    st.subheader("长尾问题表现")
    prompts = data["prompts"].copy()
    longtail = prompts[prompts["prompt_kind"] == "gt_longtail"].copy()
    longtail["领域"] = longtail["topic"].map(zh_topic)
    st.caption("长尾问题不包含媒体品牌名，只使用近期文章中的具体事实和事件；来源文章用于判断 AI 是否自主发现环球时报原文。")
    with st.expander(f"查看长尾问题清单（{len(longtail)}）", expanded=False):
        st.dataframe(
            longtail[["领域", "question", "core_fact", "cluster_size", "seed_article_title", "seed_article_url"]].rename(
                columns={
                    "question": "长尾问题",
                    "core_fact": "问题依据",
                    "cluster_size": "关联报道数",
                    "seed_article_title": "来源文章",
                    "seed_article_url": "查看原文",
                }
            ),
            hide_index=True,
            use_container_width=True,
            column_config={"查看原文": st.column_config.LinkColumn("查看原文", display_text="打开")},
        )

    answers = data["answers"]
    sources = data["sources"]
    valid_sources = sources[sources["valid_evidence"].fillna(False)] if not sources.empty else sources
    current_questions = set(longtail["question"].tolist())
    tested = answers[
        (answers["status"] == "success")
        & (answers["query_intent"] == "article_longtail")
        & (answers["question"].isin(current_questions))
    ]
    if tested.empty:
        st.info("长尾问题已经生成，尚未采集 AI 回答。")
    else:
        raw_topic_sources = sources[sources["answer_id"].isin(tested["answer_id"])] if not sources.empty else sources
        target = raw_topic_sources[
            raw_topic_sources["answer_id"].isin(tested["answer_id"])
            & (raw_topic_sources["media_name"] == TARGET_MEDIA)
        ]
        valid_target = valid_sources[
            valid_sources["answer_id"].isin(tested["answer_id"])
            & (valid_sources["media_name"] == TARGET_MEDIA)
        ]
        cluster_urls_by_question: dict[str, set[str]] = {}
        for prompt in longtail.to_dict("records"):
            try:
                supporting = json.loads(prompt.get("supporting_article_urls") or "[]")
            except (json.JSONDecodeError, TypeError):
                supporting = []
            cluster_urls_by_question[str(prompt["question"])] = set(
                [str(prompt.get("seed_article_url") or ""), *[str(url) for url in supporting]]
            )
        cluster_hit_ids: set[int] = set()
        for answer in tested.to_dict("records"):
            answer_urls = set(raw_topic_sources[raw_topic_sources["answer_id"] == answer["answer_id"]]["source_url"])
            if answer_urls & cluster_urls_by_question.get(str(answer["question"]), set()):
                cluster_hit_ids.add(int(answer["answer_id"]))
        metric_row(
            [
                ("已测长尾问题", str(tested["answer_id"].nunique()), "已经获得联网 AI 回答的文章长尾问题。"),
                ("环球 AI 引用", str(target["answer_id"].nunique()), "环球时报出现在任意引用位置的问题数，不要求网页抓取成功。"),
                ("长尾环球覆盖率", pct(target["answer_id"].nunique() / tested["answer_id"].nunique() * 100), "环球时报在长尾回答中的原始引用覆盖率。"),
                ("环球 Top3", str(target[target["source_position"] <= 3]["answer_id"].nunique()), "环球时报原始引用进入前三位的问题数。"),
                ("环球原文可读", str(valid_target["answer_id"].nunique()), "引用环球时报且可以读取文章原文的问题数。"),
                ("来源文章命中", str(len(cluster_hit_ids)), "AI 直接引用生成该问题的来源文章或同一组关联报道的问题数。"),
            ]
        )
        topic_rows = []
        for topic, topic_answers in tested.groupby("topic"):
            answer_ids = set(topic_answers["answer_id"])
            topic_sources = raw_topic_sources[raw_topic_sources["answer_id"].isin(answer_ids)]
            topic_valid_sources = valid_sources[valid_sources["answer_id"].isin(answer_ids)]
            topic_target = topic_sources[topic_sources["media_name"] == TARGET_MEDIA]
            topic_valid_target = topic_valid_sources[topic_valid_sources["media_name"] == TARGET_MEDIA]
            topic_cluster_hits = len(answer_ids & cluster_hit_ids)
            competitors = topic_sources[topic_sources["media_name"] != TARGET_MEDIA]
            dominant = ""
            if not competitors.empty:
                dominant = str(
                    competitors.groupby("media_name")["answer_id"]
                    .nunique()
                    .sort_values(ascending=False)
                    .index[0]
                )
            tested_count = topic_answers["answer_id"].nunique()
            cited_count = topic_target["answer_id"].nunique()
            valid_count = topic_valid_target["answer_id"].nunique()
            deep_score = (
                float(topic_valid_target["support_score"].mean())
                if not topic_valid_target.empty and topic_valid_target["support_score"].notna().any()
                else 0.0
            )
            if cited_count == 0 and dominant:
                diagnosis = f"未召回环球；AI 更偏好 {zh_media(dominant)}"
            elif cited_count == 0:
                diagnosis = "尚未引用环球，需继续扩大具体事件样本"
            elif valid_count == 0:
                diagnosis = "AI 已引用环球，但暂时无法读取原文"
            elif deep_score >= 70:
                diagnosis = "已召回且原文支撑较强"
            elif deep_score >= 55:
                diagnosis = "已召回，部分延伸判断缺少原文支撑"
            else:
                diagnosis = "已召回，但回答对原文存在明显过度解释"
            topic_rows.append(
                {
                    "领域": zh_topic(topic),
                    "测试问题": int(tested_count),
                    "环球 AI 覆盖": int(cited_count),
                    "环球覆盖率": cited_count / tested_count * 100 if tested_count else 0.0,
                    "环球 Top3": int(topic_target[topic_target["source_position"] <= 3]["answer_id"].nunique()),
                    "环球原文可读": int(valid_count),
                    "来源文章命中": int(topic_cluster_hits),
                    "内容匹配度": round(deep_score, 1),
                    "主要竞品": zh_media(dominant) if dominant else "-",
                    "诊断": diagnosis,
                    "提升建议": longtail_advice(topic, cited_count, deep_score, dominant),
                }
            )
        topic_summary = pd.DataFrame(topic_rows).sort_values("环球覆盖率", ascending=False)
        st.markdown("#### 各领域长尾问题诊断")
        fig = px.bar(
            topic_summary,
            x="领域",
            y="环球覆盖率",
            color="内容匹配度",
            text=topic_summary["环球覆盖率"].map(lambda value: f"{value:.0f}%"),
            color_continuous_scale="Blues",
            range_color=[0, 100],
        )
        fig.update_yaxes(range=[0, 100])
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(topic_summary, hide_index=True, use_container_width=True)

        outcomes = data["prompt_outcomes"]
        tested_view = tested.merge(
            outcomes[["answer_id", "winner", "target_position", "competition_result", "citation_count"]],
            on="answer_id",
            how="left",
        )
        tested_view["领域"] = tested_view["topic"].map(zh_topic)
        tested_view["结果"] = tested_view["competition_result"].map(status_text)
        tested_view["第一信源"] = tested_view["winner"].map(zh_media)
        tested_view["环球位置"] = tested_view["target_position"].map(display_position)
        with st.expander(f"查看长尾问题逐题结果（{len(tested_view)}）", expanded=False):
            st.dataframe(
                tested_view[["领域", "question", "结果", "第一信源", "环球位置", "citation_count"]].rename(
                    columns={"question": "长尾问题", "citation_count": "全部引用数"}
                ),
                hide_index=True,
                use_container_width=True,
            )


def render_evidence(data: dict[str, pd.DataFrame]) -> None:
    st.caption("本页保留完整回答、引用链接和文章内容，供现场查看与会后复核。")
    evidence_view = st.radio(
        "选择证据类型",
        ["逐题回答与引用", "文章内容匹配", "环球内容与长尾问题"],
        horizontal=True,
        label_visibility="collapsed",
    )
    if evidence_view == "逐题回答与引用":
        render_prompts(data)
    elif evidence_view == "文章内容匹配":
        render_citations(data)
    else:
        render_corpus(data)


def render_methodology(
    data: dict[str, pd.DataFrame],
    summary: dict,
    provider: str,
    platform: str,
    model: str,
    api_key: str,
    key_env: str,
) -> None:
    st.markdown("### 报告口径")
    st.write(
        "系统每天用固定问题向 ChatGPT 提问，完整保存回答中的引用链接，再抓取文章正文进行内容匹配。"
        "同一问题在不同日期的回答作为独立观察，用于判断引用表现是否稳定。"
    )
    metric_row(
        [
            ("监测天数", str(summary["monitoring_days"]), "已经产生成功回答的自然日数量。"),
            ("完成批次", str(summary["completed_runs"]), "已完成或部分完成的采集轮次。"),
            ("有效回答", str(summary["successful_answers"]), "ChatGPT 成功返回并保存的回答数。"),
            ("原始引用", str(summary["citations"]), "回答中实际返回并保存的全部唯一引用 URL。"),
            ("可读取原文", str(summary["verified_citations"]), "成功访问并取得有效文章正文的引用数。"),
            ("覆盖域名", str(summary["unique_domains"]), "引用涉及的不同来源域名数量。"),
        ]
    )
    st.markdown("### 三层判断")
    method_cols = st.columns(3)
    method_cols[0].info("**1. AI 引用覆盖率**\n\n环球时报出现在回答任意引用位置的问题占比。")
    method_cols[1].info("**2. Top3 率**\n\n环球时报进入引用前三位的问题占比，代表优先程度。")
    method_cols[2].info("**3. 内容匹配度**\n\n比较被引文章正文与 AI 回答内容是否一致。")
    st.caption(
        "无法打开原文的链接仍计入 AI 引用覆盖率和 Top3 率，但不计入内容匹配度。报告不输出 ASTI 总分，"
        "所有比例都直接显示样本数和统一分母。"
    )
    if api_key and st.toggle(
        "显示系统运行信息",
        value=False,
        help="用于查看问题矩阵、采集批次和运行错误；正式汇报时通常无需展开。",
    ):
        render_collection(data, provider, platform, model, api_key, key_env)


ensure_prompt_config()
provider = configured_provider()
platform = PROVIDER_LABELS[provider]
key_env, model_env, default_model = provider_environment(provider)
api_key = configured_value(key_env)
model = configured_value(model_env, default_model) or default_model
data = get_real_data(real_db_version(), platform)
summary = real_summary(data)


st.markdown(
    """
    <style>
    .block-container {padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1500px;}
    div[data-testid="stMetric"] {background:#fff; border:1px solid #e3e7ed; border-radius:8px; padding:14px 16px;}
    .status-band {display:flex; gap:1rem; align-items:center; padding:.7rem 1rem; border:1px solid #dce4ec; border-radius:8px; background:#f8fafc; margin:.4rem 0 1.1rem;}
    .status-live {color:#126a45; background:#e5f5ec; border-radius:999px; padding:.2rem .65rem; font-weight:700;}
    .status-empty {color:#8a5a00; background:#fff3d6; border-radius:999px; padding:.2rem .65rem; font-weight:700;}
    .status-copy {color:#4c5867; font-size:.93rem;}
    .insight-box {display:grid; grid-template-columns:1fr auto; gap:.7rem 1rem; border:1px solid #e2e7ef; border-radius:8px; padding:1rem 1.1rem; background:#f8fafc; line-height:1.5;}
    .insight-box span {color:#647082;}
    .report-conclusion {display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.8rem; margin:.9rem 0;}
    .report-conclusion div {border:1px solid #dde4ec; border-radius:8px; padding:1rem; background:#f8fafc; min-width:0;}
    .report-conclusion span,.report-conclusion small {display:block; color:#647082;}
    .report-conclusion b {display:block; margin:.3rem 0; color:#162033; font-size:1.05rem;}
    div[data-testid="stTabs"] button {font-weight:650;}
    @media (max-width: 700px) {.status-band{align-items:flex-start; flex-direction:column;} .insight-box,.report-conclusion{grid-template-columns:1fr;}}
    </style>
    """,
    unsafe_allow_html=True,
)


with st.sidebar:
    st.title("报告导航")
    st.caption("环球时报英文站 AI 信源表现")
    st.markdown("**监测对象**  环球时报英文站")
    st.markdown("**监测平台**  ChatGPT")
    st.markdown("**问题范围**  8 个领域 / 80 个固定问题")
    st.markdown("**最近采集**")
    st.write(latest_capture_text(data))
    st.divider()
    st.markdown("**报告章节**")
    st.caption("01 核心结论\n\n02 分领域诊断\n\n03 证据与样本\n\n04 方法与数据")
    if st.button("刷新数据", use_container_width=True):
        get_real_data.clear()
        st.rerun()


st.title("环球时报 AI 信源表现监测报告")
st.caption("基于固定问题矩阵持续观察环球时报英文站在 AI 回答中的可见度、优先引用情况与内容支撑能力。")
status_class = "status-live" if summary["successful_answers"] else "status-empty"
status_label = "已形成真实样本" if summary["successful_answers"] else "等待首次采集"
st.markdown(
    f"""
    <div class="status-band">
      <span class="{status_class}">{status_label}</span>
      <span class="status-copy">ChatGPT · 8 个领域 · 80 个固定问题 · 累计 {summary['successful_answers']} 个真实回答 · 持续监测</span>
    </div>
    """,
    unsafe_allow_html=True,
)

overview_tab, topics_tab, evidence_tab, method_tab = st.tabs(
    ["01 核心结论", "02 分领域诊断", "03 证据与样本", "04 方法与数据"]
)
with overview_tab:
    render_overview(data, summary)
with topics_tab:
    render_topics(data)
with evidence_tab:
    render_evidence(data)
with method_tab:
    render_methodology(data, summary, provider, platform, model, api_key, key_env)

st.caption(
    f"报告版本：{PROMPT_CONFIG_VERSION}。结果代表 ChatGPT 在本报告固定问题和采集时间下的联网回答，"
    "不同账号、地区和会话可能产生差异。"
)
