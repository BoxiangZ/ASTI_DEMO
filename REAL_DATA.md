# ASTI 每日真实监测说明

## 监测口径

- 目标媒体：环球时报英文站（Global Times）
- 8 个 Topic
- 每个 Topic 10 个自然查询
- 每轮 80 次联网 AI 请求
- 建议每天固定时间运行
- 数据库：`database/real_monitor.db`

Prompt 位于 `config/pilot_prompts.csv`。通用问题保持稳定，文章长尾问题由近期环球时报全文语料自动生成。

## 每日流程

```text
抓取环球时报近期官网文章全文并重算 Topic 权重
  -> 生成通用 + 文章长尾的 80 个问题
  -> ZenMux ChatGPT 或 Perplexity 联网回答
  -> 提取真实 citation URL 和引用位置
  -> 逐条验证 URL 并提取文章全文
  -> 回答逐句检索匹配 + 环球时报引用的 claim-level 深度核验
  -> 保存回答、原始 JSON、全文和审计结果到 SQLite
  -> 只用全文有效引用计算 ASTI、Topic 权威和 Prompt 输赢
  -> Streamlit 页面展示
```

## 手工运行

```bash
./scripts/collect_daily.sh
```

测试单条：

```bash
python -m engine.real_collector collect --limit 1
```

只采集指定问题：

```bash
python -m engine.real_collector collect --prompt-ids 1,2,3
```

## macOS 每日任务

```bash
./scripts/install_daily_schedule.sh
```

默认每天 09:00 运行。任务文件位于：

```text
~/Library/LaunchAgents/com.asti.daily-monitor.plist
```

日志：

```text
/tmp/asti-daily-monitor.log
```

卸载：

```bash
./scripts/uninstall_daily_schedule.sh
```

## 数据解释

- AI 覆盖率：环球时报出现在多少条真实回答中。
- 自然 Top3 率：环球时报被引用后，有多少次进入前三引用位置。
- 引用质量：按引用位置计分，第一位 100，第二位 80，第三位 60，其余 30。
- Topic 权威：该 Topic 的覆盖、Top3 偏好和引用质量综合分。
- 全文支持度：AI 回答逐句与引用文章全文的检索匹配。
- 主张级深度核验：列出文章支持、未支持和矛盾的回答主张。
- Prompt 结果：GT 胜出、GT Top3、GT 弱引用、竞品胜出或未形成有效竞争。

系统不会在没有环球时报引用时制造得分。Topic 没有足够样本时会显示“待采集”或“证据不足”。

## 安全与成本

- `.env` 已加入 `.gitignore`。
- API Key 不进入数据库。
- 每轮完整监测产生 80 次请求。
- 安装每日任务前先确认 API 额度。
- 不建议依赖 Streamlit Community Cloud 的临时磁盘保存长期 SQLite 数据。
