const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');
const { spawn, exec } = require('child_process');

let mainWindow;
let appProcess;
let backendMonitoringInterval;

function getAppPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'app');
  } else {
    return path.join(__dirname, '..');
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    resizable: true,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
    icon: path.join(__dirname, 'assets', 'icon.png'),
  });

  mainWindow.loadFile('progress.html');
  mainWindow.setMenu(null);
}

function sendProgress(progress, status) {
  if (mainWindow) {
    mainWindow.webContents.send('progress', { progress, status });
  }
}

function sendLog(message, type = '') {
  if (mainWindow) {
    mainWindow.webContents.send('log', { message, type });
  }
}

function sendError(message) {
  if (mainWindow) {
    mainWindow.webContents.send('error', { message });
  }
}

function sendSuccess() {
  if (mainWindow) {
    mainWindow.webContents.send('success');
  }
}

function checkPython() {
  return new Promise((resolve, reject) => {
    if (app.isPackaged) {
      const embeddedPython = path.join(process.resourcesPath, 'python', 'python.exe');
      if (fs.existsSync(embeddedPython)) {
        sendLog(`使用内嵌 Python: ${embeddedPython}`, 'success');
        resolve(embeddedPython);
        return;
      }
      reject('内嵌 Python 未找到，请重新安装应用');
      return;
    }
    sendLog('检测 Python 环境...');
    exec('python --version', (error, stdout, stderr) => {
      if (error) {
        exec('python3 --version', (error3, stdout3, stderr3) => {
          if (error3) {
            reject('未检测到 Python，请先安装 Python 3.7+');
          } else {
            sendLog(`Python 版本: ${stdout3 || stderr3}`, 'success');
            resolve('python3');
          }
        });
      } else {
        sendLog(`Python 版本: ${stdout || stderr}`, 'success');
        resolve('python');
      }
    });
  });
}

function checkNode() {
  return new Promise((resolve, reject) => {
    if (app.isPackaged) {
      sendLog('已打包应用，跳过 Node.js 检测', 'success');
      resolve();
      return;
    }
    sendLog('检测 Node.js 环境...');
    exec('node --version', (error, stdout, stderr) => {
      if (error) {
        reject('未检测到 Node.js，请先安装 Node.js');
      } else {
        sendLog(`Node.js 版本: ${stdout || stderr}`, 'success');
        resolve();
      }
    });
  });
}

function installPythonDeps(pythonCmd) {
  return new Promise((resolve, reject) => {
    if (app.isPackaged) {
      sendLog('已打包应用，跳过 Python 依赖安装', 'success');
      resolve();
      return;
    }
    sendLog('安装 Python 依赖...');
    const projectRoot = getAppPath();
    const requirementsPath = path.join(projectRoot, 'requirements.txt');
    
    sendLog(`项目根目录: ${projectRoot}`);
    sendLog(`requirements.txt 路径: ${requirementsPath}`);
    
    if (!fs.existsSync(requirementsPath)) {
      reject(`找不到 requirements.txt: ${requirementsPath}`);
      return;
    }
    
    const process = spawn(pythonCmd, ['-m', 'pip', 'install', '-r', requirementsPath], {
      cwd: projectRoot
    });

    process.stdout.on('data', (data) => {
      sendLog(data.toString().trim());
    });

    process.stderr.on('data', (data) => {
      sendLog(data.toString().trim());
    });

    process.on('close', (code) => {
      if (code === 0) {
        sendLog('Python 依赖安装成功', 'success');
        resolve();
      } else {
        reject('Python 依赖安装失败');
      }
    });
  });
}

function installFrontendDeps() {
  return new Promise((resolve, reject) => {
    if (app.isPackaged) {
      sendLog('已打包应用，跳过前端依赖安装', 'success');
      resolve();
      return;
    }
    
    sendLog('安装前端依赖...');
    const frontendDir = path.join(getAppPath(), 'frontend');
    
    const process = spawn('npm', ['install'], {
      cwd: frontendDir,
      shell: true
    });

    process.stdout.on('data', (data) => {
      sendLog(data.toString().trim());
    });

    process.stderr.on('data', (data) => {
      sendLog(data.toString().trim());
    });

    process.on('close', (code) => {
      if (code === 0) {
        sendLog('前端依赖安装成功', 'success');
        resolve();
      } else {
        reject('前端依赖安装失败');
      }
    });
  });
}

function buildFrontend() {
  return new Promise((resolve, reject) => {
    if (app.isPackaged) {
      sendLog('已打包应用，跳过前端构建', 'success');
      resolve();
      return;
    }
    
    sendLog('构建前端...');
    const frontendDir = path.join(getAppPath(), 'frontend');
    
    const process = spawn('npm', ['run', 'build'], {
      cwd: frontendDir,
      shell: true
    });

    process.stdout.on('data', (data) => {
      sendLog(data.toString().trim());
    });

    process.stderr.on('data', (data) => {
      sendLog(data.toString().trim());
    });

    process.on('close', (code) => {
      if (code === 0) {
        sendLog('前端构建成功', 'success');
        resolve();
      } else {
        reject('前端构建失败');
      }
    });
  });
}

function startBackend(pythonCmd) {
  return new Promise((resolve, reject) => {
    sendLog('启动后端服务...');
    const projectRoot = getAppPath();
    const runPyPath = path.join(projectRoot, 'run.py');
    
    sendLog(`项目根目录: ${projectRoot}`);
    sendLog(`run.py 路径: ${runPyPath}`);
    
    if (!fs.existsSync(runPyPath)) {
      const error = `找不到 run.py: ${runPyPath}`;
      sendLog(error, 'error');
      reject(error);
      return;
    }
    
    const env = Object.assign({}, process.env, {
      PYTHONUTF8: '1',
      PYTHONIOENCODING: 'utf-8',
      PYTHONUNBUFFERED: '1'
    });
    if (app.isPackaged) {
      const pythonDir = path.join(process.resourcesPath, 'python');
      sendLog(`内嵌 Python 目录: ${pythonDir}`);
      
      if (!fs.existsSync(pythonDir)) {
        sendLog(`警告: 内嵌 Python 目录不存在: ${pythonDir}`, 'error');
      }
      
      const sitePackages = path.join(pythonDir, 'Lib', 'site-packages');
      env.PYTHONPATH = sitePackages;
      env.PATH = pythonDir + ';' + (env.PATH || '');

      // 关键修复：设置 Playwright 浏览器路径
      // 让 Playwright 在标准的 %LOCALAPPDATA%\ms-playwright 目录查找浏览器
      // 避免在打包环境下走错误的默认路径导致 30 秒冷启动超时
      const localAppData = process.env.LOCALAPPDATA || path.join(process.env.USERPROFILE || '', 'AppData', 'Local');
      const playwrightBrowsersPath = path.join(localAppData, 'ms-playwright');
      env.PLAYWRIGHT_BROWSERS_PATH = playwrightBrowsersPath;

      // 透传 HTTP 代理设置（如果有）
      if (process.env.HTTP_PROXY) env.HTTP_PROXY = process.env.HTTP_PROXY;
      if (process.env.HTTPS_PROXY) env.HTTPS_PROXY = process.env.HTTPS_PROXY;
      if (process.env.NO_PROXY) env.NO_PROXY = process.env.NO_PROXY;
    }

    sendLog(`执行命令: ${pythonCmd} ${runPyPath} --serve`);

    appProcess = spawn(pythonCmd, [runPyPath, '--serve'], {
      cwd: projectRoot,
      detached: process.platform !== 'win32',
      env: env
    });

    let resolved = false;
    let startupTimeout = null;
    let healthCheckInterval = null;

    const clearStartupTimers = () => {
      if (startupTimeout) {
        clearTimeout(startupTimeout);
        startupTimeout = null;
      }
      if (healthCheckInterval) {
        clearInterval(healthCheckInterval);
        healthCheckInterval = null;
      }
    };

    const markBackendReady = () => {
      if (resolved) return;
      sendLog('Backend service started successfully', 'success');
      resolved = true;
      clearStartupTimers();
      startBackendMonitoring();
      resolve();
    };

    const checkBackendReady = () => {
      const request = http.get('http://127.0.0.1:8000/', (response) => {
        response.resume();
        if (response.statusCode && response.statusCode < 500) {
          markBackendReady();
        }
      });
      request.on('error', () => {});
      request.setTimeout(1000, () => request.destroy());
    };

    appProcess.stdout.on('data', (data) => {
      const output = data.toString().trim();
      sendLog(output);
      
      if (!resolved && (output.includes('Uvicorn running') || output.includes('Application startup complete'))) {
        markBackendReady();
      }
    });

    appProcess.stderr.on('data', (data) => {
      const output = data.toString().trim();
      sendLog(output, 'error');

      if (!resolved && (output.includes('Uvicorn running') || output.includes('Application startup complete'))) {
        markBackendReady();
      }
    });

    appProcess.on('error', (error) => {
      sendLog(`后端进程错误: ${error}`, 'error');
      if (!resolved) {
        resolved = true;
        clearStartupTimers();
        reject(error);
      }
    });

    appProcess.on('close', (code, signal) => {
      const message = code !== 0 
        ? `后端服务已退出，退出代码: ${code}, 信号: ${signal}` 
        : '后端服务已正常退出';
      sendLog(message, code !== 0 ? 'error' : 'info');
      
      if (!resolved) {
        resolved = true;
        clearStartupTimers();
        reject(new Error(message));
      }
      
      stopBackendMonitoring();
    });

    healthCheckInterval = setInterval(checkBackendReady, 500);
    checkBackendReady();

    startupTimeout = setTimeout(() => {
      if (!resolved) {
        sendLog('后端服务启动超时，继续尝试连接...', 'warn');
        startBackendMonitoring();
        resolved = true;
        clearStartupTimers();
        resolve();
      }
    }, 30000);
  });
}

function startBackendMonitoring() {
  if (backendMonitoringInterval) {
    clearInterval(backendMonitoringInterval);
  }
  
  backendMonitoringInterval = setInterval(() => {
    if (!appProcess || appProcess.killed) {
      sendLog('检测到后端服务已停止，尝试重新启动...', 'error');
      stopBackendMonitoring();
      
      // 尝试重新启动后端
      checkPython().then((pythonCmd) => {
        return startBackend(pythonCmd);
      }).catch((error) => {
        sendLog(`自动重启失败: ${error}`, 'error');
      });
    }
  }, 5000);
  
  console.log('[Electron] 后端监控已启动');
}

function stopBackendMonitoring() {
  if (backendMonitoringInterval) {
    clearInterval(backendMonitoringInterval);
    backendMonitoringInterval = null;
    console.log('[Electron] 后端监控已停止');
  }
}

function openAppInWindow() {
  sendLog('正在打开应用...');
  setTimeout(() => {
    mainWindow.loadURL('http://localhost:8000');
    mainWindow.show();
  }, 1000);
}

async function runSetup() {
  try {
    sendProgress(5, '检查环境...');
    sendLog(`应用是否打包: ${app.isPackaged ? '是' : '否'}`);
    sendLog(`应用路径: ${getAppPath()}`);
    
    const pythonCmd = await checkPython();
    sendProgress(15, '检查 Node.js...');
    await checkNode();
    
    sendProgress(25, '安装依赖...');
    await installPythonDeps(pythonCmd);
    sendProgress(50, '准备应用...');
    await installFrontendDeps();
    await buildFrontend();
    
    sendProgress(85, '启动服务...');
    await startBackend(pythonCmd);
    
    sendProgress(100, '准备完成！');
    sendSuccess();
    
    openAppInWindow();
    
  } catch (error) {
    sendLog(error, 'error');
    sendError(error);
  }
}

app.whenReady().then(() => {
  createWindow();

  ipcMain.on('ready', () => {
    runSetup();
  });

  ipcMain.on('retry', () => {
    runSetup();
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

function cleanupAppProcess() {
    stopBackendMonitoring();
    
    if (!appProcess) return;
    
    console.log('[Electron] 正在停止后端服务...');
    
    if (process.platform === 'win32') {
        try {
            // 使用 taskkill 强制终止进程树
            spawn('taskkill', ['/pid', appProcess.pid, '/F', '/T']);
        } catch (e) {
            console.error('[Electron] taskkill 失败:', e);
        }
    } else {
        try {
            // 先尝试优雅终止
            process.kill(appProcess.pid, 'SIGTERM');
            // 等待一小段时间
            setTimeout(() => {
                if (appProcess && !appProcess.killed) {
                    try {
                        process.kill(-appProcess.pid, 'SIGKILL');
                    } catch (e) {
                        console.error('[Electron] SIGKILL 失败:', e);
                    }
                }
            }, 2000);
        } catch (e) {
            console.error('[Electron] 终止进程失败:', e);
        }
    }
    
    appProcess = null;
}


app.on('before-quit', (e) => {
    if (appProcess) {
        e.preventDefault(); // 阻止立即退出
        cleanupAppProcess();
        // 等待一段时间后再退出
        setTimeout(() => {
            app.quit();
        }, 1000);
    }
});

app.on('window-all-closed', () => {
    console.log('[Electron] 所有窗口已关闭');
    cleanupAppProcess();
    if (process.platform !== 'darwin') {
        app.quit();
    }
});
