# ASTI Media Intelligence Demo

中文名：AI信源权威分析系统 Demo

ASTI means AI Source Trust Intelligence / AI Source Trust Index. This local demo shows how a GenTrack-style AI visibility monitor can evolve into a media-specific source intelligence system.

## What ASTI Measures

Traditional PV/UV analytics measure direct visits. In AI search, users often receive an AI-generated answer without clicking the original article. For news media, influence increasingly depends on whether AI systems discover, cite, trust, and prioritize a publisher as a source.

ASTI answers questions such as:

- Does AI find this media source?
- Does AI choose it for neutral and strategic questions?
- Does it beat Reuters, Xinhua, China Daily, SCMP, and other competitors in answer position?
- Which topics show authority, and which topics show absence loss?
- In high-value cases, does the AI answer borrow facts, data, and narrative framing from this media source?

## Relationship With GenTrack

GenTrack monitors AI/GEO visibility for brands:

- Whether AI mentions a brand.
- Which prompts trigger brand visibility.
- Brand share of voice against competitors.
- Position, frequency, and trend in AI answers.

ASTI extends that workflow for news media. It does not stop at "AI mentioned Global Times." It separates brand-search visibility from organic source preference, identifies meaningful source competition, and adds topic authority plus deep attribution.

## Demo Workflow

The dashboard presents five layers:

1. Prompt Matrix
2. AI Visibility Layer
3. Source Competition Layer
4. Deep Attribution Layer
5. ASTI Scores and Recommendations

## Run Locally

Use Python 3.11+.

```bash
cd asti-media-demo
pip install -r requirements.txt
streamlit run app.py
```

## Share Online

The demo is ready for Streamlit Community Cloud deployment. See [DEPLOYMENT.md](DEPLOYMENT.md).

Quick path:

1. Push this folder to GitHub.
2. Open https://share.streamlit.io/.
3. Select the repo.
4. Set main file path to `app.py` if this folder is repo root, or `asti-media-demo/app.py` if it is a subdirectory.
5. Deploy and share the generated URL.

On first run, the app automatically creates simulated CSV data in `data/`:

- `prompts.csv`
- `media.csv`
- `simulated_answers.csv`
- `source_records.csv`
- `competition_cases.csv`
- `deep_attribution_cases.csv`
- `asti_scores.csv`
- `topic_authority.csv`
- `recommendations.csv`

## Dashboard Pages

- Executive Overview: Mock Demo Data mode banner, Real Data Mode placeholders, Overall ASTI formula, score contribution breakdown, Strategic ASTI explanation, media ranking, and core benchmarks.
- AI Visibility: total prompts, citations, source counts, Global Times coverage, brand-search inflation, platform and language breakdowns.
- Source Competition: effective competition funnel, win rates, head-to-head, position gap, absence loss, and topic x competitor heatmap.
- Topic Authority: four-level authority status, coverage, source preference, citation quality, attribution score, strategic weights, and topic contribution.
- Deep Attribution Cases: 30-50 high-value cases with selection reason, prompt, answer summary, source summaries, radar chart, loss reason, and recommendation.
- Recommendations: executable topic-level tasks with issue, priority, action, and expected metric lift.

## Important Demo Logic

The simulated data intentionally shows these patterns:

- Brand search inflates Global Times visibility.
- Global Times English site is stronger than Huanqiu in multilingual AI answers.
- Global Times performs better in China Military, China Diplomacy, South China Sea, and Taiwan Strait.
- Global Times is weaker in China Technology/AI, Science & Society, and specialist domains.
- Reuters is strong across international, economic, timely, and technology queries.
- Xinhua, China Daily, and CGTN are direct competitors on China-related topics.
- Absence Loss highlights topics where competitors enter Top3 while Global Times is missing.
- Deep Attribution explains why losses happen, such as weaker data density, freshness, structure, or international-reader framing.

## Demo Limitations

This is a local MVP demo. All data is simulated. It does not call real AI APIs and does not parse real articles.

## Next Steps for a Real Product

A production ASTI system would connect:

- OpenAI / Gemini / Claude / Perplexity APIs
- Web citation fetching
- Real article parsing
- Embedding similarity
- LLM-based source attribution
- Longitudinal monitoring
- Client-specific strategic topic weights
- Report export to PDF / HTML
