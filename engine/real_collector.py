from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from engine.config import MEDIA
from engine.real_store import (
    DEFAULT_DB_PATH,
    complete_run,
    create_run,
    initialize_database,
    load_pilot_prompts,
    load_real_data,
    real_summary,
    record_answer,
)


ZENMUX_BASE_URL = "https://zenmux.ai/api/v1"
SONAR_ENDPOINT = "https://api.perplexity.ai/v1/sonar"
DEFAULT_PROVIDER = "chatgpt"
DEFAULT_ZENMUX_MODEL = "openai/gpt-5.4-mini"
DEFAULT_PERPLEXITY_MODEL = "sonar"
DEFAULT_SEARCH_CONTEXT_SIZE = "high"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_COMPLETION_TOKENS = 2500
PROVIDER_LABELS = {
    "chatgpt": "ChatGPT",
    "perplexity": "Perplexity",
}
ResponseProvider = Callable[[str, str], tuple[dict[str, Any], int]]


def load_local_env(env_path: Path | str | None = None) -> None:
    path = Path(env_path) if env_path else Path(__file__).resolve().parents[1] / ".env"
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_local_env()


def collect_prompts(
    api_key: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    limit: int | None = None,
    prompt_ids: list[int] | None = None,
    delay_seconds: float = 0.4,
    db_path: Path | str = DEFAULT_DB_PATH,
    response_provider: ResponseProvider | None = None,
) -> dict[str, Any]:
    selected_provider = (provider or os.getenv("ASTI_PROVIDER", DEFAULT_PROVIDER)).strip().lower()
    if selected_provider == "zenmux":
        selected_provider = "chatgpt"
    if selected_provider not in PROVIDER_LABELS:
        raise ValueError(f"Unsupported provider: {selected_provider}. Choose chatgpt or perplexity.")
    key_env, model_env, default_model = provider_environment(selected_provider)
    resolved_key = api_key or os.getenv(key_env, "").strip()
    selected_model = model or os.getenv(model_env, default_model).strip() or default_model
    platform = PROVIDER_LABELS[selected_provider]
    if response_provider is None and not resolved_key:
        raise ValueError(f"Missing {key_env}. Set it in the environment before collecting real data.")

    prompts = load_pilot_prompts()
    if prompt_ids:
        prompts = prompts[prompts["prompt_id"].isin(prompt_ids)]
    if limit is not None:
        prompts = prompts.head(max(0, int(limit)))
    if prompts.empty:
        raise ValueError("No pilot prompts matched the requested selection.")

    run_id = str(uuid.uuid4())
    started_at = _now_iso()
    create_run(run_id, started_at, platform, selected_model, len(prompts), db_path=db_path)
    success_count = 0
    error_count = 0

    try:
        for index, prompt in enumerate(prompts.to_dict("records")):
            captured_at = _now_iso()
            try:
                if response_provider is not None:
                    response, latency_ms = response_provider(str(prompt["question"]), selected_model)
                else:
                    response, latency_ms = call_provider(
                        question=str(prompt["question"]),
                        api_key=resolved_key,
                        provider=selected_provider,
                        model=selected_model,
                    )
                answer_text = _extract_answer_text(response)
                citations = extract_citations(response)
                record_answer(
                    run_id=run_id,
                    prompt=prompt,
                    platform=platform,
                    model=selected_model,
                    captured_at=captured_at,
                    latency_ms=latency_ms,
                    status="success",
                    answer_text=answer_text,
                    raw_response=response,
                    citations=citations,
                    db_path=db_path,
                )
                success_count += 1
            except Exception as exc:
                record_answer(
                    run_id=run_id,
                    prompt=prompt,
                    platform=platform,
                    model=selected_model,
                    captured_at=captured_at,
                    latency_ms=0,
                    status="error",
                    error_message=str(exc),
                    db_path=db_path,
                )
                error_count += 1
            if delay_seconds > 0 and index < len(prompts) - 1:
                time.sleep(delay_seconds)
    finally:
        complete_run(
            run_id=run_id,
            completed_at=_now_iso(),
            success_count=success_count,
            error_count=error_count,
            db_path=db_path,
        )

    return {
        "run_id": run_id,
        "provider": selected_provider,
        "platform": platform,
        "model": selected_model,
        "total_prompts": int(len(prompts)),
        "success_count": success_count,
        "error_count": error_count,
    }


def call_provider(
    question: str,
    api_key: str,
    provider: str = DEFAULT_PROVIDER,
    model: str | None = None,
) -> tuple[dict[str, Any], int]:
    if provider in {"chatgpt", "zenmux"}:
        return call_zenmux(question, api_key, model or DEFAULT_ZENMUX_MODEL)
    if provider == "perplexity":
        return call_sonar(question, api_key, model or DEFAULT_PERPLEXITY_MODEL)
    raise ValueError(f"Unsupported provider: {provider}")


def call_zenmux(
    question: str,
    api_key: str,
    model: str = DEFAULT_ZENMUX_MODEL,
) -> tuple[dict[str, Any], int]:
    base_url = os.getenv("CHATGPT_BASE_URL", os.getenv("ZENMUX_BASE_URL", ZENMUX_BASE_URL)).strip().rstrip("/") or ZENMUX_BASE_URL
    payload = {
        "model": model,
        "messages": _grounded_messages(question),
        "web_search_options": {
            "search_context_size": os.getenv("ASTI_SEARCH_CONTEXT_SIZE", DEFAULT_SEARCH_CONTEXT_SIZE).strip()
            or DEFAULT_SEARCH_CONTEXT_SIZE,
            "user_location": {
                "type": "approximate",
                "country": "CN",
                "timezone": "Asia/Shanghai",
            },
        },
        "temperature": _float_env("ZENMUX_TEMPERATURE", _float_env("ASTI_TEMPERATURE", DEFAULT_TEMPERATURE)),
        "max_completion_tokens": _int_env(
            "ZENMUX_MAX_COMPLETION_TOKENS",
            _int_env("ASTI_MAX_COMPLETION_TOKENS", DEFAULT_MAX_COMPLETION_TOKENS),
        ),
        "stream": False,
    }
    seed = os.getenv("ZENMUX_SEED", os.getenv("ASTI_SEED", "")).strip()
    if seed:
        payload["seed"] = int(seed)
    return _post_json(
        endpoint=f"{base_url}/chat/completions",
        payload=payload,
        api_key=api_key,
        provider_name="ChatGPT",
    )


def call_sonar(
    question: str,
    api_key: str,
    model: str = DEFAULT_PERPLEXITY_MODEL,
) -> tuple[dict[str, Any], int]:
    payload = {
        "model": model,
        "messages": _grounded_messages(question),
        "web_search_options": {"search_mode": "web"},
        "temperature": _float_env("PERPLEXITY_TEMPERATURE", _float_env("ASTI_TEMPERATURE", DEFAULT_TEMPERATURE)),
        "max_tokens": _int_env(
            "PERPLEXITY_MAX_TOKENS",
            _int_env("ASTI_MAX_COMPLETION_TOKENS", DEFAULT_MAX_COMPLETION_TOKENS),
        ),
    }
    return _post_json(
        endpoint=SONAR_ENDPOINT,
        payload=payload,
        api_key=api_key,
        provider_name="Perplexity",
    )


def _grounded_messages(question: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Answer using current web search evidence for a media-source monitoring report. "
                "Do not favor any outlet by brand; select sources because they directly support the facts. "
                "For specific recent events, products, equipment, meetings, or data releases, look for the "
                "original or earliest reporting plus follow-on coverage from specialist, official, and news sources. "
                "Use enough distinct citations to make the answer auditable; when the web has sufficient evidence, "
                "preserve 6 to 10 cited URLs instead of only the first few results. "
                "Write a factual answer with the key numbers, dates, actors, and uncertainties. "
                "If reliable sources do not support a claim, state the uncertainty instead of guessing."
            ),
        },
        {"role": "user", "content": question},
    ]


def _float_env(key: str, default: float) -> float:
    value = os.getenv(key, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _int_env(key: str, default: int) -> int:
    value = os.getenv(key, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _post_json(
    endpoint: str,
    payload: dict[str, Any],
    api_key: str,
    provider_name: str,
) -> tuple[dict[str, Any], int]:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "asti-real-monitor/0.1",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{provider_name} API returned HTTP {exc.code}: {details[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {provider_name} API: {exc.reason}") from exc
    latency_ms = int((time.perf_counter() - started) * 1000)
    return json.loads(body), latency_ms


def extract_citations(response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_citations = response.get("citations") or []
    search_results = response.get("search_results") or []
    result_by_url = {
        canonicalize_url(str(item.get("url", ""))): item
        for item in search_results
        if item.get("url")
    }
    citation_items: list[dict[str, str]] = []
    try:
        annotations = response["choices"][0]["message"].get("annotations") or []
    except (KeyError, IndexError, TypeError, AttributeError):
        annotations = []
    for annotation in annotations:
        if not isinstance(annotation, dict) or annotation.get("type") != "url_citation":
            continue
        citation = annotation.get("url_citation") or annotation
        if isinstance(citation, dict):
            citation_items.append(
                {
                    "url": str(citation.get("url", "")),
                    "title": str(citation.get("title", "")),
                    "snippet": str(citation.get("snippet", "")),
                }
            )
    for citation in raw_citations:
        if isinstance(citation, dict):
            citation_items.append(
                {
                    "url": str(citation.get("url", "")),
                    "title": str(citation.get("title", "")),
                    "snippet": str(citation.get("snippet", "")),
                }
            )
        else:
            citation_items.append({"url": str(citation), "title": "", "snippet": ""})

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for citation in citation_items:
        source_url = citation["url"]
        canonical = canonicalize_url(source_url)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        metadata = result_by_url.get(canonical, {})
        domain = normalized_domain(canonical)
        media_name, cluster = identify_media(domain)
        rows.append(
            {
                "media_name": media_name,
                "domain": domain,
                "cluster": cluster,
                "source_url": canonical,
                "source_title": citation["title"] or str(metadata.get("title", "")),
                "source_snippet": citation["snippet"] or str(metadata.get("snippet", "")),
                "source_position": len(rows) + 1,
            }
        )
    return rows


def canonicalize_url(url: str) -> str:
    text = url.strip()
    if not text:
        return ""
    parsed = urllib.parse.urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    filtered_query = urllib.parse.urlencode(
        [
            (key, value)
            for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
            and key.lower() not in {"gclid", "fbclid", "ref", "source"}
        ]
    )
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", filtered_query, "")
    )


def normalized_domain(url: str) -> str:
    hostname = (urllib.parse.urlsplit(url).hostname or "").lower()
    return hostname[4:] if hostname.startswith("www.") else hostname


def identify_media(domain: str) -> tuple[str, str]:
    clean_domain = domain.lower().strip(".")
    domain_aliases = {
        "fmprc.gov.cn": ("MFA China", "Government Source"),
    }
    for known_domain, metadata in domain_aliases.items():
        if clean_domain == known_domain or clean_domain.endswith(f".{known_domain}"):
            return metadata
    for item in sorted(MEDIA, key=lambda value: len(str(value["domain"])), reverse=True):
        known_domain = str(item["domain"]).lower().strip(".")
        if clean_domain == known_domain or clean_domain.endswith(f".{known_domain}"):
            return str(item["media_name"]), str(item["cluster"])
    label = clean_domain or "Unknown Source"
    return label, "Other Web Source"


def _extract_answer_text(response: dict[str, Any]) -> str:
    try:
        return str(response["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("API response did not contain choices[0].message.content") from exc


def provider_environment(provider: str) -> tuple[str, str, str]:
    if provider in {"chatgpt", "zenmux"}:
        key_name = "CHATGPT_API_KEY" if os.getenv("CHATGPT_API_KEY", "").strip() else "ZENMUX_API_KEY"
        model_name = "CHATGPT_MODEL" if os.getenv("CHATGPT_MODEL", "").strip() else "ZENMUX_MODEL"
        return key_name, model_name, DEFAULT_ZENMUX_MODEL
    return "PERPLEXITY_API_KEY", "PERPLEXITY_MODEL", DEFAULT_PERPLEXITY_MODEL


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_prompt_ids(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ASTI daily collector for ChatGPT and Perplexity")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect", help="Run one collection round")
    collect_parser.add_argument("--limit", type=int, default=None, help="Collect only the first N prompts")
    collect_parser.add_argument("--prompt-ids", type=_parse_prompt_ids, default=None, help="Comma-separated prompt IDs")
    collect_parser.add_argument(
        "--provider",
        choices=sorted(PROVIDER_LABELS),
        default=None,
        help="API provider; defaults to ASTI_PROVIDER or perplexity",
    )
    collect_parser.add_argument("--model", default=None, help="Model ID; defaults to the selected provider setting")
    collect_parser.add_argument("--delay", type=float, default=0.4, help="Delay between requests in seconds")
    collect_parser.add_argument("--repeats", type=int, default=1, help="Run the selected prompt set multiple times")
    collect_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path")

    status_parser = subparsers.add_parser("status", help="Show current monitoring status")
    status_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path")

    subparsers.add_parser("prompts", help="List the 80 fixed daily-monitoring prompts")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "prompts":
        print(load_pilot_prompts().to_string(index=False))
        return 0
    if args.command == "status":
        initialize_database(args.db)
        print(json.dumps(real_summary(load_real_data(args.db)), ensure_ascii=False, indent=2))
        return 0
    try:
        results = []
        for repeat_index in range(max(1, int(args.repeats))):
            result = collect_prompts(
                provider=args.provider,
                model=args.model,
                limit=args.limit,
                prompt_ids=args.prompt_ids,
                delay_seconds=args.delay,
                db_path=args.db,
            )
            result["repeat_index"] = repeat_index + 1
            results.append(result)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if len(results) == 1:
        print(json.dumps(results[0], ensure_ascii=False, indent=2))
        return 0 if results[0]["error_count"] == 0 else 1
    aggregate = {
        "provider": results[0]["provider"],
        "platform": results[0]["platform"],
        "model": results[0]["model"],
        "runs": [item["run_id"] for item in results],
        "repeat_count": len(results),
        "total_prompts": sum(int(item["total_prompts"]) for item in results),
        "success_count": sum(int(item["success_count"]) for item in results),
        "error_count": sum(int(item["error_count"]) for item in results),
    }
    print(json.dumps(aggregate, ensure_ascii=False, indent=2))
    return 0 if aggregate["error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
