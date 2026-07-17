from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from engine.config import TOPICS
from engine.real_store import DEFAULT_DB_PATH, initialize_database


LISTING_PAGES = {
    "Source": "https://www.globaltimes.cn/source/",
    "Economy": "https://www.globaltimes.cn/source/economy/",
    "China": "https://www.globaltimes.cn/china/",
    "Diplomacy": "https://www.globaltimes.cn/china/diplomacy/",
    "Military": "https://www.globaltimes.cn/china/military/",
    "World": "https://www.globaltimes.cn/world/",
    "Opinion": "https://www.globaltimes.cn/opinion/",
}
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
)

TOPIC_TERMS = {
    "China Economy": {
        "gdp": 4, "economy": 3, "economic": 3, "trade": 2, "export": 2,
        "import": 2, "consumption": 2, "investment": 2, "tariff": 2,
        "manufacturing": 2, "industrial": 2, "market": 1, "rare-earth": 3,
    },
    "China Technology/AI": {
        "artificial intelligence": 5, " ai ": 4, "robot": 3, "chip": 3,
        "semiconductor": 4, "technology": 2, "computing": 3, "digital": 2,
        "smartphone": 2, "innovation": 2, "sugon": 4,
    },
    "China Diplomacy": {
        "diplomacy": 4, "diplomatic": 4, "foreign minister": 4,
        "foreign ministry": 3, "global governance": 4, "bilateral": 2,
        "multilateral": 3, "summit": 2, "relations": 1,
    },
    "China Military": {
        "pla": 5, "military": 4, "defense": 3, "warship": 4, "missile": 4,
        "air force": 4, "navy": 4, "drill": 3, "exercise": 2, "weapon": 3,
    },
    "US-China Relations": {
        "china-us": 5, "china-u.s.": 5, "us-china": 5, "u.s.-china": 5,
        "united states": 2, "washington": 1, "beijing": 1,
        "american": 1, "white house": 2,
    },
    "Taiwan Strait": {
        "taiwan strait": 5, "taiwan island": 5, "taiwan": 4,
        "cross-strait": 5, "dpp": 3, "lai ching-te": 4, "reunification": 3,
    },
    "South China Sea": {
        "south china sea": 6, "huangyan dao": 5, "ren'ai jiao": 5,
        "philippines": 2, "coast guard": 3, "maritime": 2, "manila": 2,
    },
    "China EV": {
        "electric vehicle": 5, " ev ": 4, "new-energy vehicle": 5,
        "new energy vehicle": 5, "battery": 3, "byd": 4, "automaker": 3,
        "green transition": 2, "clean energy": 2, "charging": 2,
    },
}

SECTION_DEFAULT_TOPIC = {
    "Economy": "China Economy",
    "Diplomacy": "China Diplomacy",
    "Military": "China Military",
}
SECTION_PRIORITY = {"Source": 0, "China": 1, "World": 1, "Opinion": 1, "Economy": 2, "Diplomacy": 3, "Military": 3}

STRATEGIC_IMPORTANCE = {
    "China Economy": 5,
    "China Technology/AI": 5,
    "China Diplomacy": 5,
    "China Military": 5,
    "US-China Relations": 5,
    "Taiwan Strait": 5,
    "South China Sea": 4,
    "China EV": 4,
}


def collect_gt_corpus(
    db_path: Path | str = DEFAULT_DB_PATH,
    recent_days: int = 21,
    max_articles: int = 700,
    workers: int = 8,
    force: bool = False,
) -> dict[str, Any]:
    from engine.content_audit import fetch_and_extract

    initialize_database(db_path)
    links = discover_article_links()
    existing = set() if force else _existing_verified_urls(db_path)
    selected = [(url, metadata) for url, metadata in links.items() if url not in existing][:max_articles]
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        future_map = {
            pool.submit(fetch_and_extract, url): (url, metadata)
            for url, metadata in selected
        }
        for future in as_completed(future_map):
            url, metadata = future_map[future]
            audit = future.result()
            title = max(
                (str(audit["article_title"]), str(metadata["listing_title"])),
                key=lambda value: len(value.strip()),
            ).strip()
            topic, score, terms = classify_article(
                title,
                audit["article_text"],
                metadata["section"],
            )
            rows.append(
                {
                    "source_section": metadata["section"],
                    "source_listing_url": metadata["listing_url"],
                    "article_url": url,
                    "title": title,
                    "published_at": audit["published_at"] or _date_from_url(url),
                    "author": audit["author"],
                    "article_text": audit["article_text"],
                    "article_word_count": audit["article_word_count"],
                    "content_hash": audit["content_hash"],
                    "fetched_at": audit["fetched_at"],
                    "primary_topic": topic,
                    "classification_score": score,
                    "classification_terms": ", ".join(terms),
                    "is_original": int(_is_original(audit["author"], audit["article_text"])),
                    "access_status": audit["access_status"],
                    "http_status": audit["http_status"],
                    "error_message": audit["error_message"],
                }
            )
    _save_articles(rows, db_path)
    _update_article_sections(links, db_path)
    weights = calculate_topic_weights(db_path, recent_days=recent_days)
    if Path(db_path).resolve() == DEFAULT_DB_PATH.resolve():
        from engine.topic_strategy import refresh_prompt_config_from_corpus

        refresh_prompt_config_from_corpus()
    return {
        "listing_pages": len(LISTING_PAGES),
        "discovered_urls": len(links),
        "fetched_urls": len(rows),
        "previously_verified_urls": len(existing),
        "verified_articles": sum(r["access_status"] in {"verified", "verified_tls_fallback"} for r in rows),
        "snapshot_date": datetime.now(timezone.utc).date().isoformat(),
        "topic_weights": weights,
    }


def discover_article_links() -> dict[str, dict[str, str]]:
    from lxml import html as lxml_html

    links: dict[str, dict[str, str]] = {}
    for section, listing_url in LISTING_PAGES.items():
        response = requests.get(
            listing_url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
            timeout=20,
        )
        response.raise_for_status()
        document = lxml_html.fromstring(response.content, base_url=listing_url)
        for anchor in document.xpath("//a[@href]"):
            href = str(anchor.get("href") or "").strip()
            url = urljoin(listing_url, href).split("#", 1)[0]
            parsed = urlparse(url)
            if parsed.netloc not in {"www.globaltimes.cn", "globaltimes.cn"}:
                continue
            if not re.search(r"/page/20\d{4}/\d+\.shtml$", parsed.path):
                continue
            title = " ".join(anchor.text_content().split())
            current = links.get(url)
            if current is None:
                links[url] = {"section": section, "listing_url": listing_url, "listing_title": title}
            else:
                if not current["listing_title"] and title:
                    current["listing_title"] = title
                if SECTION_PRIORITY.get(section, 0) > SECTION_PRIORITY.get(current["section"], 0):
                    current["section"] = section
                    current["listing_url"] = listing_url
    return links


def classify_article(title: str, article_text: str, section: str = "") -> tuple[str, float, list[str]]:
    title_text = f" {title} ".lower()
    body_text = f" {article_text[:4000]} ".lower()
    scores: dict[str, float] = defaultdict(float)
    title_scores: dict[str, float] = defaultdict(float)
    matches: dict[str, list[str]] = defaultdict(list)
    for topic, terms in TOPIC_TERMS.items():
        for term, weight in terms.items():
            if term in title_text:
                title_scores[topic] += weight
                scores[topic] += weight * 4
                matches[topic].append(f"title:{term.strip()}")
            if term in body_text:
                scores[topic] += weight
                matches[topic].append(f"body:{term.strip()}")
    if title_scores and max(title_scores.values()) >= 2:
        topic = max(scores, key=scores.get)
        return topic, round(scores[topic], 1), sorted(set(matches[topic]))
    default_topic = SECTION_DEFAULT_TOPIC.get(section)
    if default_topic:
        score = scores.get(default_topic, 0.0) + 6.0
        return default_topic, round(score, 1), sorted(set(matches[default_topic] + [f"section:{section}"]))
    return "Other", 0.0, []


def classify_article_topics(title: str, article_text: str, section: str = "") -> list[str]:
    title_text = f" {title} ".lower()
    labels: list[str] = []
    for topic, terms in TOPIC_TERMS.items():
        title_score = sum(weight for term, weight in terms.items() if term in title_text)
        if title_score >= 2:
            labels.append(topic)
    default_topic = SECTION_DEFAULT_TOPIC.get(section)
    if default_topic and default_topic not in labels:
        labels.append(default_topic)
    return labels


def calculate_topic_weights(
    db_path: Path | str = DEFAULT_DB_PATH,
    recent_days: int = 21,
) -> list[dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=recent_days)).isoformat()
    with sqlite3.connect(Path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        articles = conn.execute(
            """
            SELECT * FROM gt_articles
            WHERE access_status IN ('verified', 'verified_tls_fallback')
              AND article_word_count >= 80
              AND published_at >= ?
            """,
            (cutoff,),
        ).fetchall()

        counts = {topic: 0 for topic in TOPICS}
        originals = {topic: 0 for topic in TOPICS}
        samples: dict[str, list[str]] = {topic: [] for topic in TOPICS}
        first_hand_updates: list[tuple[int, int]] = []
        for article in articles:
            is_first_hand = int(_is_original(str(article["author"] or ""), str(article["article_text"] or "")))
            first_hand_updates.append((is_first_hand, int(article["article_id"])))
            labels = classify_article_topics(
                str(article["title"] or ""),
                str(article["article_text"] or ""),
                str(article["source_section"] or ""),
            )
            for topic in labels:
                if topic not in counts:
                    continue
                counts[topic] += 1
                originals[topic] += is_first_hand
                if len(samples[topic]) < 5:
                    samples[topic].append(article["article_url"])

        conn.executemany(
            "UPDATE gt_articles SET is_original = ? WHERE article_id = ?",
            first_hand_updates,
        )

        total_count = sum(counts.values())
        total_original = sum(originals.values())
        total_strategy = sum(STRATEGIC_IMPORTANCE.values())
        result: list[dict[str, Any]] = []
        snapshot_date = datetime.now(timezone.utc).date().isoformat()
        for topic in TOPICS:
            volume_share = counts[topic] / total_count if total_count else 0.0
            original_share = originals[topic] / total_original if total_original else 0.0
            strategy_share = STRATEGIC_IMPORTANCE[topic] / total_strategy
            weight = volume_share * 0.55 + original_share * 0.20 + strategy_share * 0.25
            row = {
                "snapshot_date": snapshot_date,
                "topic": topic,
                "article_count": counts[topic],
                "original_count": originals[topic],
                "volume_share": round(volume_share, 6),
                "original_share": round(original_share, 6),
                "strategic_importance": STRATEGIC_IMPORTANCE[topic],
                "calculated_weight": round(weight, 6),
                "sample_urls_json": json.dumps(samples[topic], ensure_ascii=False),
            }
            result.append(row)
        total_weight = sum(float(row["calculated_weight"]) for row in result)
        if total_weight:
            for row in result:
                row["calculated_weight"] = round(float(row["calculated_weight"]) / total_weight, 6)
        for row in result:
            conn.execute(
                """
                INSERT INTO topic_weight_snapshots (
                    snapshot_date, topic, article_count, original_count, volume_share,
                    original_share, strategic_importance, calculated_weight, sample_urls_json
                ) VALUES (:snapshot_date, :topic, :article_count, :original_count, :volume_share,
                          :original_share, :strategic_importance, :calculated_weight, :sample_urls_json)
                ON CONFLICT(snapshot_date, topic) DO UPDATE SET
                    article_count=excluded.article_count,
                    original_count=excluded.original_count,
                    volume_share=excluded.volume_share,
                    original_share=excluded.original_share,
                    strategic_importance=excluded.strategic_importance,
                    calculated_weight=excluded.calculated_weight,
                    sample_urls_json=excluded.sample_urls_json
                """,
                row,
            )
        conn.commit()
    return sorted(result, key=lambda item: item["calculated_weight"], reverse=True)


def _save_articles(rows: list[dict[str, Any]], db_path: Path | str) -> None:
    if not rows:
        return
    fields = list(rows[0])
    updates = ", ".join(f"{field}=excluded.{field}" for field in fields if field != "article_url")
    with sqlite3.connect(Path(db_path)) as conn:
        conn.executemany(
            f"""
            INSERT INTO gt_articles ({', '.join(fields)})
            VALUES ({', '.join(':' + field for field in fields)})
            ON CONFLICT(article_url) DO UPDATE SET {updates}
            """,
            rows,
        )
        conn.commit()


def _existing_verified_urls(db_path: Path | str) -> set[str]:
    with sqlite3.connect(Path(db_path)) as conn:
        rows = conn.execute(
            "SELECT article_url FROM gt_articles WHERE access_status IN ('verified', 'verified_tls_fallback')"
        ).fetchall()
    return {str(row[0]) for row in rows}


def _update_article_sections(links: dict[str, dict[str, str]], db_path: Path | str) -> None:
    with sqlite3.connect(Path(db_path)) as conn:
        conn.executemany(
            "UPDATE gt_articles SET source_section = ?, source_listing_url = ? WHERE article_url = ?",
            [
                (metadata["section"], metadata["listing_url"], url)
                for url, metadata in links.items()
            ],
        )
        conn.commit()


def _date_from_url(url: str) -> str:
    match = re.search(r"/page/(20\d{2})(\d{2})/", url)
    return f"{match.group(1)}-{match.group(2)}-01" if match else ""


def _is_original(author: str, article_text: str) -> bool:
    # The site's author metadata is often just "Global Times", so a bare byline
    # cannot establish first-hand reporting. Require an explicit reporting signal.
    signal = article_text[:2500].lower()
    return bool(
        re.search(
            r"\bglobal times reporters?\b|\btold the global times\b|"
            r"\b(?:the )?global times (?:learned|found|obtained|observed|witnessed)\b",
            signal,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and classify recent Global Times articles.")
    parser.add_argument("--days", type=int, default=21)
    parser.add_argument("--max-articles", type=int, default=700)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(json.dumps(collect_gt_corpus(recent_days=args.days, max_articles=args.max_articles, workers=args.workers, force=args.force), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
