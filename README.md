# 弹幕智趣 - AI 驱动的抖音直播互动引擎


基于 AI 语义理解技术的抖音直播弹幕智能互动系统，支持 Web 与桌面（Electron）两种部署方式，提供弹幕实时抓取、AI 猜词游戏、智能语义过滤、浏览器自动化输出等核心能力。



## 🎯 产品概述

### 产品形态

基于 AI 语义理解技术的抖音直播弹幕智能互动系统，支持 **桌面应用（Electron）** 和 **Web 应用** 两种部署方式。

### 核心用户

- **抖音主播**: 通过智能互动游戏提升直播间活跃度
- **直播运营团队**: 管理弹幕内容、优化互动体验
- **直播观众**: 参与猜词等互动游戏，获得趣味性和成就感

### 核心功能

| 功能模块 | 描述 |
|---------|------|
| 弹幕实时抓取 | 连接抖音直播间，通过 WebSocket 实时获取弹幕消息流 |
| AI 猜词互动游戏 | 主播发起猜词游戏，观众通过弹幕参与，系统基于语义相似度实时评分 |
| 实时排行榜 | 基于语义评分的实时排名系统，激发观众竞争热情 |
| 智能弹幕过滤 | 基于 bge-small-zh-v1.5 Embedding 的语义级过滤，精准过滤无效信息 |
| 浏览器自动化输出 | 集成 Playwright 实现弹幕自动发送到目标网页 |
| 多端部署 | 支持 Web 应用与 Electron 桌面应用两种部署方式 |

---

## 💡 创作思路

### 灵感来源

随着直播行业的快速发展，弹幕已成为观众互动的核心方式。然而，传统弹幕系统面临三大痛点：

1. **信息过载**: 海量弹幕中有效信息被淹没，主播难以关注关键内容
2. **互动形式单一**: 观众只能被动观看和发送简单弹幕，缺乏深度参与感
3. **缺乏智能理解**: 系统无法理解弹幕语义，难以实现精准互动和个性化响应

### 想解决的问题

- 让直播互动从"被动观看"向"主动参与"转变
- 利用 AI 语义理解技术，让系统能够"读懂"弹幕内容
- 打造趣味性与竞技性兼备的直播互动体验
- 帮助主播高效管理弹幕内容，提升直播间质量

### 技术选型判断

| 技术 | 选型理由 |
|-----|---------|
| bge-small-zh-v1.5 | 轻量高效的中文 Embedding 模型，适合本地部署，语义相似度计算精度高 |
| FastAPI | 高性能异步框架，支持 WebSocket 实时通信，API 开发效率高 |
| Vue 3 | 响应式前端框架，组件化开发，配合 Element Plus 快速构建 UI |
| Electron | 跨平台桌面应用方案，支持 Windows/macOS，无需额外安装环境 |
| Playwright | 浏览器自动化工具，支持弹幕自动输出到目标网页 |

---

## 🏗️ 技术架构

### 系统架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         前端层 (Vue 3)                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐          │
│  │ RoomManager  │  │ FilterConfig │  │   GameLauncher   │          │
│  │ 房间管理组件 │  │ 过滤配置组件 │  │   游戏启动组件   │          │
│  ├──────────────┤  ├──────────────┤  ├──────────────────┤          │
│  │ DanmakuViewer│  │ OutputConfig │  │   GamePanel      │          │
│  │ 弹幕展示组件 │  │ 输出配置组件 │  │   游戏面板组件   │          │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘          │
└─────────┼─────────────────┼────────────────────┼───────────────────┘
          │                 │                    │
          ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         通信层 (WebSocket)                          │
│                          实时消息广播                                │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         后端层 (FastAPI)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐          │
│  │ RoomManager  │  │ FilterEngine │  │    GameManager   │          │
│  │ 弹幕抓取管理 │  │ 智能过滤引擎 │  │   AI猜词管理器   │          │
│  ├──────────────┤  ├──────────────┤  ├──────────────────┤          │
│  │ OutputManager│  │ Performance  │  │  EmbeddingEngine │          │
│  │ 输出管理器   │  │   Monitor    │  │   语义嵌入引擎   │          │
│  └──────────────┘  └──────────────┘  └──────────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        AI 模型层 (bge-small-zh-v1.5)                │
│              本地部署的中文语义嵌入模型，支持向量编码与余弦相似度计算         │
└─────────────────────────────────────────────────────────────────────┘
```

### 核心模块说明

| 模块 | 文件 | 职责 |
|-----|------|-----|
| 弹幕抓取模块 | [backend/manager.py](backend/manager.py) | 连接抖音直播间 WebSocket，解析 Protobuf 格式消息 |
| AI 猜词游戏模块 | [backend/game_manager.py](backend/game_manager.py) | 词库管理、游戏控制、语义相似度计算、实时排行榜 |
| Embedding 语义引擎 | [backend/embedding_similarity.py](backend/embedding_similarity.py) | 词库向量预计算、余弦相似度计算、上下文加成评分 |
| 输出管理模块 | [backend/output_manager.py](backend/output_manager.py) | 浏览器自动化弹幕输出、文件输出、目标元素选择器 |
| 过滤引擎 | [backend/filter_engine.py](backend/filter_engine.py) | 关键词过滤、消息类型过滤、语义过滤 |
| 语义分析器 | [backend/semantic_analyzer.py](backend/semantic_analyzer.py) | 语义分类、问答自动回复、同义词匹配 |

### 技术栈

| 层级 | 技术 | 版本 |
|-----|------|-----|
| 前端框架 | Vue | 3.x |
| UI 组件库 | Element Plus | - |
| 构建工具 | Vite | - |
| 后端框架 | FastAPI | 0.136+ |
| 编程语言 | Python | 3.11 |
| AI 模型 | bge-small-zh-v1.5 | - |
| 浏览器自动化 | Playwright | - |
| 桌面应用 | Electron | 28 |
| 数据库 | SQLite | - |

---

## ✨ 核心创新点

### 1. 语义级弹幕评分

基于 bge-small-zh-v1.5 Embedding 模型，实现精准的中文语义相似度计算：

- **多算法支持**: 编辑距离、拼音匹配、语义相似度、Embedding 向量余弦相似度
- **混合评分策略**: 综合多种算法结果，加权计算最终得分
- **上下文感知**: 结合分类和提示词给予额外加成

### 2. 智能化问答系统

自动识别"是XXX吗"、"能XXX吗"等提问句式，基于语义分类自动回答：

- 支持 20+ 语义类别（家具、食物、动物、交通等）
- 偏旁部首分析辅助语义理解
- 同义词/近义词组匹配

### 3. 高性能消息处理

基于队列的消息广播机制：

- 支持高并发弹幕处理
- 异步消息广播，不阻塞主线程
- 自动清理过期消息，控制内存占用

### 4. 模块化架构设计

前后端分离，支持独立部署和功能扩展：

- RESTful API + WebSocket 双协议
- 插件化过滤引擎
- 可配置的相似度算法

---

## 🚀 快速开始

本项目提供两种使用方式：

### 方式一：开发者运行（Web 模式）

适合希望直接运行源码的开发者，需要预装 Python 和 Node.js。

#### 环境要求

- Python 3.10+（推荐 3.11）
- Node.js 18+
- npm

#### 一键启动（Windows）

```bash
# 1. 克隆仓库
git clone https://github.com/G542B/DouyinLiveWebFetcher.git
cd DouyinLiveWebFetcher

# 2. 双击运行 start.bat（自动安装所有依赖并启动）
start.bat
```

`start.bat` 会自动完成以下操作：
1. 安装 Python 依赖（`requirements.txt` + `backend/requirements.txt`）
2. 安装前端依赖并构建（`npm install` + `npm run build`）
3. 停止旧的 8000 端口服务
4. 启动后端服务，访问 http://localhost:8000

#### 手动逐步启动

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt
pip install -r backend/requirements.txt

# 2. 下载 AI 模型（必需，用于语义过滤与猜词游戏）
pip install huggingface_hub
huggingface-cli download BAAI/bge-small-zh-v1.5 --local-dir backend/models/bge-small-zh-v1.5

# 3. 构建前端
cd frontend
npm install
npm run build
cd ..

# 4. 启动 Web 服务
python run.py --serve
```

浏览器访问 http://localhost:8000

#### 开发模式（前后端分离热重载）

```bash
python run.py --dev
# 前端: http://localhost:5173
# 后端: http://localhost:8000
```

### 方式二：打包成桌面安装包（推荐给最终用户）

适合分发给非技术用户，打包成自包含的 Windows 安装包（包含内嵌 Python、所有依赖、AI 模型、Playwright 浏览器）。

#### 环境要求（仅打包时需要）

- Python 3.10+（用于运行打包脚本）
- Node.js 18+

#### 一键打包

```bash
# 双击运行打包脚本
build_release.bat
```

`build_release.bat` 会自动完成以下操作：
1. 检查环境（Node.js / Python）
2. 下载并配置内嵌 Python 3.11.9（无需用户预装）
3. 下载所有 Python 依赖的离线 wheel 包
4. 下载 BGE-small-zh-v1.5 AI 模型
5. 下载 Playwright Chromium 浏览器
6. 构建前端（Vite 生产模式）
7. 安装 Electron 依赖
8. 调用 electron-builder 打包成 NSIS 安装包

打包完成后，安装包位于 `electron/dist_build/` 目录下，是一个 `.exe` 文件。

最终用户只需：
1. 双击 `.exe` 安装包
2. 按照安装向导完成安装
3. 从开始菜单或桌面快捷方式启动应用

**安装后无需联网**，所有运行时依赖（Python、依赖库、模型、浏览器）都已内嵌。

#### 非交互式打包（用于 CI/CD）

```bash
build_release.bat /auto
```

### 方式三：开发模式启动桌面应用

```bash
# 安装 Electron 依赖
npm run app:install

# 开发模式启动
npm run app:start
```

---

## 📋 使用流程

### 1. 启动应用

```bash
npm run app:install
npm run app:start
```

### 2. 连接直播间

1. 在"房间管理"面板添加抖音直播间 ID
2. 点击"开始抓取"按钮
3. 等待 WebSocket 连接成功

### 3. 配置过滤规则

1. 在"过滤配置"面板选择需要显示的消息类型
2. 配置高级过滤规则（关键词、正则表达式）
3. 开启语义过滤提升内容质量

### 4. 启动猜词游戏

1. 切换到"游戏大厅"标签页
2. 管理词库（添加/编辑/删除词语）
3. 配置游戏参数（轮次、时间限制、排行榜数量）
4. 点击"开始游戏"
5. 观众通过弹幕发送猜测，系统实时评分并更新排行榜

### 5. 弹幕输出

1. 在"输出配置"面板设置目标 URL
2. 使用元素选择器定位弹幕输入框
3. 点击"开始输出"自动发送弹幕

---

## 📊 适用场景

| 场景 | 描述 |
|-----|------|
| 直播互动 | 主播发起猜词游戏，观众通过弹幕参与，提升直播间活跃度 |
| 内容过滤 | 过滤无效弹幕，提升直播间内容质量，方便主播管理 |
| 数据采集 | 弹幕数据实时采集与分析，用于直播效果评估 |
| 二次创作 | 弹幕数据导出用于内容创作（如视频剪辑、数据分析报告） |
| 教学互动 | 在线教育场景中，学生通过弹幕参与答题互动 |

---

## 📁 项目结构

```
DouyinLiveWebFetcher/
├── backend/                    # Python 后端（FastAPI）
│   ├── app.py                  # FastAPI 入口
│   ├── manager.py              # 弹幕管理器
│   ├── game_manager.py         # 猜词游戏管理
│   ├── embedding_engine.py     # Embedding 引擎
│   ├── embedding_similarity.py # 语义相似度计算
│   ├── filter_engine.py        # 过滤引擎
│   ├── semantic_analyzer.py    # 语义分析器
│   ├── output_manager.py       # 输出管理器
│   ├── database.py             # 数据库连接
│   ├── game_storage.py         # 游戏数据持久化
│   ├── config_manager.py       # 配置管理器
│   ├── performance_monitor.py  # 性能监控
│   ├── license.py              # 许可证管理
│   ├── logger.py               # 日志管理
│   ├── models.py               # 数据模型
│   ├── requirements.txt        # Python 依赖
│   └── models/                 # AI 模型文件
│       └── bge-small-zh-v1.5/  # bge-small-zh-v1.5 模型
├── frontend/                   # Vue 3 前端
│   ├── src/
│   │   ├── components/         # 业务组件（15个）
│   │   │   ├── RoomManager.vue
│   │   │   ├── FilterConfig.vue
│   │   │   ├── DanmakuViewer.vue
│   │   │   ├── GameLauncher.vue
│   │   │   ├── GamePanel.vue
│   │   │   ├── RankingBoard.vue
│   │   │   ├── WordBankManager.vue
│   │   │   ├── OutputConfig.vue
│   │   │   ├── GameHistory.vue
│   │   │   ├── PerformanceMonitor.vue
│   │   │   ├── CongratsPopup.vue
│   │   │   ├── ElementPicker.vue
│   │   │   ├── GameConfigPanel.vue
│   │   │   ├── GuessTable.vue
│   │   │   └── LicenseVerify.vue
│   │   ├── composables/        # 组合式函数
│   │   ├── App.vue             # 主应用组件
│   │   └── main.js             # 入口文件
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── electron/                   # Electron 桌面应用
│   ├── main.js                 # 主进程
│   ├── preload.js              # 预加载脚本
│   ├── progress.html           # 启动进度页
│   ├── installer.nsh           # NSIS 安装脚本
│   ├── package.json
│   └── assets/                 # 资源文件
├── protobuf/                   # Protobuf 协议定义
│   ├── douyin.proto            # 抖音协议定义
│   └── douyin.py               # 生成的 Python 代码
├── config/                     # 应用配置
│   └── app_config.json         # 配置文件
├── data/                       # 数据存储
│   └── game/                   # 游戏数据（SQLite）
├── scripts/                    # 辅助脚本
├── liveMan.py                  # 抖音弹幕抓取核心
├── main.py                     # Python 入口
├── run.py                      # 启动脚本
├── ac_signature.py             # 签名 Python 实现
├── a_bogus.js                  # 签名算法
├── sign.js / sign_v0.js        # 签名实现
├── webmssdk.js                 # 抖音前端 SDK
├── requirements.txt            # 根目录依赖
├── package.json                # 项目依赖与脚本
├── LICENSE                     # 许可证
├── README.md                   # 项目说明（本文件）
├── DEMO_INTRO.md               # Demo 介绍文档
├── APP_GUIDE.md                # 应用部署指南
├── StartWeb.bat                # Web 启动脚本
├── build.bat                   # 构建脚本
├── buildwin.bat                # Windows 构建脚本
├── buildmac.bat                # macOS 构建脚本
├── install.bat                 # 安装脚本
└── install_playwright_browsers.bat  # Playwright 浏览器安装
```

---

## 🛠️ 开发说明

### 后端开发

后端基于 FastAPI 构建，主要模块：

- `backend/app.py` - FastAPI 应用入口，定义路由与 WebSocket 端点
- `backend/manager.py` - 弹幕抓取管理器，统一管理多个直播间
- `backend/game_manager.py` - 猜词游戏管理
- `backend/embedding_engine.py` - Embedding 模型加载与推理
- `backend/output_manager.py` - 输出管理（浏览器自动化 / 文件写入）

### 前端开发

前端基于 Vue 3 + Vite，启动开发服务器：

```bash
cd frontend
npm install
npm run dev
```

### Protobuf 重新生成

如需修改抖音协议定义，编辑 `protobuf/douyin.proto` 后使用 `protoc` 重新生成：

```bash
protoc --python_out=. protobuf/douyin.proto
```

---

## 💪 开发亮点与心得

### 技术挑战与解决方案

| 挑战 | 解决方案 |
|-----|---------|
| Embedding 模型加载慢 | 异步初始化线程，不阻塞应用启动 |
| 高并发弹幕处理 | 基于队列的异步广播机制 |
| 语义相似度计算精度 | 多算法混合评分，上下文加成 |
| 打包后路径问题 | 使用 `process.resourcesPath` 正确处理路径 |

### TRAE 开发体验

使用 TRAE IDE 开发本项目的优势：

- **智能代码生成**: 快速生成前后端代码框架
- **AI 辅助调试**: 自动分析错误并提供修复建议
- **多模态交互**: 支持自然语言描述需求，自动转换为代码
- **性能优化建议**: 智能识别性能瓶颈并提供优化方案

---


## 🔮 未来规划

- [ ] 支持多直播间同时抓取
- [ ] 弹幕情感分析与可视化
- [ ] 主播助手功能（自动回复、关键信息提取）
- [ ] AI 生成词库（根据直播内容自动生成猜词题目）
- [ ] 看图猜词等更多弹幕互动游戏
