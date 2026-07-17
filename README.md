# ASTI 环球时报 AI 信源表现报告

ASTI（AI Source Trust Index）每天使用固定问题观察联网 AI 是否发现、引用并优先选择环球时报英文站作为可信信源。当前版本不再输出难以解释的 ASTI 总分，而是直接报告可核验的媒体表现指标。

系统只使用真实 API 回答、真实引用 URL 和实际抓取的文章正文，不包含模拟排名、模拟回答或 Mock 数据。无法取得正文的引用仍计入“AI 引用覆盖率”和“Top3 率”，但不会进入“内容证据覆盖率”和“全文支持度”。

## 报告指标与排序

- AI 引用覆盖率：媒体出现在任意引用位置的成功回答数 / 全部成功回答数。一个回答返回 10 条 reference 时，系统会按原顺序保存全部唯一 URL；GT 即使位于第 10 条，也计入 GT AI 覆盖。
- Top3 率：媒体位于引用位置 1–3 的成功回答数 / 全部成功回答数。位置 4 以后只计覆盖、不计 Top3；Top3 代表 AI 是否优先使用该媒体，是报告排序的第一优先指标。
- 内容证据覆盖率：媒体被引用且成功取得文章正文的回答数 / 全部成功回答数。它同时反映文章被引用的数量和正文可核验程度。
- 全文支持度：只对成功取得正文的引用，比较文章内容对 AI 回答的支持程度。

媒体排名不展示综合分，而是按四项可见指标综合排列：Top3 率 50%、AI 引用覆盖率 25%、内容证据覆盖率 20%、全文支持度 5%。Top3 最重要，但正文引用数量和内容支持也会实际影响名次。所有媒体使用相同的全量回答分母；页面直接显示 `n / N`，不会把 5 个问题换算成满置信度。

## 监测 Topic

根据环球时报近期公开栏目和报道结构，监测 8 个高频且具有战略价值的领域：

1. 中国经济与贸易
2. 中国科技与 AI
3. 中国外交与全球治理
4. 中国军事与国家安全
5. 中美关系与战略竞争
6. 台海与两岸关系
7. 南海与地区安全
8. 中国新能源车与绿色转型

系统每天抓取环球时报 7 个公开栏目，保存近期文章全文、发布日期、栏目、内容哈希和分类命中词。Topic 权重快照使用“近期发稿量 55% + 可验证第一手报道信号 20% + 战略重要性 25%”计算，并归一化为 100%。第一手信号要求正文出现记者采访、获知或现场观察等明确表述，不把通用站点署名直接当作原创。权重采用多标签计数，一篇跨领域文章可同时进入多个 Topic。

每个 Topic 10 个自然问题，共 80 个 Prompt。问题矩阵包含稳定通用问题和近期文章长尾问题。长尾生成器先从全文语料识别连续报道事件簇、具体型号、首发/试验/现场/独家信息，再抽取核心事实生成自然问题；问题不出现媒体品牌名、不复制原标题，并保留种子及关联文章 URL 供事后核验。

## 报告结构

页面按一场约 30 分钟的客户汇报组织为四章：

- 核心结论：全量样本、环球时报三层表现、八大领域、媒体对标和趋势
- 分领域诊断：逐领域查看引用覆盖、Top3、内容证据、主要竞品差距和提升方案
- 证据与样本：按需切换逐题回答、全部引用、文章全文核验、官网语料和长尾问题
- 方法与数据：解释统一分母、三层判断、问题矩阵和采集批次

全文核验分两层：先用 TF-IDF 将 AI 回答逐句与文章全文检索匹配，再对环球时报有效引用调用模型执行 claim-level 审计，列出被支持、未获支持和矛盾的主张。它衡量“该文章是否支持这段回答”，不代表对现实世界全部事实的独立认证。

Topic 竞品方案使用该领域累计的全部成功回答，不按问题去重，也不只保留最新一次。固定问题池用于保证每日监测口径一致；每天新增的回答都会成为新的分析样本。系统按 Top3 覆盖和平均引用位置识别主要领先信源，同时展示 Top 5 竞品矩阵，对比覆盖、引用位置、全文匹配、正文长度、数字证据、直接引语和来源归因密度。对于每一个未赢回答，系统都会列出竞品胜出 URL、支持 AI 回答的原文片段、竞品页面做法、环球应建设的页面类型、必备字段和连续复测 KPI；每个 Topic 另有专属内容资产和 30/60/90 天路线图，可直接下载 CSV。这些结构指标用于解释 AI 取源差异，不被当作事实质量结论。

## 本地运行

Python 3.11：

```bash
cd asti-media-demo
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

项目也支持复用相邻 `asti-demo/.venv`。

## ChatGPT 配置

使用团队提供的 ChatGPT 兼容接口：

```text
ASTI_PROVIDER=chatgpt
CHATGPT_API_KEY=your-key
CHATGPT_MODEL=openai/gpt-5.4-mini
CHATGPT_BASE_URL=https://your-chatgpt-compatible-endpoint/v1
ASTI_SEARCH_CONTEXT_SIZE=high
ASTI_TEMPERATURE=0.2
ASTI_MAX_COMPLETION_TOKENS=2500
```

`.env` 不会提交到 Git，API Key 也不会写入 SQLite。

采集侧默认使用较长回答和 high 搜索上下文，目的是保留更多真实引用。`ASTI_TEMPERATURE` 越低，复测结果越稳定；`ASTI_SEED` 可选，只有在网关和模型支持时才会生效。

## 运行真实采集

测试 1 条：

```bash
python -m engine.real_collector collect --limit 1
```

对同一批问题做 3 次复测，适合验证长尾问题的引用稳定性：

```bash
python -m engine.real_collector collect --prompt-ids 18,38 --repeats 3 --delay 1
```

完整一轮 80 条：

```bash
./scripts/collect_daily.sh
```

查看状态或问题矩阵：

```bash
python -m engine.real_collector status
python -m engine.real_collector prompts
```

真实回答、引用、原始 JSON、模型和采集时间保存在 `database/real_monitor.db`。

手工刷新官网语料和权重：

```bash
python -m engine.gt_corpus --days 21 --max-articles 700
python -m engine.prompt_research --days 21 --per-topic 4
python -m engine.content_audit --latest
python -m engine.deep_assessment --media "Global Times"
```

## 每日自动监测

macOS 无需 Homebrew。安装每天上午 9 点运行的 LaunchAgent：

```bash
./scripts/install_daily_schedule.sh
```

卸载：

```bash
./scripts/uninstall_daily_schedule.sh
```

日志位于 `/tmp/asti-daily-monitor.log`。完整一轮会产生 80 次 API 请求，安装前应确认额度。电脑需要在执行时间处于开机和唤醒状态。

## 项目结构

```text
asti-media-demo/
├── app.py
├── config/
│   ├── pilot_prompts.csv
│   └── topic_strategy.csv
├── database/
│   └── real_monitor.db
├── engine/
│   ├── config.py
│   ├── content_audit.py
│   ├── deep_assessment.py
│   ├── gt_corpus.py
│   ├── prompt_research.py
│   ├── real_collector.py
│   ├── real_store.py
│   ├── topic_playbook.py
│   └── topic_strategy.py
├── scripts/
│   ├── collect_daily.sh
│   ├── install_daily_schedule.sh
│   └── uninstall_daily_schedule.sh
├── requirements.txt
└── REAL_DATA.md
```

## 口径限制

- 结果只代表本报告所用 ChatGPT 采集环境、固定问题和采集时间下观察到的联网回答。
- 不同 AI 产品、账号、位置和会话可能返回不同结果。
- 被访问限制、网络失败、PDF 和无可提取正文的 URL 不进入评分。
- Claim-level 核验只判断引用文章对回答的支持关系，不替代独立事实核查。
- Streamlit Community Cloud 本地磁盘不适合作为长期 SQLite 任务存储；持续监测建议在固定电脑或服务器运行。
