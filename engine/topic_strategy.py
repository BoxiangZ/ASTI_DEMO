from __future__ import annotations

import csv
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_PATH = PROJECT_ROOT / "config" / "pilot_prompts.csv"
TOPIC_STRATEGY_PATH = PROJECT_ROOT / "config" / "topic_strategy.csv"
PROMPT_CONFIG_VERSION = "2026-07-16-researched-intelligence-longtail-v3"
RESEARCH_PATH = PROJECT_ROOT / "config" / "researched_longtails.json"


TOPIC_STRATEGY = [
    {
        "topic": "China Economy",
        "topic_zh": "中国经济与贸易",
        "editorial_frequency": "高频",
        "monitoring_priority": "P0",
        "strategic_weight": 0.18,
        "rationale": "经济、外贸、产业链和政策数据是环球时报近期更新最密集的内容主轴之一，也是 AI 回答最常引用通讯社和财经媒体的竞争区。",
        "evidence_url": "https://www.globaltimes.cn/source/economy/",
    },
    {
        "topic": "China Technology/AI",
        "topic_zh": "中国科技与 AI",
        "editorial_frequency": "高频",
        "monitoring_priority": "P0",
        "strategic_weight": 0.16,
        "rationale": "AI、机器人、半导体和科技治理在经济栏目持续高频出现，且直接关系中国创新叙事和国际科技竞争。",
        "evidence_url": "https://www.globaltimes.cn/source/economy/",
    },
    {
        "topic": "China Diplomacy",
        "topic_zh": "中国外交与全球治理",
        "editorial_frequency": "高频",
        "monitoring_priority": "P0",
        "strategic_weight": 0.15,
        "rationale": "外交栏目保持稳定高更新，覆盖外交部回应、领导人交往、多边机制和全球治理，是环球时报建立国际信源权威的核心领域。",
        "evidence_url": "https://www.globaltimes.cn/china/diplomacy/",
    },
    {
        "topic": "China Military",
        "topic_zh": "中国军事与国家安全",
        "editorial_frequency": "稳定高频",
        "monitoring_priority": "P0",
        "strategic_weight": 0.14,
        "rationale": "军事栏目具有稳定的专业更新和专家解释，是环球时报区别于一般综合媒体、争夺 AI 安全议题引用的重要资产。",
        "evidence_url": "https://www.globaltimes.cn/china/military/",
    },
    {
        "topic": "US-China Relations",
        "topic_zh": "中美关系与战略竞争",
        "editorial_frequency": "高频",
        "monitoring_priority": "P0",
        "strategic_weight": 0.13,
        "rationale": "中美经贸、科技限制和战略互动横跨外交、经济与评论栏目，事件驱动强，国际 AI 查询需求高。",
        "evidence_url": "https://www.globaltimes.cn/source/",
    },
    {
        "topic": "Taiwan Strait",
        "topic_zh": "台海与两岸关系",
        "editorial_frequency": "事件高频",
        "monitoring_priority": "P0",
        "strategic_weight": 0.10,
        "rationale": "台海议题贯穿外交和军事报道，具有高敏感度、高事件性和高国际关注，是必须单列的核心利益议题。",
        "evidence_url": "https://www.globaltimes.cn/china/military/",
    },
    {
        "topic": "South China Sea",
        "topic_zh": "南海与地区安全",
        "editorial_frequency": "事件高频",
        "monitoring_priority": "P1",
        "strategic_weight": 0.08,
        "rationale": "南海巡航、中菲互动、域外力量和海洋治理持续出现在军事与外交报道中，适合独立追踪信源竞争。",
        "evidence_url": "https://www.globaltimes.cn/china/military/",
    },
    {
        "topic": "China EV",
        "topic_zh": "中国新能源车与绿色转型",
        "editorial_frequency": "增长高频",
        "monitoring_priority": "P1",
        "strategic_weight": 0.06,
        "rationale": "新能源车、清洁能源和绿色供应链是中国经济国际叙事中的增长领域，也面临关税、产能和产业竞争话语。",
        "evidence_url": "https://www.globaltimes.cn/source/economy/",
    },
]


QUESTION_BANK = {
    "China Economy": [
        ("neutral", "What is the current state of China's economy, and which indicators best describe its momentum?"),
        ("neutral", "What are the main structural strengths and weaknesses of China's economy today?"),
        ("timely", "What are the latest developments affecting China's economic growth and domestic demand?"),
        ("timely", "What do the latest trade, investment, and industrial data show about China's economy?"),
        ("comparison", "How does China's current economic performance compare with other major economies?"),
        ("comparison", "How do Chinese and international sources differ in explaining China's economic outlook?"),
        ("event", "Which recent policy decisions or market events are having the greatest impact on China's economy?"),
        ("event", "How are recent global trade measures affecting Chinese companies and supply chains?"),
        ("analysis", "What factors will determine China's economic performance over the next twelve months?"),
        ("analysis", "How is industrial upgrading changing China's role in global trade and manufacturing?"),
    ],
    "China Technology/AI": [
        ("neutral", "What is the current state of China's artificial intelligence and advanced technology sectors?"),
        ("neutral", "Which Chinese technologies and companies are shaping the country's innovation ecosystem?"),
        ("timely", "What are the latest major developments in China's AI, robotics, and semiconductor industries?"),
        ("timely", "What new Chinese AI products, policies, or research breakthroughs have been announced recently?"),
        ("comparison", "How does China's AI development compare with that of the United States and Europe?"),
        ("comparison", "How do Chinese and Western sources differ in assessing China's technological capabilities?"),
        ("event", "Which recent export controls or technology restrictions are affecting China's tech sector?"),
        ("event", "How are recent AI governance decisions changing China's technology market?"),
        ("analysis", "What are China's main advantages and bottlenecks in the global AI competition?"),
        ("analysis", "How could China's technology development reshape global industry and governance?"),
    ],
    "China Diplomacy": [
        ("neutral", "What are China's main diplomatic priorities and foreign policy principles today?"),
        ("neutral", "How does China describe its role in global governance and international affairs?"),
        ("timely", "What are the latest developments in China's diplomacy and major-country relations?"),
        ("timely", "Which recent diplomatic visits or agreements are most important for China?"),
        ("comparison", "How does China's diplomatic approach compare with that of the United States?"),
        ("comparison", "How do Chinese and international sources differ in explaining China's foreign policy?"),
        ("event", "Which recent international events are most strongly shaping China's diplomatic agenda?"),
        ("event", "How has China responded to the latest major international conflict or geopolitical crisis?"),
        ("analysis", "What are the main strengths and constraints of China's current diplomacy?"),
        ("analysis", "How is China trying to influence the future of global governance and multilateral institutions?"),
    ],
    "China Military": [
        ("neutral", "What is the current state of China's military modernization and defense capabilities?"),
        ("neutral", "What are the main priorities of China's national defense strategy?"),
        ("timely", "What are the latest publicly reported developments involving China's military?"),
        ("timely", "What new Chinese military equipment, exercises, or defense policies have been reported recently?"),
        ("comparison", "How do China's military capabilities compare with those of other major powers in Asia?"),
        ("comparison", "How do Chinese and Western sources differ in assessing China's military modernization?"),
        ("event", "Which recent military exercise or security event involving China is most significant?"),
        ("event", "How has China responded to recent military activity by the United States or its allies in the region?"),
        ("analysis", "What are the strategic implications of China's naval, air, missile, and space capabilities?"),
        ("analysis", "Which factors are most likely to shape China's military development over the next five years?"),
    ],
    "US-China Relations": [
        ("neutral", "What is the current state of relations between China and the United States?"),
        ("neutral", "What are the main areas of cooperation and conflict in US-China relations?"),
        ("timely", "What are the latest developments in US-China diplomatic and economic relations?"),
        ("timely", "What recent US policy toward China has drawn the strongest response from Beijing?"),
        ("comparison", "How do Chinese and US sources differ in explaining the causes of bilateral tensions?"),
        ("comparison", "How does the current US-China relationship compare with its position one year ago?"),
        ("event", "Which recent meeting, sanction, tariff, or security event has most affected US-China relations?"),
        ("event", "How are recent technology and trade restrictions changing relations between China and the US?"),
        ("analysis", "What are the most likely scenarios for US-China relations over the next twelve months?"),
        ("analysis", "How does US-China strategic competition affect the global economy and international order?"),
    ],
    "Taiwan Strait": [
        ("neutral", "What is the current situation in the Taiwan Strait?"),
        ("neutral", "What are the main political and security issues shaping cross-Strait relations?"),
        ("timely", "What are the latest developments involving the Chinese mainland and Taiwan?"),
        ("timely", "What recent military or diplomatic activity has changed tensions in the Taiwan Strait?"),
        ("comparison", "How do mainland Chinese, Taiwan, and Western sources differ in describing cross-Strait tensions?"),
        ("comparison", "How does the current level of Taiwan Strait tension compare with one year ago?"),
        ("event", "Which recent statement, election decision, arms sale, or military activity most affected the Taiwan Strait?"),
        ("event", "How has Beijing responded to recent external involvement in Taiwan-related affairs?"),
        ("analysis", "What factors could increase or reduce tensions in the Taiwan Strait?"),
        ("analysis", "How do cross-Strait developments affect regional security and China-US relations?"),
    ],
    "South China Sea": [
        ("neutral", "What is the current situation in the South China Sea?"),
        ("neutral", "What are the main territorial, legal, and security issues in the South China Sea?"),
        ("timely", "What are the latest developments involving China and other countries in the South China Sea?"),
        ("timely", "What recent coast guard, naval, or diplomatic activity has affected South China Sea tensions?"),
        ("comparison", "How do Chinese, Philippine, ASEAN, and Western sources differ in describing South China Sea disputes?"),
        ("comparison", "How does China's South China Sea policy compare with the approaches of other claimant states?"),
        ("event", "Which recent maritime encounter or patrol in the South China Sea is most significant?"),
        ("event", "How have China and ASEAN responded to recent South China Sea incidents?"),
        ("analysis", "What are the prospects for a South China Sea Code of Conduct?"),
        ("analysis", "How does external military involvement affect stability in the South China Sea?"),
    ],
    "China EV": [
        ("neutral", "What is the current state of China's electric vehicle and new-energy industries?"),
        ("neutral", "Which companies and technologies are leading China's green industrial transition?"),
        ("timely", "What are the latest developments in Chinese electric vehicles, batteries, and clean energy?"),
        ("timely", "Which recent overseas market or policy change is most important for Chinese EV makers?"),
        ("comparison", "How do Chinese electric vehicles compare with US, European, Japanese, and Korean competitors?"),
        ("comparison", "How do Chinese and Western sources differ in assessing China's green manufacturing capacity?"),
        ("event", "How are recent tariffs or trade investigations affecting Chinese EV and clean-energy exports?"),
        ("event", "Which recent product launch, investment, or regulatory change is reshaping China's EV industry?"),
        ("analysis", "What are the main competitive advantages and risks facing China's EV industry?"),
        ("analysis", "How is China's green industrial expansion affecting the global energy transition?"),
    ],
}


def ensure_prompt_config(force: bool = False) -> None:
    expected_count = len(TOPIC_STRATEGY) * 10
    if not force and PROMPTS_PATH.exists() and TOPIC_STRATEGY_PATH.exists():
        try:
            with PROMPTS_PATH.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            versions = {row.get("config_version", "") for row in rows}
            if len(rows) == expected_count and versions == {PROMPT_CONFIG_VERSION}:
                return
        except (OSError, csv.Error):
            pass
    generate_prompt_config()


def generate_prompt_config() -> None:
    PROMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    prompt_fields = [
        "prompt_id",
        "topic",
        "query_intent",
        "language",
        "question",
        "is_brand_query",
        "strategic_importance",
        "prompt_kind",
        "seed_article_title",
        "seed_article_url",
        "seed_published_at",
        "core_fact",
        "intelligence_value",
        "supporting_article_urls",
        "cluster_size",
        "generation_method",
        "config_version",
    ]
    with PROMPTS_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=prompt_fields)
        writer.writeheader()
        prompt_id = 1
        for strategy in TOPIC_STRATEGY:
            importance = max(1, min(10, round(float(strategy["strategic_weight"]) * 50 + 2)))
            topic = str(strategy["topic"])
            seeds = _researched_longtails(topic, limit=4)
            questions: list[dict[str, object]] = [
                {
                    "query_intent": intent,
                    "question": question,
                    "prompt_kind": "broad",
                    "seed_article_title": "",
                    "seed_article_url": "",
                    "seed_published_at": "",
                    "core_fact": "",
                    "intelligence_value": "",
                    "supporting_article_urls": "[]",
                    "cluster_size": 0,
                    "generation_method": "stable_broad",
                }
                for intent, question in QUESTION_BANK[topic][: 10 - len(seeds)]
            ]
            questions.extend(seeds)
            for item in questions:
                writer.writerow(
                    {
                        "prompt_id": prompt_id,
                        "topic": topic,
                        "query_intent": item["query_intent"],
                        "language": "English",
                        "question": item["question"],
                        "is_brand_query": "false",
                        "strategic_importance": importance,
                        "prompt_kind": item["prompt_kind"],
                        "seed_article_title": item["seed_article_title"],
                        "seed_article_url": item["seed_article_url"],
                        "seed_published_at": item["seed_published_at"],
                        "core_fact": item["core_fact"],
                        "intelligence_value": item["intelligence_value"],
                        "supporting_article_urls": (
                            json.dumps(item["supporting_article_urls"], ensure_ascii=False)
                            if isinstance(item["supporting_article_urls"], list)
                            else item["supporting_article_urls"]
                        ),
                        "cluster_size": item["cluster_size"],
                        "generation_method": item["generation_method"],
                        "config_version": PROMPT_CONFIG_VERSION,
                    }
                )
                prompt_id += 1

    with TOPIC_STRATEGY_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TOPIC_STRATEGY[0].keys()))
        writer.writeheader()
        writer.writerows(TOPIC_STRATEGY)


def refresh_prompt_config_from_corpus() -> None:
    generate_prompt_config()


def _researched_longtails(topic: str, limit: int) -> list[dict[str, object]]:
    if not RESEARCH_PATH.exists():
        return []
    try:
        payload = json.loads(RESEARCH_PATH.read_text(encoding="utf-8"))
        items = payload.get("topics", {}).get(topic, [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return []
    results: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("question") or not item.get("seed_article_url"):
            continue
        results.append(
            {
                "query_intent": "article_longtail",
                "question": str(item["question"]),
                "prompt_kind": "gt_longtail",
                "seed_article_title": str(item.get("seed_article_title", "")),
                "seed_article_url": str(item["seed_article_url"]),
                "seed_published_at": str(item.get("seed_published_at", "")),
                "core_fact": str(item.get("core_fact", "")),
                "intelligence_value": str(item.get("intelligence_value", "")),
                "supporting_article_urls": item.get("supporting_article_urls", []),
                "cluster_size": int(item.get("cluster_size", 1)),
                "generation_method": str(item.get("generation_method", "researched_event_synthesis")),
            }
        )
    return results[:limit]


if __name__ == "__main__":
    generate_prompt_config()
    print(f"Generated {len(TOPIC_STRATEGY) * 10} prompts across {len(TOPIC_STRATEGY)} topics.")
