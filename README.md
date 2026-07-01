# 弹幕智趣 - AI 驱动的抖音直播互动引擎

基于 AI 语义理解技术的抖音直播弹幕智能互动系统，支持 Web 与桌面（Electron）两种部署方式，提供弹幕实时抓取、AI 猜词游戏、智能语义过滤、浏览器自动化输出等核心能力。

## 核心功能

| 功能模块 | 描述 |
|---------|------|
| 弹幕实时抓取 | 连接抖音直播间，通过 WebSocket 实时获取弹幕消息流 |
| AI 猜词互动游戏 | 主播发起猜词游戏，观众通过弹幕参与，系统基于语义相似度实时评分 |
| 实时排行榜 | 基于语义评分的实时排名系统，激发观众竞争热情 |
| 智能弹幕过滤 | 基于 bge-small-zh-v1.5 Embedding 的语义级过滤，精准过滤无效信息 |
| 浏览器自动化输出 | 集成 Playwright 实现弹幕自动发送到目标网页 |
| 多端部署 | 支持 Web 应用与 Electron 桌面应用两种部署方式 |

## 技术栈

- **后端**：Python 3.7+ / FastAPI / WebSocket / Protobuf
- **前端**：Vue 3 / Vite / Element Plus / Axios
- **桌面壳**：Electron 28 / electron-builder
- **AI 能力**：sentence-transformers + bge-small-zh-v1.5 Embedding 模型
- **浏览器自动化**：Playwright
- **协议解析**：Protobuf（抖音 WebSocket 二进制协议）

## 项目结构

```
DouyinLiveWebFetcher/
├── backend/                 # Python 后端（FastAPI）
│   ├── app.py               # FastAPI 入口
│   ├── manager.py           # 弹幕管理器
│   ├── filter_engine.py     # 过滤引擎
│   ├── semantic_analyzer.py # 语义分析
│   ├── embedding_engine.py  # Embedding 引擎
│   ├── game_manager.py      # 游戏管理
│   ├── output_manager.py    # 输出管理（浏览器/文件）
│   └── ...
├── frontend/                # Vue 3 前端
│   ├── src/
│   │   ├── components/       # 业务组件
│   │   ├── composables/     # 组合式函数
│   │   ├── App.vue
│   │   └── main.js
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── electron/                # Electron 桌面壳
│   ├── main.js
│   ├── preload.js
│   ├── progress.html
│   ├── installer.nsh
│   └── package.json
├── protobuf/                # 抖音协议定义
│   ├── douyin.proto
│   └── douyin.py
├── config/                  # 应用配置
│   └── app_config.json
├── scripts/                 # 辅助脚本
├── data/game/               # 游戏数据
├── liveMan.py               # 抖音弹幕抓取核心
├── main.py                  # Python 入口
├── run.py                   # 启动脚本
├── a_bogus.js               # 签名算法
├── sign.js / sign_v0.js     # 签名实现
├── webmssdk.js              # 抖音前端 SDK
├── ac_signature.py          # 签名 Python 实现
├── requirements.txt
└── package.json
```

## 快速开始

### 环境要求

- Python 3.7+
- Node.js 18+
- npm 或 pnpm

### 1. 克隆仓库

```bash
git clone https://github.com/G542B/DouyinLiveWebFetcher.git
cd DouyinLiveWebFetcher
```

### 2. 下载 AI 模型（必需）

语义过滤与猜词游戏依赖 `bge-small-zh-v1.5` Embedding 模型。请从 HuggingFace 下载并放置到指定目录：

```bash
# 方式一：使用 huggingface-cli
pip install huggingface_hub
huggingface-cli download BAAI/bge-small-zh-v1.5 --local-dir backend/models/bge-small-zh-v1.5

# 方式二：手动下载
# 访问 https://huggingface.co/BAAI/bge-small-zh-v1.5
# 下载所有文件到 backend/models/bge-small-zh-v1.5/
```

### 3. 安装 Python 依赖

```bash
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

### 4. 启动 Web 应用

```bash
# 启动后端服务（默认端口 8000）
python run.py
# 或
StartWeb.bat
```

浏览器访问 http://localhost:8000

### 5. 启动桌面应用（可选）

```bash
# 安装 Electron 依赖
npm run app:install

# 构建前端（首次必做）
cd frontend
npm install
npm run build
cd ..

# 启动桌面应用
npm run app:start
```

### 6. 打包桌面应用

```bash
npm run app:build:win   # Windows
npm run app:build:mac   # macOS
```

详细部署与打包说明请参考 [APP_GUIDE.md](./APP_GUIDE.md)。

## 文档导航

- [DEMO_INTRO.md](./DEMO_INTRO.md) - 产品介绍与功能演示
- [APP_GUIDE.md](./APP_GUIDE.md) - 应用部署与打包指南
- [creative_name.md](./creative_name.md) - 项目创意命名说明

## 开发说明

### 后端开发

后端基于 FastAPI 构建，主要模块：

- `backend/app.py` - FastAPI 应用入口，定义路由与 WebSocket 端点
- `backend/manager.py` - 弹幕抓取管理器，统一管理多个直播间
- `backend/filter_engine.py` - 消息过滤引擎（关键词 + 类型）
- `backend/semantic_analyzer.py` - 语义分析器（基于 Embedding 相似度）
- `backend/game_manager.py` - 猜词游戏管理
- `backend/output_manager.py` - 输出管理（浏览器自动化 / 文件写入）

### 前端开发

前端基于 Vue 3 + Vite，启动开发服务器：

```bash
cd frontend
npm install
npm run dev
```

### Protobuf 重新生成

如需修改抖音协议定义，编辑 `protobuf/douyin.proto` 后使用 `protoc` 重新生成 `douyin.py`：

```bash
protoc --python_out=. douyin.proto
```

## License

MIT License - 详见 [LICENSE](./LICENSE)
