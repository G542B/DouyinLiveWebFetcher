# 抖音弹幕抓取工具 - 桌面应用指南

## 开发环境运行

1. 首先安装 Electron 依赖：
   ```bash
   npm run app:install
   ```

2. 启动应用：
   ```bash
   npm run app:start
   ```

## 打包应用

### 重要！打包前准备

在打包应用之前，**必须先构建前端**！因为打包后的应用需要预构建的前端文件：

```bash
cd frontend
npm install
npm run build
cd ..
```

### Windows

```bash
npm run app:build:win
```

### macOS

```bash
npm run app:build:mac
```

打包后的安装包将位于 `electron/dist/` 目录中。

## 前置要求

用户系统需要提前安装：
- Python 3.7+
- Node.js

## 应用功能

- 自动检测并安装 Python 依赖
- 自动检测并安装前端依赖（开发模式）
- 自动构建前端（开发模式）
- 启动后端服务
- 自动打开浏览器访问应用
- 显示安装进度和日志
- 错误提示和重试功能
- 支持 Windows 和 macOS 双平台

## 修复内容

- **修复了打包后找不到文件的问题**：添加了正确的路径处理，打包后使用 `process.resourcesPath/app` 作为项目根目录
- **添加了开发/打包模式判断**：通过 `app.isPackaged` 判断当前是开发环境还是打包环境
- **优化了打包流程**：配置 `extraResources` 将项目文件正确打包到安装包中
- **跳过打包后的前端构建**：打包模式下不再重复构建前端，直接使用预构建的 `frontend/dist`
