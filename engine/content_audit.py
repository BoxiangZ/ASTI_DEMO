from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import urllib3
from trafilatura import bare_extraction

from engine.real_store import DEFAULT_DB_PATH, initialize_database


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
)
MAX_RESPONSE_BYTES = 6_000_000
MIN_ARTICLE_WORDS = 80


def fetch_and_extract(url: str, timeout: int = 18) -> dict[str, Any]:
    fetched_at = _now_iso()
    base = {
        "http_status": 0,
        "access_status": "network_error",
        "final_url": "",
        "content_type": "",
        "article_title": "",
        "article_text": "",
        "article_word_count": 0,
        "published_at": "",
        "author": "",
        "fetched_at": fetched_at,
        "content_hash": "",
        "tls_fallback": 0,
        "error_message": "",
    }
    response: requests.Response | None = None
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.exceptions.SSLError:
        try:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            response = requests.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
                timeout=timeout,
                allow_redirects=True,
                verify=False,
            )
            base["tls_fallback"] = 1
        except requests.RequestException as exc:
            base["error_message"] = f"{type(exc).__name__}: {exc}"[:500]
            return base
    except requests.RequestException as exc:
        base["error_message"] = f"{type(exc).__name__}: {exc}"[:500]
        return base

    if response is None:
        return base
    base["http_status"] = int(response.status_code)
    base["final_url"] = str(response.url)
    base["content_type"] = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
    if response.status_code in {401, 403, 429}:
        base["access_status"] = "blocked"
        base["error_message"] = f"HTTP {response.status_code}"
        return base
    if not 200 <= response.status_code < 300:
        base["access_status"] = "http_error"
        base["error_message"] = f"HTTP {response.status_code}"
        return base
    if "pdf" in base["content_type"] or response.url.lower().endswith(".pdf"):
        base["access_status"] = "unsupported_pdf"
        return base
    if len(response.content) > MAX_RESPONSE_BYTES:
        base["access_status"] = "too_large"
        base["error_message"] = f"Response exceeded {MAX_RESPONSE_BYTES} bytes"
        return base

    html = response.content.decode("utf-8", errors="replace")
    try:
        document = bare_extraction(
            html,
            url=str(response.url),
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        metadata = document.as_dict() if document else {}
    except Exception as exc:
        base["access_status"] = "extract_error"
        base["error_message"] = f"{type(exc).__name__}: {exc}"[:500]
        return base
    text = str(metadata.get("text") or "").strip()
    html_title = _html_metadata(html, "og:title") or _html_metadata(html, "twitter:title")
    published_at = (
        _html_metadata(html, "article:published_time")
        or _html_metadata(html, "datePublished")
        or _json_value(html, "datePublished")
        or _published_label(html)
        or str(metadata.get("date") or "").strip()
    )
    author = (
        _html_metadata(html, "author")
        or _json_value(html, "author")
        or str(metadata.get("author") or "").strip()
    )
    word_count = len(text.split())
    base.update(
        {
            "article_title": str(html_title or metadata.get("title") or "").strip(),
            "article_text": text,
            "article_word_count": word_count,
            "published_at": published_at,
            "author": author,
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else "",
        }
    )
    if word_count < MIN_ARTICLE_WORDS:
        base["access_status"] = "no_article_text"
        base["error_message"] = f"Only {word_count} extracted words"
    else:
        base["access_status"] = "verified_tls_fallback" if base["tls_fallback"] else "verified"
    return base


def _html_metadata(document: str, key: str) -> str:
    patterns = [
        rf'<meta[^>]+(?:property|name|itemprop)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name|itemprop)=["\']{re.escape(key)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, document, flags=re.IGNORECASE)
        if match:
            return html_lib.unescape(match.group(1)).strip()
    return ""


def _json_value(document: str, key: str) -> str:
    match = re.search(rf'["\']{re.escape(key)}["\']\s*:\s*["\']([^"\']+)', document, re.IGNORECASE)
    return html_lib.unescape(match.group(1)).strip() if match else ""


def _published_label(document: str) -> str:
    match = re.search(
        r'class=["\']pub_time["\'][^>]*>\s*Published:\s*([^<]+)',
        document,
        re.IGNORECASE,
    )
    if not match:
        return ""
    raw = html_lib.unescape(match.group(1)).split("Updated:", 1)[0].strip()
    try:
        return datetime.strptime(raw, "%b %d, %Y %I:%M %p").isoformat()
    except ValueError:
        return raw


def audit_citations(
    db_path: Path | str = DEFAULT_DB_PATH,
    run_id: str | None = None,
    force: bool = False,
    max_workers: int = 10,
    limit: int | None = None,
) -> dict[str, int]:
    initialize_database(db_path)
    with sqlite3.connect(Path(db_path)) as conn:
        query = """
            SELECT c.citation_id, c.source_url
            FROM citations c
            LEFT JOIN citation_audits a ON a.citation_id = c.citation_id
            WHERE (? IS NULL OR c.run_id = ?)
              AND (? = 1 OR a.citation_id IS NULL)
            ORDER BY c.citation_id
        """
        rows = conn.execute(query, (run_id, run_id, int(force))).fetchall()
    if limit is not None:
        rows = rows[: max(0, int(limit))]

    url_to_ids: dict[str, list[int]] = {}
    for citation_id, url in rows:
        url_to_ids.setdefault(str(url), []).append(int(citation_id))
    results: list[tuple[int, dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        futures = {pool.submit(fetch_and_extract, url): url for url in url_to_ids}
        for future in as_completed(futures):
            url = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "http_status": 0,
                    "access_status": "audit_error",
                    "final_url": "",
                    "content_type": "",
                    "article_title": "",
                    "article_text": "",
                    "article_word_count": 0,
                    "published_at": "",
                    "author": "",
                    "fetched_at": _now_iso(),
                    "content_hash": "",
                    "tls_fallback": 0,
                    "error_message": f"{type(exc).__name__}: {exc}"[:500],
                }
            for citation_id in url_to_ids[url]:
                results.append((citation_id, result))

    fields = [
        "http_status",
        "access_status",
        "final_url",
        "content_type",
        "article_title",
        "article_text",
        "article_word_count",
        "published_at",
        "author",
        "fetched_at",
        "content_hash",
        "tls_fallback",
        "error_message",
    ]
    with sqlite3.connect(Path(db_path)) as conn:
        for citation_id, result in results:
            values = [result.get(field, "") for field in fields]
            conn.execute(
                f"""
                INSERT INTO citation_audits (citation_id, {', '.join(fields)})
                VALUES (?, {', '.join('?' for _ in fields)})
                ON CONFLICT(citation_id) DO UPDATE SET
                    {', '.join(f'{field}=excluded.{field}' for field in fields)}
                """,
                [citation_id, *values],
            )
        conn.commit()
    status_counts: dict[str, int] = {}
    for _, result in results:
        status = str(result.get("access_status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
    return {"total": len(results), **status_counts}


def latest_completed_run(db_path: Path | str = DEFAULT_DB_PATH) -> str | None:
    initialize_database(db_path)
    with sqlite3.connect(Path(db_path)) as conn:
        row = conn.execute(
            """
            SELECT run_id FROM runs
            WHERE status IN ('completed', 'completed_with_errors')
            ORDER BY completed_at DESC LIMIT 1
            """
        ).fetchone()
    return str(row[0]) if row else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify citation URLs and extract full article text")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--latest", action="store_true", help="Audit the latest completed run")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    run_id = latest_completed_run(args.db) if args.latest else args.run_id
    result = audit_citations(
        db_path=args.db,
        run_id=run_id,
        force=args.force,
        max_workers=args.workers,
        limit=args.limit,
    )
    print(result)
    return 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
