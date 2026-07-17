# ASTI 部署说明

## 本地运行

```bash
cd asti-media-demo
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.address 0.0.0.0 --server.port 8510
```

浏览器打开 `http://localhost:8510`。

## Streamlit Community Cloud

1. 将项目推送到私有 GitHub 仓库。
2. 打开 `https://share.streamlit.io/`。
3. 选择仓库和 `app.py`。
4. 在 Secrets 中配置 API：

```toml
ASTI_PROVIDER = "chatgpt"
CHATGPT_API_KEY = "your-key"
CHATGPT_MODEL = "openai/gpt-5.4-mini"
CHATGPT_BASE_URL = "https://your-chatgpt-compatible-endpoint/v1"
ASTI_SEARCH_CONTEXT_SIZE = "high"
ASTI_TEMPERATURE = "0.2"
ASTI_MAX_COMPLETION_TOKENS = "2500"
```

页面可以在 Cloud 上查看和测试单条采集，但 Streamlit Community Cloud 的本地磁盘不是可靠的长期存储，不能依赖它每天后台运行 80 条监测。

## 推荐的持续监测方式

真实持续监测建议在固定 Mac 或服务器运行：

```bash
./scripts/install_daily_schedule.sh
```

每天采集结果保存在 `database/real_monitor.db`，页面读取同一个数据库展示趋势。

如果需要给外部品牌方查看，可在固定机器启动 Streamlit 后使用 Cloudflare Tunnel、内网穿透或部署到持久化服务器。分享前应确认数据库中的 Prompt、回答和引用证据可以对外公开。

## 上线检查

- 页面顶部显示“真实数据运行中”或“等待首次采集”
- 监测矩阵显示 8 个 Topic、80 个问题
- 页面中没有 Mock、模拟数据或第三方网关品牌入口
- API Key 只存在于 `.env` 或 Streamlit Secrets
- `database/real_monitor.db` 已备份
- 每日任务日志 `/tmp/asti-daily-monitor.log` 无连续错误
