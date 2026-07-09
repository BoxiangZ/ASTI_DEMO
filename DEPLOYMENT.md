# ASTI Media Intelligence Demo Deployment

这份说明用于把本地 Streamlit Demo 变成可分享链接。

## 推荐方式：Streamlit Community Cloud

适合给领导、客户或内部同事看一个稳定链接。

### 1. 准备 GitHub 仓库

把 `asti-media-demo/` 作为一个 GitHub repo 上传，或放到现有 repo 的子目录。

需要保留这些文件：

- `app.py`
- `requirements.txt`
- `runtime.txt`
- `.streamlit/config.toml`
- `engine/`
- `assets/`
- `data/.gitkeep`

不需要提交生成后的 CSV。线上首次打开时会自动生成 Mock Demo Data。

### 2. 部署到 Streamlit Cloud

1. 打开 https://share.streamlit.io/
2. 选择 GitHub repo。
3. 如果 `asti-media-demo` 是 repo 根目录：
   - Main file path: `app.py`
4. 如果它在大 repo 子目录：
   - Main file path: `asti-media-demo/app.py`
5. 点击 Deploy。

部署完成后会得到一个公开 URL，可以直接发给领导。

## 临时分享方式：本地运行 + 隧道

适合当天临时演示，不需要先建云部署。

### 1. 本地启动

```bash
cd asti-media-demo
pip install -r requirements.txt
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

### 2. 用 ngrok 暴露链接

```bash
ngrok http 8501
```

复制 ngrok 生成的 `https://...ngrok-free.app` 链接给领导。

### 3. 或用 cloudflared

```bash
cloudflared tunnel --url http://localhost:8501
```

复制输出的 `https://...trycloudflare.com` 链接。

## 私有部署方式

如果不希望公开到 Streamlit Community Cloud，可以部署到：

- Render
- Railway
- Fly.io
- 公司内部服务器
- 一台云主机上的 Docker / systemd 服务

启动命令：

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port $PORT
```

## 当前数据模式

当前 Demo 默认使用 `Mock Demo Data`。

页面中已经预留 Real Data Mode：

- Tavily
- GDELT
- Gemini API

未配置 API Key 时，系统保持 Mock 模式，适合演示产品逻辑。

## 部署前检查

```bash
python -m compileall app.py engine
streamlit run app.py
```

打开页面后重点检查：

- 首页是否显示 Mock Demo Data banner
- ASTI 分数拆解是否正常
- 信源竞争漏斗是否正常
- 深度归因案例是否能打开
- 行动建议表是否包含 Topic / 问题 / 优先级 / 具体行动 / 预期提升指标
