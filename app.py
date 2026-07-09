from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from engine.competition import (
    absence_loss_by_topic,
    head_to_head,
    source_win_rate,
    topic_competitor_heatmap,
)
from engine.config import (
    CHINESE_SITE,
    CORE_COMPETITORS,
    CORE_QUERY_INTENTS,
    STRATEGIC_TOPICS,
    STRATEGIC_WEIGHTS,
    TARGET_MEDIA,
)
from engine.data_generator import DATA_SCHEMA_VERSION, ensure_data, generate_all_data, load_data
from engine.visibility import (
    compute_visibility_summary,
    media_citation_ranking,
    target_breakdown,
    target_query_intent_coverage,
    target_site_split,
)


st.set_page_config(
    page_title="ASTI 媒体智能 Demo",
    page_icon="ASTI",
    layout="wide",
)


PAGE_KEYS = {
    "管理总览": "overview",
    "AI 可见度": "visibility",
    "信源竞争": "competition",
    "议题权威": "topic_authority",
    "深度归因案例": "deep_cases",
    "行动建议": "recommendations",
}

TOPIC_ZH = {
    "China Diplomacy": "中国外交",
    "China Military": "中国军事",
    "South China Sea": "南海",
    "Taiwan Strait": "台海",
    "US-China Relations": "中美关系",
    "China Economy": "中国经济",
    "China EV": "中国电动车",
    "China Technology/AI": "中国科技与 AI",
    "Climate & Green Transition": "气候与绿色转型",
    "Global Governance": "全球治理",
    "Science & Society": "科学与社会",
    "Public Health": "公共卫生",
    "Overall": "整体",
}

INTENT_ZH = {
    "neutral": "中立查询",
    "timely": "时效查询",
    "comparison": "比较查询",
    "event": "事件查询",
    "analysis": "分析查询",
    "brand_search": "品牌查询",
}

LANGUAGE_ZH = {
    "English": "英语",
    "Chinese": "中文",
    "French": "法语",
    "Spanish": "西班牙语",
    "Arabic": "阿拉伯语",
    "Multilingual": "多语种",
}

STATUS_ZH = {
    "Strong Win": "高质量胜出案例",
    "Competitive": "进入竞争",
    "Weak Presence": "弱引用",
    "Absence Loss": "缺席损失",
    "No Strategic Competition": "无战略竞争",
    "Strong Advantage": "强优势",
    "Stable Advantage": "稳定优势",
    "Needs Improvement": "有待提升",
    "Clear Weakness": "明显短板",
}

PRIORITY_ZH = {
    "High Priority": "高优先级",
    "Medium Priority": "中优先级",
    "Low Priority": "低优先级",
}

CATEGORY_ZH = {
    "Coverage": "覆盖率",
    "Source Preference": "信源偏好",
    "Citation Quality": "引用质量",
    "Attribution": "内容归因",
    "Absence Loss": "缺席损失",
    "Monitoring": "持续监测",
    "Organic Visibility": "自然可见度",
    "Content Packaging": "内容包装",
    "Competitive Benchmark": "竞争基准",
    "Deep Attribution": "深度归因",
}

MEDIA_ZH = {
    "Global Times": "环球时报英文站",
    "Huanqiu": "环球网中文站",
    "Reuters": "路透社",
    "BBC": "英国广播公司",
    "AP News": "美联社",
    "Bloomberg": "彭博社",
    "Financial Times": "金融时报",
    "The Guardian": "卫报",
    "New York Times": "纽约时报",
    "Washington Post": "华盛顿邮报",
    "Wall Street Journal": "华尔街日报",
    "Xinhua": "新华社",
    "China Daily": "中国日报",
    "CGTN": "中国国际电视台",
    "People's Daily": "人民日报",
    "CCTV": "央视",
    "SCMP": "南华早报",
    "The Diplomat": "外交学者",
    "Nikkei Asia": "日经亚洲",
    "Al Jazeera": "半岛电视台",
    "CFR": "美国外交关系协会",
    "CSIS": "战略与国际研究中心",
    "Carnegie": "卡内基国际和平基金会",
    "Brookings": "布鲁金斯学会",
    "IEA": "国际能源署",
    "WHO": "世界卫生组织",
    "NASA": "美国国家航空航天局",
    "Wikipedia": "维基百科",
    "Gov.cn": "中国政府网",
    "MFA China": "中国外交部",
}

COLUMN_ZH = {
    "media_name": "媒体",
    "domain": "域名",
    "country_region": "国家/地区",
    "language": "语言",
    "media_type": "媒体类型",
    "cluster": "媒体集群",
    "overall_asti_score": "整体 ASTI",
    "strategic_asti_score": "战略 ASTI",
    "ai_visibility": "AI 可见度",
    "source_preference": "信源偏好",
    "citation_quality": "引用质量",
    "topic_authority_avg": "领域权威均值",
    "topic": "议题",
    "topic_zh": "议题",
    "status": "状态",
    "topic_authority_score": "议题权威分",
    "topic_coverage": "议题覆盖率",
    "topic_source_preference": "议题信源偏好",
    "topic_citation_quality": "议题引用质量",
    "topic_attribution_score": "议题归因分",
    "strategic_weight": "战略权重",
    "weighted_contribution": "加权贡献",
    "query_intent": "查询意图",
    "ai_platform": "AI 平台",
    "question": "问题",
    "prompt": "问题",
    "prompt_id": "Prompt ID",
    "case_id": "案例 ID",
    "gt_present": "GT 是否出现",
    "gt_position": "GT 位置",
    "best_competitor": "最强竞品",
    "best_competitor_position": "竞品位置",
    "competitor": "竞品",
    "competitor_position": "竞品位置",
    "position_gap": "位置差",
    "competitive_status": "竞争状态",
    "shared_cases": "共同出现次数",
    "gt_wins": "GT 胜出",
    "competitor_wins": "竞品胜出",
    "ties": "持平",
    "gt_head_to_head_win_rate": "GT 对位胜率",
    "avg_position_gap": "平均位置差",
    "absence_losses": "缺席损失数",
    "effective_cases": "有效竞争样本",
    "absence_loss_rate": "缺席损失率",
    "cases": "案例数",
    "top3_cases": "Top3 次数",
    "source_win_rate": "信源胜率",
    "citations": "引用次数",
    "coverage_rate": "覆盖率",
    "winning_source": "胜出信源",
    "final_attribution_score": "最终归因分",
    "fact_contribution_score": "事实贡献",
    "freshness_score": "新鲜度",
    "data_density_score": "数据密度",
    "narrative_contribution_score": "叙事贡献",
    "content_authority_score": "内容权威",
    "priority": "优先级",
    "category": "类别",
    "issue": "问题",
    "action": "具体行动",
    "expected_metric": "预期提升指标",
    "selection_reason": "入选原因",
    "recommendation": "建议",
}


@st.cache_data(show_spinner=False)
def get_data(schema_version: str = DATA_SCHEMA_VERSION) -> dict:
    _ = schema_version
    ensure_data()
    return load_data()


def refresh_data() -> None:
    generate_all_data()
    get_data.clear()


def percent(value: float) -> str:
    return f"{value:.1f}%"


def zh_topic(value: str) -> str:
    return TOPIC_ZH.get(str(value), str(value))


def zh_media(value: str) -> str:
    return MEDIA_ZH.get(str(value), str(value))


def zh_question(topic: str, intent: str, brand: str = TARGET_MEDIA) -> str:
    topic_name = zh_topic(topic)
    brand_name = zh_media(brand)
    templates = {
        "neutral": f"{topic_name}当前处于什么状态？",
        "timely": f"{topic_name}近期有哪些最新进展？",
        "comparison": f"中外信源如何不同地解释{topic_name}？",
        "event": f"最近哪些事件正在影响{topic_name}？",
        "analysis": f"为什么{topic_name}对全球政治与市场重要？",
        "brand_search": f"{brand_name}如何报道{topic_name}？",
    }
    return templates.get(str(intent), f"请分析{topic_name}。")


def zh_answer_summary(topic: str) -> str:
    return (
        f"模拟 AI 回答通常会综合政策信号、事件时间线、官方表述、国际媒体报道与专家分析，"
        f"来解释{zh_topic(topic)}。"
    )


def zh_gt_summary(topic: str, present: bool, position: object) -> str:
    topic_name = zh_topic(topic)
    if not present or pd.isna(position):
        return f"环球时报英文站未被该模拟回答直接引用，因此没有贡献直接事实或叙事框架。"
    return (
        f"环球时报英文站出现在引用第 {int(position)} 位，主要贡献与{topic_name}相关的观点型框架；"
        "但在该模拟场景中，竞品通常拥有更强的数据密度、中立表述或结构化事实。"
    )


def zh_competitor_summary(topic: str, competitor: str, position: object) -> str:
    pos = "未知" if pd.isna(position) else int(position)
    return (
        f"{zh_media(competitor)}出现在引用第 {pos} 位，被模拟 AI 视为更易引用的信源，"
        f"在{zh_topic(topic)}上提供了更清晰的事实、上下文或专家式解释。"
    )


def zh_selection_reason(value: str) -> str:
    text = str(value)
    mapping = {
        "Absence Loss": "缺席损失",
        "Weak Citation": "弱引用",
        "Lost to Reuters": "输给 Reuters",
        "GT Top3 But Not Winning": "GT 进入 Top3 但未胜出",
        "Abnormal Drop": "异常下降",
    }
    if text.startswith("Lost to "):
        return f"输给 {zh_media(text.replace('Lost to ', ''))}"
    return mapping.get(text, text)


def zh_loss_reason(competitor: str) -> str:
    reasons = {
        "Reuters": "路透社胜出，主要因为其模拟内容具备更强的时效事实与中立国际表述。",
        "Bloomberg": "彭博社胜出，主要因为其市场数据、商业语境和量化解释更清晰。",
        "SCMP": "南华早报胜出，主要因为其更善于把中国议题转化为国际读者能理解的语境。",
        "Xinhua": "新华社胜出，主要因为其接近官方信源，并具备广泛的多语种分发能力。",
        "China Daily": "中国日报胜出，主要因为其英文摘要和政策解释更结构化。",
        "CGTN": "CGTN 胜出，主要因为其多媒体式摘要和跨语种可用性更强。",
        "CSIS": "CSIS 胜出，主要因为其安全议题专家分析和具名专家框架更强。",
        "CFR": "CFR 胜出，主要因为 AI 将其视为外交语境下的简明解释型信源。",
    }
    return reasons.get(competitor, f"{zh_media(competitor)}胜出，因为模拟回答认为它更适合作为该问题的引用信源。")


def zh_case_recommendation(topic: str, competitor: str, status: str) -> str:
    topic_name = zh_topic(topic)
    if status == "Absence Loss":
        return f"优先建设{topic_name}的英文结构化解释稿；当前 AI 选择了{zh_media(competitor)}，而环球时报英文站缺席。"
    if competitor in ["Reuters", "Bloomberg"]:
        return "增加原创数据、时间线、市场或政策证据，让文章更适合被 AI 直接引用。"
    if competitor in ["SCMP", "The Diplomat", "Nikkei Asia"]:
        return "增强国际读者语境，解释该议题为何影响中国以外的受众。"
    return "强化专家引语、事实摘要和实体一致性，提升 AI 的信源偏好。"


def zh_recommendation(row: dict) -> str:
    if row.get("action"):
        return str(row["action"])
    category = row.get("category", "")
    topic = zh_topic(row.get("topic", ""))
    messages = {
        "Coverage": f"建设{topic}的英文结构化专题页和高频解释稿，让 AI 更容易自然发现环球时报英文站。",
        "Source Preference": "增加原创数据、具名专家引语、简洁事实断言和中立比较稿，提高 Top3 选择率。",
        "Citation Quality": "优化文章结构，加入摘要要点、关键事实、时间线、表格和明确来源标注。",
        "Attribution": "沉淀独家数据点和更强叙事框架，让 AI 回答更可能借用该信源的事实与逻辑。",
        "Absence Loss": f"{topic}具有战略重要性，但竞品进入 Top3 时环球时报英文站缺席，应优先补强权威内容。",
        "Monitoring": "持续追踪 prompt 集群，并在竞品引用上升时刷新常青解释稿。",
        "Organic Visibility": "在每份客户报告中区分品牌搜索胜出与中立问题胜出，避免品牌查询夸大可见度。",
        "Content Packaging": "用稳定实体、日期、简洁摘要、数据表和清晰议题标签，为 AI 检索重新包装内容。",
        "Competitive Benchmark": "按议题对比路透社、新华社、中国日报、南华早报、CSIS 等竞品，而不是只看一个总排名。",
        "Deep Attribution": "只在高价值失分和战略事件中使用成本较高的 LLM 深度归因，不必覆盖每个 prompt。",
    }
    return messages.get(category, str(row.get("recommendation", "")))


def zh_value(value: object) -> object:
    if isinstance(value, bool):
        return "是" if value else "否"
    if pd.isna(value):
        return "未出现"
    text = str(value)
    for mapping in (TOPIC_ZH, INTENT_ZH, LANGUAGE_ZH, STATUS_ZH, PRIORITY_ZH, CATEGORY_ZH, MEDIA_ZH):
        if text in mapping:
            return mapping[text]
    if text.startswith("Lost to ") or text in [
        "Absence Loss",
        "Weak Citation",
        "GT Top3 But Not Winning",
        "Abnormal Drop",
    ]:
        return zh_selection_reason(text)
    return value


MEDIA_COLOR_MAP = {
    TARGET_MEDIA: "#d62728",
    "Huanqiu": "#d62728",
    "Reuters": "#1f77b4",
    "AP News": "#1f77b4",
    "BBC": "#1f77b4",
    "Bloomberg": "#1f77b4",
    "Financial Times": "#1f77b4",
    "The Guardian": "#1f77b4",
    "New York Times": "#1f77b4",
    "Washington Post": "#1f77b4",
    "Wall Street Journal": "#1f77b4",
    "Xinhua": "#ff7f0e",
    "China Daily": "#ff7f0e",
    "CGTN": "#ff7f0e",
    "People's Daily": "#ff7f0e",
    "CCTV": "#ff7f0e",
    "Gov.cn": "#ff7f0e",
    "MFA China": "#ff7f0e",
    "CFR": "#2ca02c",
    "CSIS": "#2ca02c",
    "Carnegie": "#2ca02c",
    "Brookings": "#2ca02c",
    "IEA": "#2ca02c",
    "WHO": "#2ca02c",
    "NASA": "#2ca02c",
}


def media_color(media_name: str) -> str:
    return MEDIA_COLOR_MAP.get(str(media_name), "#8c8c8c")


def localized_color_map(names: list[str]) -> dict:
    return {zh_media(name): media_color(name) for name in names}


def build_score_breakdown(row: pd.Series) -> pd.DataFrame:
    parts = [
        ("AI 可见度", float(row["ai_visibility"]), 0.20, "被 AI 发现并引用的广度。"),
        ("信源偏好", float(row["source_preference"]), 0.35, "自然查询中被选入 Top3 的能力。"),
        ("引用质量", float(row["citation_quality"]), 0.20, "引用位置越靠前，质量分越高。"),
        ("领域权威", float(row["topic_authority_avg"]), 0.25, "各领域覆盖、偏好、质量和归因的综合表现。"),
    ]
    return pd.DataFrame(
        [
            {
                "维度": name,
                "原始分": score,
                "权重": weight,
                "对总分贡献": score * weight,
                "说明": note,
            }
            for name, score, weight, note in parts
        ]
    )


def competition_funnel(prompts: pd.DataFrame, sources: pd.DataFrame, competition_cases: pd.DataFrame) -> pd.DataFrame:
    total_answers = prompts["prompt_id"].nunique()
    strategic = prompts[prompts["topic"].isin(STRATEGIC_TOPICS)]
    non_brand = strategic[strategic["query_intent"].isin(CORE_QUERY_INTENTS)]
    competitor_prompt_ids = sources[
        sources["prompt_id"].isin(non_brand["prompt_id"]) & sources["media_name"].isin(CORE_COMPETITORS)
    ]["prompt_id"].nunique()
    effective = competition_cases["prompt_id"].nunique()
    steps = [
        ("全量回答数", total_answers, "全部 Prompt 对应的 AI 回答，是第一层可见度监测基座。"),
        ("战略 Topic 样本数", strategic["prompt_id"].nunique(), "只保留客户战略相关议题。"),
        ("排除品牌指定查询后", non_brand["prompt_id"].nunique(), "去掉 brand_search，避免品牌指定查询抬高表现。"),
        ("出现核心竞品池", competitor_prompt_ids, "样本中至少出现 Reuters、新华社、SCMP、智库等核心竞品。"),
        ("Top3/Top5 有效竞争样本", effective, "GT 或竞品进入 Top3，或 GT 与竞品同时进入 Top5。"),
    ]
    return pd.DataFrame(
        [
            {
                "漏斗步骤": name,
                "样本数": count,
                "保留率": round(count / total_answers * 100, 1) if total_answers else 0,
                "说明": note,
            }
            for name, count, note in steps
        ]
    )


def localize_frame(frame: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    view = frame.copy()
    if columns is not None:
        for column in columns:
            if column not in view.columns:
                view[column] = ""
        view = view[columns].copy()
    for column in view.columns:
        if view[column].dtype == "object" or view[column].dtype == "bool":
            view[column] = view[column].map(zh_value)
    return view.rename(columns=COLUMN_ZH)


def metric_row(items: list[tuple[str, str, str]]) -> None:
    columns = st.columns(len(items))
    for col, (label, value, help_text) in zip(columns, items):
        col.metric(label, value, help=help_text)


def render_page_header(title: str, caption: str) -> None:
    st.markdown(f"## {title}")
    st.caption(caption)


def score_gauge(title: str, value: float, color: str = "#2454ff") -> go.Figure:
    return go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            title={"text": title},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": color},
                "steps": [
                    {"range": [0, 45], "color": "#f4d7d7"},
                    {"range": [45, 70], "color": "#fff1c2"},
                    {"range": [70, 100], "color": "#d7eddc"},
                ],
            },
        )
    )


st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 3rem;}
    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e8e8ee;
        border-radius: 8px;
        padding: 14px 16px;
        box-shadow: 0 1px 6px rgba(15, 23, 42, 0.04);
    }
    .asti-callout {
        border-left: 4px solid #2454ff;
        padding: 0.7rem 1rem;
        background: #f7f9ff;
        border-radius: 4px;
        margin: 0.5rem 0 1rem 0;
    }
    .mode-banner {
        display: flex;
        gap: 0.75rem;
        align-items: center;
        border: 1px solid #e8e8ee;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        background: #fff;
        margin-bottom: 1rem;
    }
    .mode-pill {
        border-radius: 999px;
        padding: 0.2rem 0.65rem;
        font-weight: 700;
        background: #fce8e8;
        color: #b42318;
    }
    .real-pill {
        border-radius: 999px;
        padding: 0.2rem 0.65rem;
        background: #eef6ff;
        color: #2454ff;
    }
    .small-note { color: #5f6673; font-size: 0.92rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

data = get_data()
prompts = data["prompts"]
media = data["media"]
answers = data["simulated_answers"]
sources = data["source_records"]
competition_cases = data["competition_cases"]
deep_cases = data["deep_attribution_cases"]
scores = data["asti_scores"]
topic_authority = data["topic_authority"]
recommendations = data["recommendations"]

visibility_summary = compute_visibility_summary(prompts, sources)
gt_score = scores[scores["media_name"] == TARGET_MEDIA].iloc[0]

with st.sidebar:
    st.title("ASTI 演示系统")
    page_label = st.radio("页面", list(PAGE_KEYS.keys()))
    page = PAGE_KEYS[page_label]
    st.divider()
    st.markdown("**目标媒体**")
    st.write(f"{zh_media(TARGET_MEDIA)}（{TARGET_MEDIA}）")
    st.markdown("**分析流程**")
    st.write("Prompt 矩阵 -> AI 可见度 -> 信源竞争 -> 深度归因 -> ASTI 评分")
    if st.button("重新生成模拟数据"):
        refresh_data()
        st.rerun()

st.title("ASTI 媒体智能 Demo")
st.caption("AI 信源权威分析系统：从 GenTrack AI 可见度监测升级到媒体 AI Source Intelligence。")
st.markdown(
    """
    <div class="mode-banner">
      <span class="mode-pill">当前数据模式：Mock Demo Data</span>
      <span class="real-pill">Real Data Mode 预留入口：Tavily / GDELT / Gemini API</span>
      <span class="small-note">未配置 API Key 时保持模拟数据模式。</span>
    </div>
    """,
    unsafe_allow_html=True,
)

if page == "overview":
    render_page_header(
        "管理总览",
        "面向管理层展示 AI 信源可见度、自然信源偏好、引用质量与战略议题权威。",
    )
    st.markdown(
        """
        <div class="asti-callout">
        <b>核心判断：</b>PV/UV 衡量的是直接访问流量；ASTI 衡量的是用户向 AI 提问时，
        AI 是否发现、信任、引用并优先选择某家媒体作为可信信源。
        </div>
        """,
        unsafe_allow_html=True,
    )

    metric_row(
        [
            ("整体 ASTI", f"{gt_score['overall_asti_score']:.1f}", "覆盖全部 prompt 与议题的综合得分。"),
            ("战略 ASTI", f"{gt_score['strategic_asti_score']:.1f}", "按环球时报重点中国议题加权后的得分。"),
            ("GT 覆盖率", percent(visibility_summary["target_media_coverage_rate"]), "包含品牌查询在内的 prompt 覆盖率。"),
            ("信源偏好", percent(gt_score["source_preference"]), "被召回后进入 Top3 的自然选择率。"),
            ("引用质量", f"{gt_score['citation_quality']:.1f}", "按引用位置加权后的质量分。"),
            ("领域权威均值", f"{gt_score['topic_authority_avg']:.1f}", "各领域权威分的平均值。"),
        ]
    )

    st.subheader("ASTI 分数拆解")
    st.markdown(
        """
        **Overall ASTI = AI 可见度 × 20% + 信源偏好 × 35% + 引用质量 × 20% + 领域权威 × 25%**

        Overall ASTI 反映全局 AI 信源表现；Strategic ASTI 只按客户战略 Topic 权重计算。
        因此，当 Global Times 在中国军事、中国外交、南海、台海等战略议题上更强，但在科技、公共卫生、
        科学社会等非核心或专业议题上较弱时，Strategic ASTI 会高于 Overall ASTI。
        """
    )
    breakdown = build_score_breakdown(gt_score)
    c_formula, c_contrib = st.columns([1, 1.25])
    with c_formula:
        st.dataframe(
            breakdown.assign(权重=breakdown["权重"].map(lambda value: f"{value:.0%}"))[
                ["维度", "原始分", "权重", "对总分贡献", "说明"]
            ],
            hide_index=True,
            use_container_width=True,
        )
    with c_contrib:
        fig = px.bar(
            breakdown,
            x="维度",
            y="对总分贡献",
            color="维度",
            color_discrete_map={
                "AI 可见度": "#8c8c8c",
                "信源偏好": "#d62728",
                "引用质量": "#ff7f0e",
                "领域权威": "#2ca02c",
            },
            text="对总分贡献",
        )
        fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
        fig.update_layout(showlegend=False, yaxis_title="贡献分")
        st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns([1, 1.35])
    with c1:
        fig = score_gauge("环球时报英文站整体 ASTI", float(gt_score["overall_asti_score"]))
        fig.update_layout(height=310, margin=dict(l=25, r=25, t=45, b=20))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        ranking = scores.head(15).copy()
        ranking["媒体"] = ranking["media_name"].map(zh_media)
        fig = px.bar(
            ranking.sort_values("overall_asti_score"),
            x="overall_asti_score",
            y="媒体",
            orientation="h",
            color="媒体",
            color_discrete_map=localized_color_map(ranking["media_name"].tolist()),
            labels={"overall_asti_score": "整体 ASTI", "媒体": "媒体"},
        )
        fig.update_layout(showlegend=False, height=360)
        st.plotly_chart(fig, use_container_width=True)

    comparison_set = [TARGET_MEDIA, "Reuters", "Xinhua", "China Daily", "SCMP", "CGTN"]
    comp = scores[scores["media_name"].isin(comparison_set)].copy()
    st.subheader("目标媒体与核心竞品对比")
    st.dataframe(
        localize_frame(
            comp,
            [
                "media_name",
                "overall_asti_score",
                "strategic_asti_score",
                "ai_visibility",
                "source_preference",
                "citation_quality",
            ],
        ),
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("关键发现")
    st.markdown(
        """
        - 品牌搜索会抬高可见度，因此 ASTI 会把诊断性的品牌查询与自然竞争查询分开计算。
        - 环球时报英文站在安全、外交等战略议题上表现更好，在科技、科学和专业领域相对较弱。
        - 路透社仍是最强的广谱竞品，因为它在中立、时效和市场导向问题中更容易胜出。
        - 深度归因只用于高价值失分案例，因为逐条答案做信源追踪的成本较高。
        """
    )

elif page == "visibility":
    render_page_header(
        "AI 可见度层",
        "第一层低成本监测：哪些信源出现、出现在哪里，以及覆盖率如何随平台和语言变化。",
    )
    metric_row(
        [
            ("Prompt 总数", f"{visibility_summary['total_prompts']:,}", "Prompt 矩阵规模。"),
            ("AI 回答数", f"{visibility_summary['total_ai_answers']:,}", "每个 prompt 对应一条模拟 AI 回答。"),
            ("引用总数", f"{visibility_summary['total_citations']:,}", "全部生成的信源引用记录。"),
            ("唯一信源数", f"{visibility_summary['unique_sources']:,}", "被引用的媒体与机构数量。"),
            ("GT 引用数", f"{visibility_summary['target_media_citations']:,}", "环球时报英文站的原始引用次数。"),
            ("GT Top3 率", percent(visibility_summary["top3_citation_rate"]), "GT 引用中进入 Top3 的比例。"),
        ]
    )

    intent_cov = target_query_intent_coverage(prompts, sources)
    intent_cov["查询意图"] = intent_cov["query_intent"].map(lambda x: INTENT_ZH.get(x, x))
    st.subheader("品牌指定查询影响检测")
    st.markdown(
        '<p class="small-note">品牌查询有诊断价值，但不能证明自然信源权威。</p>',
        unsafe_allow_html=True,
    )
    fig = px.bar(intent_cov, x="查询意图", y="coverage_rate", color="查询意图", labels={"coverage_rate": "GT 覆盖率 (%)"})
    fig.update_layout(showlegend=False, yaxis_title="GT 覆盖率 (%)")
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("引用次数 Top20 信源")
        ranking = media_citation_ranking(sources)
        ranking["媒体"] = ranking["media_name"].map(zh_media)
        fig = px.bar(
            ranking.sort_values("citations"),
            x="citations",
            y="媒体",
            orientation="h",
            color="媒体",
            color_discrete_map=localized_color_map(ranking["media_name"].tolist()),
            labels={"citations": "引用次数"},
        )
        fig.update_layout(height=500, yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader(f"{zh_media(TARGET_MEDIA)} vs {zh_media(CHINESE_SITE)}")
        split = target_site_split(sources)
        st.dataframe(localize_frame(split), hide_index=True, use_container_width=True)
        split["媒体"] = split["media_name"].map(zh_media)
        fig = px.bar(
            split,
            x="媒体",
            y="citations",
            color="媒体",
            color_discrete_map=localized_color_map(split["media_name"].tolist()),
            labels={"citations": "引用次数", "domain": "域名"},
        )
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        st.subheader("按 AI 平台的 GT 覆盖率")
        platform = target_breakdown(prompts, sources, "ai_platform")
        st.plotly_chart(px.bar(platform, x="ai_platform", y="coverage_rate", labels={"ai_platform": "AI 平台", "coverage_rate": "覆盖率 (%)"}), use_container_width=True)
    with c4:
        st.subheader("按语言的 GT 覆盖率")
        language = target_breakdown(prompts, sources, "language")
        language["语言"] = language["language"].map(lambda x: LANGUAGE_ZH.get(x, x))
        st.plotly_chart(px.bar(language, x="语言", y="coverage_rate", labels={"coverage_rate": "覆盖率 (%)"}), use_container_width=True)

elif page == "competition":
    render_page_header(
        "信源竞争层",
        "第二层分析：把所有引用过滤成真正具有战略意义的竞争场景。",
    )
    st.markdown(
        """
        <div class="asti-callout">
        <b>为什么第二层不是重复第一层：</b>第一层记录“AI 引用了谁”，用于低成本全量监测；
        第二层只筛出战略 Topic、非品牌指定查询、出现核心竞品且引用位置有意义的场景，
        用来回答“GT 是否在真正竞争中赢得信源位置”。
        </div>
        """,
        unsafe_allow_html=True,
    )
    funnel = competition_funnel(prompts, sources, competition_cases)
    st.subheader("有效竞争筛选漏斗")
    cf1, cf2 = st.columns([1.1, 1])
    with cf1:
        fig = go.Figure(
            go.Funnel(
                y=funnel["漏斗步骤"],
                x=funnel["样本数"],
                textinfo="value+percent initial",
                marker={"color": ["#8c8c8c", "#ff7f0e", "#d62728", "#1f77b4", "#2ca02c"]},
            )
        )
        fig.update_layout(height=360)
        st.plotly_chart(fig, use_container_width=True)
    with cf2:
        st.dataframe(funnel, hide_index=True, use_container_width=True)

    valid_cases = len(competition_cases)
    absence = absence_loss_by_topic(competition_cases)
    absence["议题"] = absence["topic"].map(zh_topic)
    status_counts = competition_cases["competitive_status"].value_counts().reset_index()
    status_counts.columns = ["competitive_status", "cases"]
    status_counts["竞争状态"] = status_counts["competitive_status"].map(lambda x: STATUS_ZH.get(x, x))
    metric_row(
        [
            ("有效竞争样本", f"{valid_cases:,}", "非品牌、战略议题且有明显竞品引用位置的样本。"),
            ("缺席损失案例", f"{int((competition_cases['competitive_status'] == 'Absence Loss').sum()):,}", "GT 缺席，同时核心竞品进入 Top3。"),
            ("弱引用案例", f"{int((competition_cases['competitive_status'] == 'Weak Presence').sum()):,}", "GT 出现但没有进入 Top3。"),
            ("高质量胜出案例", f"{int((competition_cases['competitive_status'] == 'Strong Win').sum()):,}", "GT 进入 Top3 且领先最强核心竞品。"),
        ]
    )

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("信源胜率排名")
        win = source_win_rate(competition_cases, sources).head(15)
        win["媒体"] = win["media_name"].map(zh_media)
        fig = px.bar(
            win.sort_values("source_win_rate"),
            x="source_win_rate",
            y="媒体",
            orientation="h",
            color="媒体",
            color_discrete_map=localized_color_map(win["media_name"].tolist()),
            labels={"source_win_rate": "信源胜率 (%)"},
        )
        fig.update_layout(xaxis_title="Top3 案例 / 有效竞争样本 (%)", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("竞争状态分布")
        fig = px.pie(status_counts, names="竞争状态", values="cases", hole=0.45)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("GT 对核心竞品基准")
    h2h = head_to_head(sources, ["Reuters", "Xinhua", "China Daily", "SCMP", "CGTN"])
    st.dataframe(localize_frame(h2h), hide_index=True, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        st.subheader("按议题的缺席损失")
        fig = px.bar(absence, x="议题", y="absence_loss_rate", hover_data=["absence_losses", "effective_cases"], labels={"absence_loss_rate": "缺席损失率 (%)"})
        fig.update_layout(xaxis_tickangle=-35, yaxis_title="缺席损失率 (%)")
        st.plotly_chart(fig, use_container_width=True)
    with c4:
        st.subheader("议题 x 最强竞品热力图")
        heat = topic_competitor_heatmap(competition_cases)
        heat["议题"] = heat["topic"].map(zh_topic)
        heat["最强竞品"] = heat["best_competitor"].map(zh_media)
        pivot = heat.pivot_table(index="议题", columns="最强竞品", values="cases", fill_value=0)
        fig = px.imshow(pivot, aspect="auto", color_continuous_scale="Blues", labels=dict(color="案例数"))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("有效竞争案例浏览")
    topic_options = sorted(competition_cases["topic"].unique())
    topic_labels = {zh_topic(topic): topic for topic in topic_options}
    selected_topic_labels = st.multiselect("议题", list(topic_labels.keys()))
    selected_platform = st.multiselect("AI 平台", sorted(competition_cases["ai_platform"].unique()))
    filtered = competition_cases.copy()
    if selected_topic_labels:
        filtered = filtered[filtered["topic"].isin([topic_labels[label] for label in selected_topic_labels])]
    if selected_platform:
        filtered = filtered[filtered["ai_platform"].isin(selected_platform)]
    filtered = filtered.head(200).copy()
    filtered["question"] = filtered.apply(lambda row: zh_question(row["topic"], row["query_intent"]), axis=1)
    st.dataframe(localize_frame(filtered), hide_index=True, use_container_width=True)

elif page == "topic_authority":
    render_page_header(
        "议题权威",
        "按议题评估环球时报英文站在哪些领域具备 AI 信源权威、在哪些领域稳定、在哪些领域偏弱。",
    )
    st.markdown(
        """
        状态分档：**80-100 强优势**，**60-79 稳定优势**，**40-59 有待提升**，**0-39 明显短板**。
        这套分档帮助客户区分“总体表现”与“可行动的领域诊断”。
        """
    )
    topic_sorted = topic_authority.sort_values("topic_authority_score", ascending=False).copy()
    topic_sorted["议题"] = topic_sorted["topic"].map(zh_topic)
    topic_sorted["状态"] = topic_sorted["status"].map(lambda x: STATUS_ZH.get(x, x))
    fig = px.bar(
        topic_sorted,
        x="议题",
        y="topic_authority_score",
        color="状态",
        color_discrete_map={
            "强优势": "#d62728",
            "稳定优势": "#ff7f0e",
            "有待提升": "#f2c94c",
            "明显短板": "#8c8c8c",
        },
        hover_data=["topic_coverage", "topic_source_preference", "topic_citation_quality", "topic_attribution_score"],
        labels={
            "topic_authority_score": "议题权威分",
            "topic_coverage": "议题覆盖率",
            "topic_source_preference": "议题信源偏好",
            "topic_citation_quality": "议题引用质量",
            "topic_attribution_score": "议题归因分",
        },
    )
    fig.update_layout(xaxis_tickangle=-35, yaxis_title="议题权威分")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("议题权威地图")
    st.dataframe(
        localize_frame(
            topic_sorted,
            [
                "topic",
                "status",
                "topic_authority_score",
                "topic_coverage",
                "topic_source_preference",
                "topic_citation_quality",
                "topic_attribution_score",
                "strategic_weight",
            ],
        ),
        hide_index=True,
        use_container_width=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("战略议题权重")
        weight_frame = pd.DataFrame(
            [{"议题": zh_topic(topic), "权重": weight * 100} for topic, weight in STRATEGIC_WEIGHTS.items()]
        )
        st.plotly_chart(px.bar(weight_frame, x="议题", y="权重"), use_container_width=True)
    with c2:
        st.subheader("对战略 ASTI 的贡献")
        contrib = topic_authority[topic_authority["topic"].isin(STRATEGIC_WEIGHTS.keys())].copy()
        contrib["议题"] = contrib["topic"].map(zh_topic)
        contrib["加权贡献"] = contrib["topic_authority_score"] * contrib["strategic_weight"]
        st.plotly_chart(px.bar(contrib, x="议题", y="加权贡献"), use_container_width=True)

elif page == "deep_cases":
    render_page_header(
        "深度归因层",
        "高成本分析只保留给最重要的 1%-5% 场景：信源缺失、位置劣势或战略价值较高的案例。",
    )
    metric_row(
        [
            ("深度案例数", f"{len(deep_cases):,}", "被选中的高价值案例。"),
            ("平均归因分", f"{deep_cases['final_attribution_score'].mean():.1f}", "最终归因分均值。"),
            ("GT 缺席案例", f"{int(deep_cases['gt_position'].isna().sum()):,}", "GT 没有直接信源贡献的案例数。"),
        ]
    )

    deep_view = deep_cases.copy()
    deep_view["prompt"] = deep_view.apply(lambda row: zh_question(row["topic"], row["query_intent"]), axis=1)
    st.dataframe(
        localize_frame(
            deep_view,
            [
                "case_id",
                "topic",
                "selection_reason",
                "query_intent",
                "ai_platform",
                "winning_source",
                "gt_position",
                "competitor_position",
                "final_attribution_score",
            ],
        ),
        hide_index=True,
        use_container_width=True,
    )

    case_id = st.selectbox("选择案例", deep_cases["case_id"].tolist())
    case = deep_cases[deep_cases["case_id"] == case_id].iloc[0]

    st.subheader(f"案例 {int(case['case_id'])}：{zh_topic(case['topic'])}")
    st.markdown(f"**入选原因：** {zh_selection_reason(case.get('selection_reason', ''))}")
    st.markdown(f"**问题：** {zh_question(case['topic'], case['query_intent'])}")
    st.markdown(f"**AI 回答摘要：** {zh_answer_summary(case['topic'])}")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**环球时报英文站信源摘要**")
        st.write(zh_gt_summary(case["topic"], pd.notna(case["gt_position"]), case["gt_position"]))
    with c2:
        st.markdown("**竞品信源摘要**")
        st.write(zh_competitor_summary(case["topic"], case["winning_source"], case["competitor_position"]))

    labels = ["事实贡献", "新鲜度", "数据密度", "叙事贡献", "内容权威"]
    values = [
        case["fact_contribution_score"],
        case["freshness_score"],
        case["data_density_score"],
        case["narrative_contribution_score"],
        case["content_authority_score"],
    ]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=values + [values[0]], theta=labels + [labels[0]], fill="toself"))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=False, height=420)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown(f"**失分原因：** {zh_loss_reason(case['winning_source'])}")
    st.markdown(
        f"**行动建议：** {zh_case_recommendation(case['topic'], case['winning_source'], competition_cases.loc[competition_cases['prompt_id'] == case['prompt_id'], 'competitive_status'].iloc[0] if not competition_cases.loc[competition_cases['prompt_id'] == case['prompt_id']].empty else '')}"
    )

elif page == "recommendations":
    render_page_header(
        "行动建议",
        "基于覆盖率、信源偏好、引用质量、内容归因和缺席损失信号生成行动计划。",
    )
    priority_options = ["高优先级", "中优先级", "低优先级"]
    reverse_priority = {label: key for key, label in PRIORITY_ZH.items()}
    selected_priority_labels = st.multiselect("优先级", priority_options, default=priority_options)
    selected_priority = [reverse_priority[label] for label in selected_priority_labels]
    rec = recommendations[recommendations["priority"].isin(selected_priority)].copy()
    rec["recommendation"] = rec.apply(lambda row: zh_recommendation(row.to_dict()), axis=1)

    metric_row(
        [
            ("高优先级", f"{int((recommendations['priority'] == 'High Priority').sum())}", "需要优先处理的战略改进项。"),
            ("中优先级", f"{int((recommendations['priority'] == 'Medium Priority').sum())}", "重要但紧急度略低的优化项。"),
            ("低优先级", f"{int((recommendations['priority'] == 'Low Priority').sum())}", "监测和维护类事项。"),
        ]
    )

    st.subheader("整体建议")
    overall = rec[rec["topic"] == "Overall"]
    for item in overall.to_dict("records"):
        st.markdown(
            f"**{PRIORITY_ZH.get(item['priority'], item['priority'])} - {CATEGORY_ZH.get(item['category'], item['category'])}**  \n"
            f"问题：{item.get('issue', '')}  \n"
            f"行动：{item.get('action', item['recommendation'])}  \n"
            f"预期提升：{item.get('expected_metric', '')}"
        )

    st.subheader("议题级建议")
    rec_table = rec[rec["topic"] != "Overall"].sort_values(["priority", "topic"]).copy()
    st.dataframe(
        localize_frame(
            rec_table,
            ["topic", "issue", "priority", "action", "expected_metric", "category"],
        ),
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("竞品解读")
    st.markdown(
        """
        - 输给路透社和彭博社，通常意味着数据密度、时间线或中立市场框架不足。
        - 输给南华早报和《外交学者》，通常意味着国际读者语境不足。
        - 输给新华社、中国日报和 CGTN，说明在中国相关国际传播议题中存在直接竞争。
        - 输给 CSIS 和 CFR，说明安全与外交议题需要更多专家型解释稿。
        """
    )
