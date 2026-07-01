const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  send: (channel, data) => {
    ipcRenderer.send(channel, data);
  },
  receive: (channel, func) => {
    ipcRenderer.on(channel, (event, ...args) => func(...args));
  },

  // 窗体管理
  openGameWindow: () => ipcRenderer.send('open-game-window'),
  openSubWindow: (type) => ipcRenderer.send('open-sub-window', type),
  closeSubWindow: () => ipcRenderer.send('close-sub-window'),
  closeGameWindow: () => ipcRenderer.send('close-game-window'),

  // 窗体事件监听
  onSubWindowClosed: (callback) => {
    ipcRenderer.on('sub-window-closed', (event, type) => callback(type));
  },
  onGameWindowClosed: (callback) => {
    ipcRenderer.on('game-window-closed', () => callback());
  },

  // 数据变更通知
  onWordsChanged: (callback) => {
    ipcRenderer.on('words-changed', () => callback());
  },
  onConfigChanged: (callback) => {
    ipcRenderer.on('config-changed', () => callback());
  },
  notifyWordsChanged: () => ipcRenderer.send('words-changed'),
  notifyConfigChanged: () => ipcRenderer.send('config-changed'),
});
