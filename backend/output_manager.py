import os
import threading
import time
import queue
import uuid
import concurrent.futures
from collections import deque
from datetime import datetime
from typing import Optional, Callable, List

from .filter_engine import filter_engine
from .config_manager import config_manager

from playwright.sync_api import sync_playwright, Page, Browser


# 可输出的用户交互消息类型白名单（非用户交互类系统消息不输出）
OUTPUTTABLE_MESSAGE_TYPES = {
    'WebcastChatMessage',       # 聊天消息
    'WebcastGiftMessage',       # 礼物消息
    'WebcastLikeMessage',       # 点赞消息
    'WebcastMemberMessage',     # 进入直播间
    'WebcastSocialMessage',     # 关注消息
    'WebcastFansclubMessage',   # 粉丝团消息
    'WebcastEmojiChatMessage',  # 表情包消息
    'WebcastRoomUserSeqMessage', # 在线观众统计
}

# 系统/内部消息类型（这些不应该被输出）
SYSTEM_MESSAGE_TYPES = {
    'WebcastControlMessage',
    'WebcastRoomMessage',
    'WebcastRoomStatsMessage',
    'WebcastRoomRankMessage',
    'WebcastRoomStreamAdaptationMessage',
}


PICKER_JS = """
() => {
    if (window.__danmakuPickerActive) return 'already_active';
    window.__danmakuPickerActive = true;
    window.__danmakuPickerResult = null;

    const overlay = document.createElement('div');
    overlay.id = '__danmaku_picker_overlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:2147483647;pointer-events:none;';
    document.body.appendChild(overlay);

    const highlight = document.createElement('div');
    highlight.id = '__danmaku_picker_highlight';
    highlight.style.cssText = 'position:absolute;border:2px solid #409eff;background:rgba(64,158,255,0.1);pointer-events:none;display:none;z-index:2147483646;transition:all 0.1s ease;';
    document.body.appendChild(highlight);

    const label = document.createElement('div');
    label.id = '__danmaku_picker_label';
    label.style.cssText = 'position:absolute;background:#409eff;color:white;padding:2px 8px;font-size:12px;border-radius:4px;pointer-events:none;display:none;z-index:2147483647;white-space:nowrap;';
    document.body.appendChild(label);

    // ── 判断 class 是否为动态 style-hash（如 _21T5T、css-1abcde、a1b2c3 等） ──
    function isDynamicClass(cls) {
        // 包含 __、sc-、css- 前缀
        if (/^(css-|sc-|_|__)[a-z0-9_-]{1,20}$/i.test(cls)) return true;
        // 纯字母+数字混合，长度 <= 8 且非英文单词（疑似 hash）
        if (/^[a-zA-Z0-9_-]{1,8}$/.test(cls) && !/^[a-z]{2,}$/i.test(cls)) return true;
        // 包含 uuid 或 hash 特征
        if (/[0-9]{4,}/.test(cls)) return true;
        return false;
    }

    // ── 提取元素上所有稳定、有意义的属性 ──
    const STABLE_ATTRS = [
        'placeholder', 'aria-label', 'aria-labelledby', 'title',
        'data-testid', 'data-test', 'data-cy', 'data-qa', 'data-id',
        'name', 'type', 'role', 'for'
    ];

    function getStableAttrs(el) {
        var attrs = {};
        for (var i = 0; i < el.attributes.length; i++) {
            var name = el.attributes[i].name;
            var value = el.attributes[i].value;
            if (!value) continue;
            var lowerName = name.toLowerCase();
            // 只看稳定属性列表
            if (STABLE_ATTRS.indexOf(lowerName) !== -1) {
                attrs[lowerName] = value;
            }
            // 也捕获自定义 data-* 且值不是过长 hash
            if (/^data-/.test(lowerName) && value.length < 60) {
                attrs[lowerName] = value;
            }
        }
        return attrs;
    }

    // ── 用稳定属性生成 selectors ──
    function buildAttrSelectors(el) {
        var tag = el.tagName.toLowerCase();
        var selectors = [];
        var attrs = getStableAttrs(el);

        // 1) id 最高优先级
        if (el.id) {
            selectors.push({ s: '#' + CSS.escape(el.id), rank: 1 });
        }

        // 2) data-testid 等测试属性
        var testKeys = ['data-testid', 'data-test', 'data-cy', 'data-qa', 'data-id'];
        for (var t = 0; t < testKeys.length; t++) {
            if (attrs[testKeys[t]]) {
                var val = attrs[testKeys[t]];
                if (val.length < 80) {
                    selectors.push({ s: tag + '[' + testKeys[t] + '="' + CSS.escape(val) + '"]', rank: 2 });
                }
            }
        }

        // 3) placeholder（登录输入框最重要的属性）
        if (attrs['placeholder']) {
            var ph = attrs['placeholder'];
            if (ph.length < 60) {
                selectors.push({ s: tag + '[placeholder="' + CSS.escape(ph) + '"]', rank: 3 });
            }
        }

        // 4) aria-label
        if (attrs['aria-label']) {
            var al = attrs['aria-label'];
            if (al.length < 60) {
                selectors.push({ s: tag + '[aria-label="' + CSS.escape(al) + '"]', rank: 4 });
            }
        }

        // 5) title
        if (attrs['title']) {
            var titleVal = attrs['title'];
            if (titleVal.length < 60) {
                selectors.push({ s: tag + '[title="' + CSS.escape(titleVal) + '"]', rank: 5 });
            }
        }

        // 6) name
        if (attrs['name']) {
            selectors.push({ s: tag + '[name="' + CSS.escape(attrs['name']) + '"]', rank: 6 });
        }

        // 7) type（仅对 input/button 有效，且值不能是 "hidden" 等无意义值）
        if (attrs['type'] && tag === 'input') {
            var typeVal = attrs['type'];
            if (['text', 'password', 'email', 'tel', 'number', 'search', 'url'].indexOf(typeVal) !== -1) {
                selectors.push({ s: 'input[type="' + typeVal + '"]', rank: 7 });
            }
        }
        if (attrs['type'] && tag === 'button') {
            selectors.push({ s: 'button[type="' + attrs['type'] + '"]', rank: 7 });
        }

        // 8) role
        if (attrs['role']) {
            selectors.push({ s: tag + '[role="' + CSS.escape(attrs['role']) + '"]', rank: 8 });
        }

        // 去重（相同 selector 只保留 rank 最高的）
        var seen = {};
        var deduped = [];
        for (var i = 0; i < selectors.length; i++) {
            if (!seen[selectors[i].s]) {
                seen[selectors[i].s] = true;
                deduped.push(selectors[i]);
            }
        }
        deduped.sort(function (a, b) { return a.rank - b.rank; });
        return deduped;
    }

    // ── 稳定的 short-path（只使用 tag + :nth-of-type，完全绕过 class） ──
    function buildStablePath(el) {
        var parts = [];
        var current = el;
        var maxDepth = 6; // 只取前 6 层避免过长
        while (current && current !== document.body && current !== document.documentElement && parts.length < maxDepth) {
            var tag = current.tagName.toLowerCase();
            var parent = current.parentElement;
            if (parent) {
                var siblings = Array.from(parent.children).filter(function (c) { return c.tagName === current.tagName; });
                if (siblings.length > 1) {
                    var idx = siblings.indexOf(current) + 1;
                    tag += ':nth-of-type(' + idx + ')';
                }
            }
            parts.unshift(tag);
            current = parent;
        }
        return parts.join(' > ');
    }

    // ── 包含稳定 class 的路径（只为 input/button 等有用元素生成，过滤 dynamic class） ──
    function buildStableClassPath(el) {
        // 只对交互元素生成
        var tag = el.tagName.toLowerCase();
        if (['input', 'button', 'textarea', 'select', 'a'].indexOf(tag) === -1 && !el.onclick && !el.getAttribute('role')) return null;

        var parts = [];
        var current = el;
        var maxDepth = 4;
        while (current && current !== document.body && current !== document.documentElement && parts.length < maxDepth) {
            var seg = current.tagName.toLowerCase();
            var parent = current.parentElement;

            // 仅附加看起来稳定的 class
            if (current.className && typeof current.className === 'string') {
                var classes = current.className.trim().split(/\\s+/).filter(function (c) {
                    return c && !c.startsWith('__danmaku') && !isDynamicClass(c);
                });
                if (classes.length > 0) {
                    // 最多用 2 个 class 避免太长
                    seg += '.' + classes.slice(0, 2).map(function (c) { return CSS.escape(c); }).join('.');
                }
            }

            if (parent) {
                var siblings = Array.from(parent.children).filter(function (c) { return c.tagName === current.tagName; });
                if (siblings.length > 1) {
                    var idx = siblings.indexOf(current) + 1;
                    seg += ':nth-of-type(' + idx + ')';
                }
            }
            parts.unshift(seg);
            current = parent;
        }
        return parts.join(' > ');
    }

    // ── 主入口：返回最适合的 selector ──
    function getBestSelector(el) {
        var attrSelectors = buildAttrSelectors(el);

        // 如果有基于属性的 selector，选 rank 最高的返回
        if (attrSelectors.length > 0) {
            // 额外确认一下 rank 1-6 的属性选择器在页面中是否唯一
            for (var i = 0; i < attrSelectors.length; i++) {
                // 如果 rank <= 6 且唯一，直接使用
                if (attrSelectors[i].rank <= 6) {
                    try {
                        var matches = document.querySelectorAll(attrSelectors[i].s);
                        if (matches.length === 1) {
                            return attrSelectors[i].s;
                        }
                    } catch (e) {
                        // 忽略
                    }
                }
            }
            // 如果没找到唯一的，返回第一个 rank 最高的
            return attrSelectors[0].s;
        }

        // 没有属性选择器，尝试 class-path
        var classPath = buildStableClassPath(el);
        if (classPath) return classPath;

        // 最后兜底：只用 tag + :nth-of-type
        return buildStablePath(el);
    }

    // ── 收集所有候选 selector（用于前端显示/选择） ──
    function getAllSelectors(el) {
        var list = [];
        var attrSelectors = buildAttrSelectors(el);

        for (var i = 0; i < attrSelectors.length; i++) {
            list.push(attrSelectors[i].s);
        }

        var classPath = buildStableClassPath(el);
        if (classPath && list.indexOf(classPath) === -1) list.push(classPath);

        var stablePath = buildStablePath(el);
        if (stablePath && list.indexOf(stablePath) === -1) list.push(stablePath);

        return list;
    }

    function getElementType(el) {
        var tag = el.tagName.toLowerCase();
        if (tag === 'textarea') return 'input';
        if (tag === 'input' && (!el.type || el.type === 'text' || el.type === 'search' || el.type === 'email' || el.type === 'tel' || el.type === 'password' || el.type === 'number' || el.type === 'url')) return 'input';
        if (tag === 'input' && (el.type === 'button' || el.type === 'submit')) return 'button';
        if (tag === 'button' || tag === 'a' || el.getAttribute('role') === 'button' || el.onclick || el.getAttribute('type') === 'submit') return 'button';
        if (el.contentEditable === 'true' || el.contentEditable === '') return 'input';
        if (tag === 'select') return 'input';
        return 'other';
    }

    function onMouseOver(e) {
        if (!window.__danmakuPickerActive) return;
        var el = e.target;
        if (el.id && el.id.startsWith('__danmaku')) return;

        var rect = el.getBoundingClientRect();
        highlight.style.display = 'block';
        highlight.style.left = rect.left + 'px';
        highlight.style.top = rect.top + 'px';
        highlight.style.width = rect.width + 'px';
        highlight.style.height = rect.height + 'px';

        var best = getBestSelector(el);
        var elType = getElementType(el);
        label.textContent = el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + ' [' + elType + ']';
        label.style.display = 'block';
        label.style.left = rect.left + 'px';
        label.style.top = Math.max(0, rect.top - 24) + 'px';
    }

    function onClick(e) {
        if (!window.__danmakuPickerActive) return;
        e.preventDefault();
        e.stopPropagation();

        var el = e.target;
        if (el.id && el.id.startsWith('__danmaku')) return;

        var best = getBestSelector(el);
        var allSelectors = getAllSelectors(el);
        var textPreview = (el.textContent || '').trim().substring(0, 50);
        var elType = getElementType(el);
        var attrs = getStableAttrs(el);

        // 收集重要属性用于前端显示
        var importantAttrs = {};
        var attrKeys = ['placeholder', 'aria-label', 'title', 'data-testid', 'name', 'type'];
        for (var k = 0; k < attrKeys.length; k++) {
            if (attrs[attrKeys[k]]) {
                importantAttrs[attrKeys[k]] = attrs[attrKeys[k]];
            }
        }

        window.__danmakuPickerResult = {
            selector: best,
            tag_name: el.tagName.toLowerCase(),
            text_preview: textPreview,
            element_type: elType,
            // 新字段
            selectors: allSelectors,
            important_attrs: importantAttrs
        };

        highlight.style.border = '2px solid #67c23a';
        highlight.style.background = 'rgba(103,194,58,0.15)';
        setTimeout(function () {
            highlight.style.border = '2px solid #409eff';
            highlight.style.background = 'rgba(64,158,255,0.1)';
        }, 500);
    }

    document.addEventListener('mouseover', onMouseOver, true);
    document.addEventListener('click', onClick, true);

    window.__danmakuPickerCleanup = function () {
        document.removeEventListener('mouseover', onMouseOver, true);
        document.removeEventListener('click', onClick, true);
        overlay.remove();
        highlight.remove();
        label.remove();
        window.__danmakuPickerActive = false;
    };

    return 'picker_started';
}
"""

PICKER_CLEANUP_JS = """
() => {
    if (window.__danmakuPickerCleanup) {
        window.__danmakuPickerCleanup();
    }
    return 'picker_stopped';
}
"""

PICKER_RESULT_JS = """
() => {
    return window.__danmakuPickerResult || null;
}
"""

RESIZE_MONITOR_JS = """
() => {
    if (window.__danmakuResizeMonitor) return 'already_active';
    window.__danmakuResizeMonitor = true;
    window.__danmakuLastResize = {
        width: window.innerWidth,
        height: window.innerHeight,
        timestamp: Date.now()
    };
    window.addEventListener('resize', function() {
        window.__danmakuLastResize = {
            width: window.innerWidth,
            height: window.innerHeight,
            timestamp: Date.now()
        };
    });
    return 'resize_monitor_started';
}
"""


class DanmakuBuffer:
    def __init__(self, max_size=10000, max_age_seconds=600, cleanup_interval=30):
        self._queue = deque()
        self._max_size = max_size
        self._max_age_seconds = max_age_seconds
        self._lock = threading.Lock()
        self._cleanup_interval = cleanup_interval
        self._cleanup_thread = None
        self._cleanup_running = False
        self._cleanup_stop_event = threading.Event()
        self._total_messages = 0
        self._cleanup_count = 0
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            return
        self._cleanup_running = True
        self._cleanup_stop_event.clear()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def _stop_cleanup_thread(self):
        self._cleanup_running = False
        self._cleanup_stop_event.set()
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=2.0)
    
    def shutdown(self):
        """关闭 buffer，停止清理线程并清空数据"""
        print("[DanmakuBuffer] 正在关闭...")
        self._stop_cleanup_thread()
        with self._lock:
            self._queue.clear()
        print("[DanmakuBuffer] 已关闭")

    def _cleanup_loop(self):
        while self._cleanup_running and not self._cleanup_stop_event.is_set():
            try:
                if self._cleanup_stop_event.wait(timeout=self._cleanup_interval):
                    break
                self._cleanup()
            except Exception:
                pass

    def _cleanup(self):
        with self._lock:
            now = datetime.now()
            original_size = len(self._queue)
            
            cutoff_time = now.timestamp() - self._max_age_seconds
            self._queue = deque([
                msg for msg in self._queue
                if self._get_timestamp(msg) > cutoff_time
            ])
            
            while len(self._queue) > self._max_size:
                self._queue.popleft()
                self._cleanup_count += 1
            
            cleaned = original_size - len(self._queue)
            if cleaned > 0:
                self._cleanup_count += cleaned

    def _get_timestamp(self, message: dict) -> float:
        ts_str = message.get('timestamp')
        if not ts_str:
            return datetime.now().timestamp()
        try:
            dt = datetime.fromisoformat(ts_str)
            return dt.timestamp()
        except (ValueError, TypeError):
            return datetime.now().timestamp()

    def push(self, message: dict):
        with self._lock:
            self._queue.append(message)
            self._total_messages += 1
            
            while len(self._queue) > self._max_size:
                self._queue.popleft()
                self._cleanup_count += 1

    def get_latest(self, since_timestamp: Optional[str] = None) -> List[dict]:
        with self._lock:
            if since_timestamp:
                return [m for m in self._queue if m.get('timestamp', '') > since_timestamp]
            return list(self._queue)

    def clear(self):
        with self._lock:
            self._queue.clear()

    @property
    def size(self):
        with self._lock:
            return len(self._queue)

    @property
    def stats(self):
        with self._lock:
            return {
                'current_size': len(self._queue),
                'max_size': self._max_size,
                'max_age_seconds': self._max_age_seconds,
                'total_messages': self._total_messages,
                'cleanup_count': self._cleanup_count
            }


class DanmakuOutputConfig:
    def __init__(self):
        self.output_mode: str = 'browser'
        self.target_url: str = ''
        self.textarea_selector: str = ''
        self.button_selector: str = ''
        self.textarea_selectors: list = []  # 备选选择器列表（新增）
        self.button_selectors: list = []    # 备选选择器列表（新增）
        self.browser_headless: bool = False
        self.file_output_path: str = ''
        self.file_append_mode: bool = True
        self.send_mode: str = 'sequential'
        self.send_interval: float = 2.0
        self.auto_click_button: bool = True
        self.auto_press_enter: bool = False
        self.add_newline: bool = True
        self.include_username: bool = True
        self.include_timestamp: bool = False

    def to_dict(self):
        return {
            'output_mode': self.output_mode,
            'target_url': self.target_url,
            'textarea_selector': self.textarea_selector,
            'button_selector': self.button_selector,
            'textarea_selectors': self.textarea_selectors,
            'button_selectors': self.button_selectors,
            'browser_headless': self.browser_headless,
            'file_output_path': self.file_output_path,
            'file_append_mode': self.file_append_mode,
            'send_mode': self.send_mode,
            'send_interval': self.send_interval,
            'auto_click_button': self.auto_click_button,
            'auto_press_enter': self.auto_press_enter,
            'add_newline': self.add_newline,
            'include_username': self.include_username,
            'include_timestamp': self.include_timestamp,
        }

    def update(self, data: dict):
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)


class DanmakuOutputStatus:
    def __init__(self):
        self.running: bool = False
        self.last_execution_time: Optional[str] = None
        self.total_sent: int = 0
        self.last_error: Optional[str] = None
        self.browser_connected: bool = False
        self.status_message: str = '就绪'

    def to_dict(self):
        return {
            'running': self.running,
            'last_execution_time': self.last_execution_time,
            'total_sent': self.total_sent,
            'last_error': self.last_error,
            'browser_connected': self.browser_connected,
            'status_message': self.status_message,
        }


class BrowserOutputStatus:
    """浏览器输出状态（独立控制）"""
    def __init__(self):
        self.running: bool = False
        self.last_execution_time: Optional[str] = None
        self.total_sent: int = 0
        self.last_error: Optional[str] = None
        self.status_message: str = '就绪'

    def to_dict(self):
        return {
            'running': self.running,
            'last_execution_time': self.last_execution_time,
            'total_sent': self.total_sent,
            'last_error': self.last_error,
            'status_message': self.status_message,
        }


class FileOutputStatus:
    """文件输出状态（独立控制）"""
    def __init__(self):
        self.running: bool = False
        self.last_execution_time: Optional[str] = None
        self.total_sent: int = 0
        self.last_error: Optional[str] = None
        self.status_message: str = '就绪'

    def to_dict(self):
        return {
            'running': self.running,
            'last_execution_time': self.last_execution_time,
            'total_sent': self.total_sent,
            'last_error': self.last_error,
            'status_message': self.status_message,
        }


class DanmakuOutputManager:
    _instance = None

    # 反调试脚本：必须安全，不能破坏页面自身的 polyfill（如 Function.prototype.bind）
    # 关键原则：不要直接覆盖 window.Function / window.eval / window.setInterval 等核心 API
    # 这些覆盖会破坏框架的 polyfill 检测，导致 vendor chunk 出现
    # "Function.prototype.bind called on incompatible undefined" 错误
    ANTI_DEBUG_SCRIPT = r"""
(function() {
  // 检测页面是否已经存在 _antiDebugApplied 标记，避免重复注入
  if (window.__antiDebugApplied) return;
  Object.defineProperty(window, '__antiDebugApplied', {
    value: true, writable: false, configurable: false
  });

  // ========== 1. 隐藏 webdriver 属性（重要，必须最先做） ==========
  try {
    Object.defineProperty(navigator, 'webdriver', {
      get: function() { return undefined; },
      configurable: true
    });
  } catch(e) {}

  // ========== 2. 隐藏 Playwright/CDP 特征（只隐藏已知标记） ==========
  try {
    if (document.querySelector) {
      var origQuerySelector = document.querySelector.bind(document);
      var origQuerySelectorAll = document.querySelectorAll.bind(document);
      // 仅当原生方法存在时再覆盖
      document.querySelector = function(selector) {
        if (typeof selector === 'string' &&
            (selector === '#__playwright' || selector === '#__pw_automation' ||
             selector === '#__pw_debugger' || selector === '#__playwright_automation__')) {
          return null;
        }
        return origQuerySelector(selector);
      };
      document.querySelectorAll = function(selector) {
        if (typeof selector === 'string' &&
            (selector === '#__playwright' || selector === '#__pw_automation' ||
             selector === '#__pw_debugger' || selector === '#__playwright_automation__')) {
          return document.createDocumentFragment();
        }
        return origQuerySelectorAll(selector);
      };
    }
  } catch(e) {}

  // ========== 3. 隐藏 Chrome 自动化扩展特征 ==========
  try {
    if (window.chrome && window.chrome.runtime && window.chrome.runtime.onConnect) {
      // 不删除 chrome 对象，只清空可疑的事件监听
      window.chrome.runtime.onConnect = undefined;
    }
  } catch(e) {}

  // ========== 4. 修补 Permissions API（只针对 notifications 探测） ==========
  try {
    if (navigator.permissions && navigator.permissions.query) {
      var origPermQuery = navigator.permissions.query.bind(navigator.permissions);
      navigator.permissions.query = function(descriptor) {
        if (descriptor && descriptor.name === 'notifications') {
          return Promise.resolve({ state: Notification.permission });
        }
        return origPermQuery(descriptor);
      };
    }
  } catch(e) {}

  // ========== 5. 修补 plugins / languages 指纹（更接近真实浏览器） ==========
  try {
    if (navigator.plugins && navigator.plugins.length === 0) {
      Object.defineProperty(navigator, 'plugins', {
        get: function() {
          // 返回空数组（headless 默认），避免被识别
          return [];
        },
        configurable: true
      });
    }
    if (!navigator.languages || navigator.languages.length === 0) {
      Object.defineProperty(navigator, 'languages', {
        get: function() { return ['zh-CN', 'zh', 'en']; },
        configurable: true
      });
    }
  } catch(e) {}

  // ========== 6. 反 debugger 无限循环（关键） ==========
  // 不要覆盖 window.Function / Function.prototype.toString
  // 覆盖这些会破坏页面 polyfill 检测（如 Function.prototype.bind）
  // 真正的反 debugger 通过 setInterval/setTimeout 拦截器实现

  // ========== 7. 阻止 setInterval/fn 注入的 debugger ==========
  // 只针对反调试常见的模式：setInterval 带 debugger 字符串
  try {
    if (!window.__antiDebugIntervalInstalled) {
      var _origSetInterval = window.setInterval;
      var safeSetInterval = function(fn, delay) {
        // 仅当参数是字符串且包含 debugger 时拦截
        if (typeof fn === 'string' && /\bdebugger\b/i.test(fn)) {
          return 0;
        }
        // 仅当 delay 极小（< 16ms）且函数 toString 包含 debugger 时拦截
        if (typeof fn === 'function' && delay !== undefined && delay < 16) {
          try {
            var src = String(fn);
            if (/\bdebugger\b/.test(src)) {
              return 0;
            }
          } catch(e) {}
        }
        return _origSetInterval.apply(window, arguments);
      };
      window.setInterval = safeSetInterval;
      window.__antiDebugIntervalInstalled = true;
    }
  } catch(e) {}

  // ========== 8. 阻止 setTimeout 注入的 debugger ==========
  try {
    if (!window.__antiDebugTimeoutInstalled) {
      var _origSetTimeout = window.setTimeout;
      var safeSetTimeout = function(fn, delay) {
        if (typeof fn === 'string' && /\bdebugger\b/i.test(fn)) {
          return 0;
        }
        if (typeof fn === 'function' && delay !== undefined && delay < 16) {
          try {
            var src = String(fn);
            if (/\bdebugger\b/.test(src)) {
              return 0;
            }
          } catch(e) {}
        }
        return _origSetTimeout.apply(window, arguments);
      };
      window.setTimeout = safeSetTimeout;
      window.__antiDebugTimeoutInstalled = true;
    }
  } catch(e) {}

  // ========== 9. 修补 outerWidth/outerHeight ==========
  // 不要在已经定义过的情况下重新定义
  try {
    if (window.outerWidth !== window.innerWidth) {
      Object.defineProperty(window, 'outerWidth', {
        get: function() { return window.innerWidth || 1920; },
        configurable: true
      });
    }
    if (window.outerHeight !== window.innerHeight) {
      Object.defineProperty(window, 'outerHeight', {
        get: function() { return window.innerHeight || 1080; },
        configurable: true
      });
    }
  } catch(e) {}

  // ========== 10. 修补 document.hidden（用 getOwnPropertyDescriptor 检测） ==========
  try {
    var _origHiddenGetter = Object.getOwnPropertyDescriptor(Document.prototype, 'hidden');
    // 不主动覆盖 hidden，因为很多网站依赖它
  } catch(e) {}

  // ========== 11. 修补 iframe contentWindow 的 webdriver 属性 ==========
  try {
    var origCreateElement = document.createElement.bind(document);
    document.createElement = function(tag) {
      var el = origCreateElement(tag);
      if (tag && tag.toLowerCase() === 'iframe') {
        try {
          Object.defineProperty(el, 'contentWindow', {
            get: function() {
              var win = el.__proto__.contentWindow;
              if (win && win.navigator) {
                try {
                  Object.defineProperty(win.navigator, 'webdriver', {
                    get: function() { return undefined; },
                    configurable: true
                  });
                } catch(e) {}
              }
              return win;
            },
            configurable: true
          });
        } catch(e) {}
      }
      return el;
    };
  } catch(e) {}

  // ========== 12. 修补 console 防止通过 console.log 检测 ==========
  // 跳过：覆盖 console 会导致调试困难，且不解决核心问题
})();
"""

    @staticmethod
    def _find_input_element(page, selector=None):
        """多策略定位输入框元素"""
        if selector:
            try:
                loc = page.locator(selector)
                if loc.count() > 0:
                    return loc.first
            except Exception:
                pass
        try:
            loc = page.locator('input[placeholder]:not([type="hidden"]):visible, textarea[placeholder]:visible')
            for i in range(loc.count()):
                el = loc.nth(i)
                if el.is_visible():
                    return el
        except Exception:
            pass
        try:
            loc = page.get_by_role('textbox')
            if loc.count() > 0:
                return loc.first
        except Exception:
            pass
        try:
            loc = page.locator('input:not([type="hidden"]):visible, textarea:visible, [contenteditable="true"]:visible')
            if loc.count() > 0:
                return loc.first
        except Exception:
            pass
        try:
            loc = page.locator('input:not([type="hidden"]), textarea, [contenteditable="true"]')
            if loc.count() > 0:
                return loc.first
        except Exception:
            pass
        return None

    @staticmethod
    def _find_button_element(page, selector=None):
        """多策略定位发送/提交按钮"""
        if selector:
            try:
                loc = page.locator(selector)
                if loc.count() > 0:
                    return loc.first
            except Exception:
                pass
        try:
            loc = page.get_by_role('button')
            for i in range(loc.count()):
                el = loc.nth(i)
                if el.is_visible():
                    text = (el.text_content() or '').strip()
                    if text:
                        return el
        except Exception:
            pass
        try:
            loc = page.get_by_role('link')
            for i in range(loc.count()):
                el = loc.nth(i)
                if el.is_visible() and (el.get_attribute('onclick') or el.get_attribute('href')):
                    return el
        except Exception:
            pass
        try:
            loc = page.locator('button:visible, [role="button"]:visible, input[type="submit"]:visible, input[type="button"]:visible, a[onclick]:visible')
            if loc.count() > 0:
                return loc.first
        except Exception:
            pass
        try:
            loc = page.locator('button, [role="button"], input[type="submit"], input[type="button"]')
            if loc.count() > 0:
                return loc.first
        except Exception:
            pass
        return None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True

        self.config = DanmakuOutputConfig()
        self.status = DanmakuOutputStatus()
        self.buffer = DanmakuBuffer()
        
        # 尝试加载保存的配置
        saved_config = config_manager.load_config('output_config')
        if saved_config:
            try:
                self.config.update(saved_config)
            except Exception as e:
                print(f"[OutputManager] 加载配置失败，使用默认配置: {e}")

        self._command_queue = queue.Queue()
        self._result_queue = queue.Queue()
        self._playwright_thread: Optional[threading.Thread] = None
        self._playwright_running = False
        self._stop_event = threading.Event()

        # 异步命令等待机制（替代原 result_queue 轮询）
        # 使用 Future 为每个命令提供独立的等待通道，避免 cmd_id 冲突和结果错配
        self._command_futures: dict = {}
        self._command_lock = threading.Lock()
        self._playwright_ready = threading.Event()
        self._first_command = True

        self._output_thread: Optional[threading.Thread] = None
        self._output_stop_event = threading.Event()

        # 浏览器输出独立控制（新增）
        self._browser_output_thread: Optional[threading.Thread] = None
        self._browser_stop_event = threading.Event()
        self.browser_status = BrowserOutputStatus()

        # 文件输出独立控制（新增）
        self._file_output_thread: Optional[threading.Thread] = None
        self._file_stop_event = threading.Event()
        self.file_status = FileOutputStatus()

        self._lock = threading.Lock()
        self._broadcast_callback: Optional[Callable] = None

        self._picker_active: bool = False
        self._send_logs: deque = deque(maxlen=50)
        self._last_sent_timestamp: Optional[str] = None

    def set_broadcast_callback(self, callback: Callable):
        self._broadcast_callback = callback

    def _broadcast(self, event_type: str, data: dict):
        if self._broadcast_callback:
            try:
                self._broadcast_callback({
                    'message_type': event_type,
                    'data': data,
                    'timestamp': datetime.now().isoformat()
                })
            except Exception:
                pass

    def _on_page_error(self, exc):
        """页面 JS 错误回调：记录但不中断流程"""
        try:
            err_msg = str(exc)
            if hasattr(self, '_page_errors'):
                self._page_errors.append(err_msg)
                # 最多保留 20 条
                if len(self._page_errors) > 20:
                    self._page_errors = self._page_errors[-20:]
            # 关键错误打印日志
            if 'Function.prototype.bind' in err_msg or 'incompatible' in err_msg:
                print(f'[Playwright] 页面关键错误: {err_msg[:200]}')
        except Exception:
            pass

    def _on_console(self, msg):
        """控制台消息回调：只记录错误和警告"""
        try:
            msg_type = msg.type if hasattr(msg, 'type') else 'log'
            if msg_type in ('error', 'warning'):
                text = msg.text if hasattr(msg, 'text') else str(msg)
                # 静默某些已知的噪音错误
                if 'Failed to load resource' in text:
                    return
                if 'favicon.ico' in text:
                    return
                if msg_type == 'error':
                    print(f'[Playwright Console Error] {text[:300]}')
                elif msg_type == 'warning':
                    print(f'[Playwright Console Warning] {text[:200]}')
        except Exception:
            pass

    def _emit_status(self):
        self._broadcast('output_status', self.status.to_dict())

    def push_danmaku(self, message: dict):
        self.buffer.push(message)

    def _start_playwright_thread(self):
        if self._playwright_thread and self._playwright_thread.is_alive():
            return
        self._stop_event.clear()
        self._playwright_running = True
        self._playwright_thread = threading.Thread(target=self._playwright_thread_loop, daemon=True)
        self._playwright_thread.start()

    def _stop_playwright_thread(self):
        if not self._playwright_running:
            return
        self._stop_event.set()
        # 更短的超时时间，快速返回
        if self._playwright_thread:
            self._playwright_thread.join(timeout=3.0)
        self._playwright_running = False
        self.status.browser_connected = False

    def _playwright_thread_loop(self):
        playwright = None
        browser = None
        page = None

        try:
            # 通知主线程：Playwright 即将启动（首次冷启动较慢）
            self._broadcast('playwright_progress', {
                'phase': 'initializing',
                'message': '正在初始化 Playwright...'
            })

            playwright = sync_playwright().start()

            self._broadcast('playwright_progress', {
                'phase': 'launching',
                'message': '正在启动浏览器...'
            })

            # 尝试多种浏览器启动方式，提高兼容性
            browser = None
            launch_options = {
                'headless': self.config.browser_headless,
                'args': [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--disable-dev-shm-usage',
                    '--no-first-run',
                    '--no-default-browser-check',
                ]
            }

            # 1. 首先尝试系统 Chrome/Edge（使用 channel）
            for channel in ['chrome', 'msedge']:
                try:
                    self._broadcast('playwright_progress', {
                        'phase': 'launching',
                        'message': f'正在尝试使用系统 {channel} 浏览器...'
                    })
                    browser = playwright.chromium.launch(
                        channel=channel,
                        **launch_options
                    )
                    print(f'[Playwright] Successfully launched using {channel}')
                    break
                except Exception as e:
                    print(f'[Playwright] Failed to launch {channel}: {e}')
                    continue

            # 2. 如果系统浏览器失败，尝试 Playwright 自带浏览器
            if browser is None:
                try:
                    self._broadcast('playwright_progress', {
                        'phase': 'launching',
                        'message': '正在使用 Playwright 浏览器...'
                    })
                    browser = playwright.chromium.launch(**launch_options)
                    print('[Playwright] Successfully launched using Playwright Chromium')
                except Exception as e:
                    print(f'[Playwright] Failed to launch Playwright Chromium: {e}')
                    # 最后尝试：给用户更明确的错误提示
                    raise Exception(
                        f'无法启动浏览器！请运行 "python -m playwright install chromium" 安装浏览器，'
                        f'或确保电脑已安装 Chrome/Edge 浏览器。\n错误: {str(e)}'
                    )

            # 全局页面错误收集器：用于记录页面 JS 错误但不中断流程
            self._page_errors = []

            # 通知主线程：Playwright 已就绪
            self._playwright_ready.set()
            self._broadcast('playwright_progress', {
                'phase': 'browser_ready',
                'message': '浏览器已启动，等待命令...'
            })

            while not self._stop_event.is_set():
                try:
                    try:
                        command = self._command_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue

                    cmd_type = command.get('type')
                    cmd_id = command.get('id')
                    result = {'id': cmd_id, 'success': False, 'error': None, 'data': None}

                    try:
                        if cmd_type == 'open_website':
                            url = command.get('url')
                            self._broadcast('playwright_progress', {
                                'phase': 'navigating',
                                'message': f'正在打开: {url}'
                            })
                            if page:
                                try:
                                    page.close()
                                except Exception:
                                    pass
                            context = browser.new_context(
                                no_viewport=True,
                                locale='zh-CN',
                                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                                permissions=['geolocation'],
                                ignore_https_errors=True,
                            )
                            # 反反调试：在页面加载前注入，防止网站检测调试工具
                            try:
                                context.add_init_script(self.ANTI_DEBUG_SCRIPT)
                            except Exception:
                                pass
                            page = context.new_page()

                            # 注册页面错误监听（关键：捕获 JS 错误但不中断流程）
                            self._page_errors = []
                            page.on('pageerror', lambda exc: self._on_page_error(exc))
                            page.on('console', lambda msg: self._on_console(msg))

                            # 增加更多的反自动化措施（轻量级）
                            try:
                                page.evaluate("""() => {
                                    try {
                                        if (navigator.webdriver !== undefined) {
                                            Object.defineProperty(navigator, 'webdriver', {get: () => undefined, configurable: true});
                                        }
                                    } catch(e) {}
                                }""")
                            except Exception:
                                pass

                            # 关键修复：放宽 page.goto 超时至 60 秒，并增加 domcontentloaded 重试
                            # 使用 'load' 而不是 'networkidle'，因为很多网站有持续的网络连接
                            # （WebSocket、长轮询），networkidle 永远不触发
                            goto_success = False
                            try:
                                page.goto(url, wait_until='load', timeout=60000)
                                goto_success = True
                            except Exception as goto_err:
                                # 如果 load 失败，尝试 domcontentloaded
                                try:
                                    page.goto(url, wait_until='domcontentloaded', timeout=45000)
                                    goto_success = True
                                except Exception:
                                    # 二次重试 domcontentloaded 一次
                                    try:
                                        page.goto(url, wait_until='domcontentloaded', timeout=30000)
                                        goto_success = True
                                    except Exception as final_err:
                                        raise Exception(f'页面加载失败（重试 3 次后仍失败）: {final_err}')

                            if not goto_success:
                                raise Exception('页面加载失败')

                            # 等待主要内容加载（最多 8 秒）
                            try:
                                page.wait_for_function(
                                    "() => document.body && document.body.children.length > 0",
                                    timeout=8000
                                )
                            except Exception:
                                pass

                            # 额外等待 1.5 秒让 React/Vue 等框架完成挂载
                            try:
                                page.wait_for_timeout(1500)
                            except Exception:
                                pass

                            # 注入窗口尺寸变化监听脚本
                            try:
                                page.evaluate(RESIZE_MONITOR_JS)
                            except Exception:
                                pass

                            self.status.browser_connected = True
                            self.status.status_message = f'已连接到: {url}'

                            # 收集页面诊断信息
                            page_diagnostics = {
                                'message': f'已打开: {url}',
                                'page_title': '',
                                'page_url': page.url,
                                'page_errors': list(self._page_errors),
                                'content_loaded': False,
                            }
                            try:
                                page_diagnostics['page_title'] = page.title()
                            except Exception:
                                pass
                            try:
                                body_children = page.evaluate("() => document.body ? document.body.children.length : 0")
                                page_diagnostics['content_loaded'] = body_children > 0
                                page_diagnostics['body_children'] = body_children
                            except Exception:
                                pass

                            result['success'] = True
                            result['data'] = page_diagnostics
                            self._emit_status()

                            self._broadcast('playwright_progress', {
                                'phase': 'page_ready',
                                'message': f'页面已就绪: {url}'
                            })

                        elif cmd_type == 'send_text':
                            text = command.get('text')
                            textarea_selector = command.get('textarea_selector')
                            button_selector = command.get('button_selector')
                            auto_click = command.get('auto_click', False)
                            auto_enter = command.get('auto_enter', False)

                            if not page:
                                raise Exception('浏览器未连接')

                            # 多策略定位输入框
                            input_el = self._find_input_element(page, textarea_selector)
                            if input_el is None:
                                raise Exception(
                                    '未找到可用的输入区域（已尝试：选择器、placeholder、role=textbox、通用输入框）'
                                )

                            # 确保元素在视口内可见
                            try:
                                input_el.scroll_into_view_if_needed(timeout=3000)
                            except Exception:
                                pass

                            input_el.fill(text)

                            # 多策略定位发送/提交按钮
                            if auto_click:
                                button_el = self._find_button_element(page, button_selector)
                                if button_el:
                                    try:
                                        button_el.scroll_into_view_if_needed(timeout=3000)
                                    except Exception:
                                        pass
                                    time.sleep(0.3)
                                    button_el.click()

                            if auto_enter:
                                time.sleep(0.2)
                                input_el.press('Enter')

                            result['success'] = True
                            result['data'] = {'count': 1}

                        elif cmd_type == 'start_picker':
                            if not page:
                                raise Exception('浏览器未连接')
                            eval_result = page.evaluate(PICKER_JS)
                            if eval_result == 'already_active':
                                result['success'] = True
                                result['data'] = {'message': '拾取模式已在运行中'}
                            else:
                                result['success'] = True
                                result['data'] = {'message': '元素拾取模式已启动，请在目标页面中点击选择元素'}

                        elif cmd_type == 'stop_picker':
                            if not page:
                                raise Exception('浏览器未连接')
                            page.evaluate(PICKER_CLEANUP_JS)
                            result['success'] = True
                            result['data'] = {'message': '元素拾取模式已停止'}

                        elif cmd_type == 'get_picker_result':
                            if not page:
                                raise Exception('浏览器未连接')
                            eval_result = page.evaluate(PICKER_RESULT_JS)
                            result['success'] = True
                            result['data'] = {'result': eval_result}

                        elif cmd_type == 'resize_viewport':
                            width = command.get('width', 1280)
                            height = command.get('height', 720)
                            if not page:
                                raise Exception('浏览器未连接')
                            try:
                                # 优先通过 CDP 调整浏览器窗口大小，保持自适应模式
                                cdp = page.context.browser.new_browser_cdp_session()
                                targets = cdp.send('Target.getTargets')
                                target_id = None
                                for t in targets.get('targetInfos', []):
                                    if t.get('type') == 'page' and t.get('attached'):
                                        target_id = t.get('targetId')
                                        break
                                if target_id:
                                    window_result = cdp.send('Browser.getWindowForTarget', {'targetId': target_id})
                                    window_id = window_result['windowId']
                                    cdp.send('Browser.setWindowBounds', {
                                        'windowId': window_id,
                                        'bounds': {'width': width, 'height': height}
                                    })
                                else:
                                    page.set_viewport_size({'width': width, 'height': height})
                                try:
                                    cdp.detach()
                                except Exception:
                                    pass
                            except Exception:
                                # CDP 失败时回退到 set_viewport_size
                                page.set_viewport_size({'width': width, 'height': height})
                            result['success'] = True
                            result['data'] = {'width': width, 'height': height}

                        elif cmd_type == 'get_viewport_info':
                            if not page:
                                raise Exception('浏览器未连接')
                            vp = page.viewport_size
                            # no_viewport=True 时 viewport_size 为 None，从页面获取实际尺寸
                            if vp is None:
                                try:
                                    vp = page.evaluate("() => ({width: window.innerWidth, height: window.innerHeight})")
                                except Exception:
                                    vp = {'width': 0, 'height': 0}
                            # 尝试获取页面实际窗口尺寸
                            try:
                                resize_info = page.evaluate("() => window.__danmakuLastResize || null")
                            except Exception:
                                resize_info = None
                            result['success'] = True
                            result['data'] = {
                                'viewport': vp,
                                'page_resize': resize_info,
                                'auto_resize': page.viewport_size is None
                            }

                        elif cmd_type == 'close':
                            # 立即返回成功结果，然后再清理资源
                            result['success'] = True
                            with self._command_lock:
                                future = self._command_futures.pop(cmd_id, None)
                            if future is not None and not future.done():
                                future.set_result(result)
                            # 直接 break 循环，让 finally 块处理资源清理
                            break

                    except Exception as e:
                        result['error'] = str(e)
                        self._broadcast('playwright_progress', {
                            'phase': 'error',
                            'message': str(e)
                        })

                    # 通过 Future 返回结果（替代原来的 result_queue.put）
                    with self._command_lock:
                        future = self._command_futures.pop(cmd_id, None)

                    if future is not None and not future.done():
                        future.set_result(result)
                    else:
                        # 兜底：放回旧队列（兼容遗留调用方）
                        try:
                            self._result_queue.put(result)
                        except Exception:
                            pass

                except Exception as e:
                    print(f'Playwright线程错误: {e}')

        except Exception as e:
            print(f'Playwright初始化失败: {e}')
            # 关键：通知主线程启动失败，避免永久阻塞
            self._playwright_ready.set()
            self._broadcast('playwright_progress', {
                'phase': 'init_failed',
                'message': f'Playwright 初始化失败: {e}'
            })
            # 唤醒所有等待的 future
            with self._command_lock:
                for fid, fut in list(self._command_futures.items()):
                    if not fut.done():
                        fut.set_result({
                            'id': fid,
                            'success': False,
                            'error': f'Playwright 初始化失败: {e}',
                            'data': None
                        })
                self._command_futures.clear()
        finally:
            # 快速清理资源，每个操作都有超时保护
            import threading
            
            def close_with_timeout(obj, method_name, timeout=2.0):
                """带超时的资源清理"""
                if not obj:
                    return
                done = threading.Event()
                
                def _close():
                    try:
                        getattr(obj, method_name)()
                    except Exception:
                        pass
                    finally:
                        done.set()
                
                t = threading.Thread(target=_close, daemon=True)
                t.start()
                done.wait(timeout=timeout)
            
            # 按顺序清理，每个操作最多等待 2 秒
            close_with_timeout(page, 'close', 2.0)
            close_with_timeout(browser, 'close', 2.0)
            close_with_timeout(playwright, 'stop', 2.0)
            
            self.status.browser_connected = False
            self._playwright_running = False
            self._playwright_ready.clear()
            self._first_command = True

    def _send_command(self, cmd_type: str, timeout: float = None, **kwargs) -> dict:
        """
        发送命令到 Playwright 线程并等待结果。

        关键改进（修复打包版"命令执行超时"问题）：
        - 首次命令（冷启动）默认超时 90 秒（原 30 秒），足够覆盖 Chromium 冷启动
        - 后续命令 30 秒超时
        - 使用 UUID 唯一 ID 替代 time.time() 避免冲突
        - 使用 Future 机制替代 result_queue 轮询，避免结果错配
        - 等待 Playwright 线程就绪事件，避免 race condition
        """
        if not self._playwright_running:
            self._start_playwright_thread()

        # 首次冷启动需等待 Playwright 线程就绪
        is_first = self._first_command
        if is_first:
            # 等待 Playwright 启动完成（带超时 60 秒）
            ready = self._playwright_ready.wait(timeout=60.0)
            if not ready:
                return {
                    'success': False,
                    'error': 'Playwright 启动超时（60秒）',
                    'data': None,
                    'id': None
                }
            # 注意：_first_command 在 Playwright 线程初始化成功后已经准备好
            # 但在 _send_command 这里我们只需关心"是否首次"来决定超时

        # 生成唯一 ID（UUID 替代 time.time() 避免冲突）
        cmd_id = str(uuid.uuid4())
        future = concurrent.futures.Future()

        with self._command_lock:
            self._command_futures[cmd_id] = future

        self._command_queue.put({
            'type': cmd_type,
            'id': cmd_id,
            **kwargs
        })

        # 自适应超时：首次 90 秒，后续 30 秒
        if timeout is None:
            timeout = 90.0 if is_first else 30.0

        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            # 清理残留 future
            with self._command_lock:
                self._command_futures.pop(cmd_id, None)
            return {
                'success': False,
                'error': f'命令执行超时（{timeout:.0f}秒）',
                'data': None,
                'id': cmd_id
            }
        except Exception as e:
            with self._command_lock:
                self._command_futures.pop(cmd_id, None)
            return {
                'success': False,
                'error': f'命令异常: {e}',
                'data': None,
                'id': cmd_id
            }
        finally:
            # 首次命令已完成，更新标志
            if is_first:
                self._first_command = False

    def _format_single_message(self, msg: dict) -> str:
        data = msg.get('data', {})
        msg_type = msg.get('message_type', '')
        timestamp = msg.get('timestamp', '')

        # 获取时间前缀
        time_prefix = ''
        if self.config.include_timestamp and timestamp:
            try:
                dt = datetime.fromisoformat(timestamp)
                time_prefix = dt.strftime('%H:%M:%S ')
            except (ValueError, TypeError):
                time_prefix = ''

        # 获取用户名部分和内容
        username_prefix = ''
        content = ''

        if self.config.include_username:
            if msg_type == 'WebcastChatMessage':
                username_prefix = f"{data.get('user_name', '')}："
                content = f"{data.get('content', '')}"
            elif msg_type == 'WebcastEmojiChatMessage':
                username_prefix = f"{data.get('user_name', '')}："
                content = f"[表情] {data.get('default_content', '')}"
            elif msg_type == 'WebcastGiftMessage':
                username_prefix = f"{data.get('user_name', '')} "
                content = f"送出 {data.get('gift_name', '')} x{data.get('gift_count', 1)}"
            elif msg_type == 'WebcastLikeMessage':
                username_prefix = f"{data.get('user_name', '')} "
                content = f"点了{data.get('count', 0)}个赞"
            elif msg_type == 'WebcastMemberMessage':
                username_prefix = f"{data.get('user_name', '')} "
                content = f"进入了直播间"
            elif msg_type == 'WebcastSocialMessage':
                username_prefix = f"{data.get('user_name', '')} "
                content = f"关注了主播"
            elif msg_type == 'WebcastFansclubMessage':
                content = f"[粉丝团] {data.get('content', '')}"
            elif msg_type == 'WebcastRoomUserSeqMessage':
                content = f"[统计] 当前观看: {data.get('current_viewers', 0)}, 累计: {data.get('total_viewers', 0)}"
            else:
                content = f"[{msg_type}] {data}"
        else:
            if msg_type == 'WebcastChatMessage':
                content = f"{data.get('content', '')}"
            elif msg_type == 'WebcastEmojiChatMessage':
                content = f"[表情] {data.get('default_content', '')}"
            elif msg_type == 'WebcastGiftMessage':
                content = f"[礼物] 送出 {data.get('gift_name', '')} x{data.get('gift_count', 1)}"
            elif msg_type == 'WebcastLikeMessage':
                content = f"[点赞] 点了{data.get('count', 0)}个赞"
            elif msg_type == 'WebcastMemberMessage':
                content = f"[进场] 进入了直播间"
            elif msg_type == 'WebcastSocialMessage':
                content = f"[关注] 关注了主播"
            elif msg_type == 'WebcastFansclubMessage':
                content = f"[粉丝团] {data.get('content', '')}"
            elif msg_type == 'WebcastRoomUserSeqMessage':
                content = f"[统计] 当前观看: {data.get('current_viewers', 0)}, 累计: {data.get('total_viewers', 0)}"
            else:
                content = f"[{msg_type}] {data}"

        return f"{time_prefix}{username_prefix}{content}"

    def _write_to_file(self, text: str):
        if not self.config.file_output_path:
            return
        
        # 检查是否已停止
        if self._output_stop_event.is_set():
            return
        
        try:
            os.makedirs(os.path.dirname(self.config.file_output_path) or '.', exist_ok=True)
            mode = 'a' if self.config.file_append_mode else 'w'
            with open(self.config.file_output_path, mode, encoding='utf-8') as f:
                f.write(text)
                if self.config.add_newline:
                    f.write('\n')
        except Exception as e:
            self.status.last_error = f'文件写入失败: {e}'
            raise e

    def _output_thread_loop(self):
        while not self._output_stop_event.is_set():
            try:
                if self.config.output_mode == 'browser':
                    self._process_browser_output()
                else:
                    self._process_file_output()

                # 使用可中断的等待
                if self._output_stop_event.wait(timeout=self.config.send_interval):
                    break
            except Exception as e:
                self.status.last_error = str(e)
                self._add_log(str(e)[:50], False, str(e))
                self._emit_status()
                if self._output_stop_event.wait(timeout=1.0):
                    break

    def _process_browser_output(self):
        # 首先检查是否已停止
        if self._output_stop_event.is_set():
            return
            
        messages = self.buffer.get_latest(since_timestamp=self._last_sent_timestamp)
        if not messages:
            return
        
        if self.config.send_mode == 'sequential':
            for msg in messages:
                # 每次处理前都检查是否已停止
                if self._output_stop_event.is_set():
                    break
                text = self._format_single_message(msg)
                self._send_to_browser(text)
                self._last_sent_timestamp = msg.get('timestamp')
                self.status.total_sent += 1
                self._add_log(text[:50], True)
                self.status.last_execution_time = datetime.now().isoformat()
                # 再次检查是否已停止
                if self._output_stop_event.is_set():
                    break
                # 使用可中断的等待
                if self._output_stop_event.wait(timeout=self.config.send_interval):
                    break
        else:
            # 批量发送前先检查是否已停止
            if self._output_stop_event.is_set():
                return
            texts = [self._format_single_message(msg) for msg in messages]
            combined_text = '\n'.join(texts)
            self._send_to_browser(combined_text)
            self._last_sent_timestamp = messages[-1].get('timestamp') if messages else None
            self.status.total_sent += len(messages)
            self._add_log(f'批量发送 {len(messages)} 条', True)
            self.status.last_execution_time = datetime.now().isoformat()
        
        self.status.status_message = f'已发送 {self.status.total_sent} 条'
        self._emit_status()

    def _process_file_output(self):
        # 首先检查是否已停止
        if self._output_stop_event.is_set():
            return
            
        messages = self.buffer.get_latest(since_timestamp=self._last_sent_timestamp)
        if not messages:
            return
        
        if self.config.send_mode == 'sequential':
            for msg in messages:
                # 每次处理前都检查是否已停止
                if self._output_stop_event.is_set():
                    break
                text = self._format_single_message(msg)
                self._write_to_file(text)
                self._last_sent_timestamp = msg.get('timestamp')
                self.status.total_sent += 1
                self._add_log(text[:50], True)
                self.status.last_execution_time = datetime.now().isoformat()
                # 再次检查是否已停止
                if self._output_stop_event.is_set():
                    break
                # 使用可中断的等待
                if self._output_stop_event.wait(timeout=self.config.send_interval):
                    break
        else:
            # 批量写入前先检查是否已停止
            if self._output_stop_event.is_set():
                return
            texts = [self._format_single_message(msg) for msg in messages]
            for text in texts:
                # 每次写入前检查是否已停止
                if self._output_stop_event.is_set():
                    break
                self._write_to_file(text)
            self._last_sent_timestamp = messages[-1].get('timestamp') if messages else None
            self.status.total_sent += len(messages)
            self._add_log(f'批量写入 {len(messages)} 条', True)
            self.status.last_execution_time = datetime.now().isoformat()
        
        self.status.status_message = f'已写入 {self.status.total_sent} 条'
        self._emit_status()

    def _send_to_browser(self, text: str):
        # 检查是否已停止
        if self._output_stop_event.is_set():
            return

        if not self.config.textarea_selector:
            raise Exception('未配置文本区域选择器')

        # 尝试主选择器，如果失败则尝试备选
        selectors_to_try = [self.config.textarea_selector]
        if self.config.textarea_selectors:
            for alt in self.config.textarea_selectors:
                if alt and alt != self.config.textarea_selector and alt not in selectors_to_try:
                    selectors_to_try.append(alt)

        last_error = None
        for sel in selectors_to_try:
            try:
                result = self._send_command(
                    'send_text',
                    text=text,
                    textarea_selector=sel,
                    button_selector=self.config.button_selector,
                    auto_click=self.config.auto_click_button,
                    auto_enter=self.config.auto_press_enter
                )
                if result['success']:
                    return
                last_error = result.get('error', '发送失败')
            except Exception as e:
                last_error = str(e)
                continue

        raise Exception(last_error or '所有选择器均无法定位输入区域，请重新拾取')

    def _add_log(self, content: str, success: bool, error: str = None):
        entry = {
            'timestamp': datetime.now().isoformat(),
            'content': content[:100],
            'success': success,
            'error': error
        }
        self._send_logs.append(entry)
        self._broadcast('output_sent' if success else 'output_error', entry)

    def _should_output_message(self, message: dict) -> bool:
        """
        判断消息是否应该被输出。
        检查条件：
        1. 消息类型应在可输出白名单中（过滤系统日志）
        2. 通过过滤引擎检查（消息类型、关键词、正则、用户等级）
        """
        msg_type = message.get('message_type', '')

        # 过滤系统内部消息（无论如何都不输出）
        if msg_type in SYSTEM_MESSAGE_TYPES:
            return False

        # 消息类型必须在可输出白名单中
        if msg_type not in OUTPUTTABLE_MESSAGE_TYPES:
            return False

        # 通过过滤引擎检查
        allowed, _ = filter_engine.should_allow(message)
        if not allowed:
            return False

        return True

    def start(self) -> bool:
        with self._lock:
            if self.status.running:
                return True

            if self.config.output_mode == 'browser':
                if not self.config.target_url:
                    self.status.last_error = '未配置目标网站URL'
                    self._emit_status()
                    return False
                if not self.config.textarea_selector:
                    self.status.last_error = '未配置文本区域选择器'
                    self._emit_status()
                    return False
                if not self.status.browser_connected:
                    self.status.last_error = '请先连接浏览器'
                    self._emit_status()
                    return False
            else:
                if not self.config.file_output_path:
                    self.status.last_error = '未配置文件输出路径'
                    self._emit_status()
                    return False

            self._output_stop_event.clear()
            self.status.running = True
            self.status.last_error = None
            self.status.total_sent = 0
            self.status.status_message = '正在运行...'
            self._output_thread = threading.Thread(target=self._output_thread_loop, daemon=True)
            self._output_thread.start()
            self._emit_status()
            return True

    def stop(self):
        with self._lock:
            if not self.status.running:
                return
            
            self._output_stop_event.set()
            self.status.running = False
            self.status.status_message = '正在停止...'
            self._emit_status()
        
        # 等待线程完全结束
        if self._output_thread and self._output_thread.is_alive():
            self._output_thread.join(timeout=5.0)
        
        with self._lock:
            self.status.status_message = '已停止'
            self._emit_status()

    # ========== 浏览器输出独立控制 ==========

    def start_browser_output(self) -> bool:
        """启动浏览器输出"""
        with self._lock:
            if self.browser_status.running:
                return True

            if not self.config.target_url:
                self.browser_status.last_error = '未配置目标网站URL'
                self._emit_status()
                return False
            if not self.config.textarea_selector:
                self.browser_status.last_error = '未配置文本区域选择器'
                self._emit_status()
                return False
            if not self.status.browser_connected:
                self.browser_status.last_error = '请先连接浏览器'
                self._emit_status()
                return False

            self._browser_stop_event.clear()
            self.browser_status.running = True
            self.browser_status.last_error = None
            self.browser_status.total_sent = 0
            self.browser_status.status_message = '正在运行...'
            self._last_sent_timestamp = None  # 重置时间戳，从最新开始
            self._browser_output_thread = threading.Thread(
                target=self._browser_output_thread_loop, daemon=True
            )
            self._browser_output_thread.start()
            self._emit_status()
            return True

    def stop_browser_output(self):
        """停止浏览器输出"""
        with self._lock:
            if not self.browser_status.running:
                return
            self._browser_stop_event.set()
            self.browser_status.running = False
            self.browser_status.status_message = '正在停止...'
            self._emit_status()

        if self._browser_output_thread and self._browser_output_thread.is_alive():
            self._browser_output_thread.join(timeout=5.0)

        with self._lock:
            self.browser_status.status_message = '已停止'
            self._emit_status()

    # ========== 文件输出独立控制 ==========

    def start_file_output(self) -> bool:
        """启动文件输出"""
        with self._lock:
            if self.file_status.running:
                return True

            if not self.config.file_output_path:
                self.file_status.last_error = '未配置文件输出路径'
                self._emit_status()
                return False

            self._file_stop_event.clear()
            self.file_status.running = True
            self.file_status.last_error = None
            self.file_status.total_sent = 0
            self.file_status.status_message = '正在运行...'
            self._last_sent_timestamp = None
            self._file_output_thread = threading.Thread(
                target=self._file_output_thread_loop, daemon=True
            )
            self._file_output_thread.start()
            self._emit_status()
            return True

    def stop_file_output(self):
        """停止文件输出"""
        with self._lock:
            if not self.file_status.running:
                return
            self._file_stop_event.set()
            self.file_status.running = False
            self.file_status.status_message = '正在停止...'
            self._emit_status()

        if self._file_output_thread and self._file_output_thread.is_alive():
            self._file_output_thread.join(timeout=5.0)

        with self._lock:
            self.file_status.status_message = '已停止'
            self._emit_status()

    # ========== 独立线程循环 ==========

    def _browser_output_thread_loop(self):
        """浏览器输出线程循环（含断线检测）"""
        consecutive_errors = 0
        max_consecutive_errors = 3

        while not self._browser_stop_event.is_set():
            try:
                # 检查浏览器连接状态
                if not self.status.browser_connected:
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        self.browser_status.last_error = '浏览器连接已断开，请重新打开网站'
                        self._add_log('浏览器连接已断开', False, '浏览器连接已断开')
                        self._emit_status()
                        # 自动停止浏览器输出
                        self.browser_status.running = False
                        self.browser_status.status_message = '已停止（浏览器断开）'
                        self._broadcast('output_browser_disconnected', {
                            'message': '浏览器连接已断开，浏览器输出已自动停止'
                        })
                        self._emit_status()
                        break
                    # 等待重试
                    if self._browser_stop_event.wait(timeout=5.0):
                        break
                    continue

                self._process_output('browser')
                consecutive_errors = 0  # 成功后重置错误计数
                if self._browser_stop_event.wait(timeout=self.config.send_interval):
                    break
            except Exception as e:
                consecutive_errors += 1
                self.browser_status.last_error = str(e)
                self._add_log(str(e)[:50], False, str(e))
                self._emit_status()
                if self._browser_stop_event.wait(timeout=1.0):
                    break

    def _file_output_thread_loop(self):
        """文件输出线程循环"""
        while not self._file_stop_event.is_set():
            try:
                self._process_output('file')
                if self._file_stop_event.wait(timeout=self.config.send_interval):
                    break
            except Exception as e:
                self.file_status.last_error = str(e)
                self._add_log(str(e)[:50], False, str(e))
                self._emit_status()
                if self._file_stop_event.wait(timeout=1.0):
                    break

    def _process_output(self, mode: str):
        """统一的输出处理（浏览器或文件），包含过滤检查"""
        stop_event = self._browser_stop_event if mode == 'browser' else self._file_stop_event
        status = self.browser_status if mode == 'browser' else self.file_status

        if stop_event.is_set():
            return

        messages = self.buffer.get_latest(since_timestamp=self._last_sent_timestamp)
        if not messages:
            return

        if self.config.send_mode == 'sequential':
            for msg in messages:
                if stop_event.is_set():
                    break
                if not self._should_output_message(msg):
                    self._last_sent_timestamp = msg.get('timestamp')
                    continue

                text = self._format_single_message(msg)
                try:
                    if mode == 'browser':
                        self._send_to_browser(text)
                    else:
                        self._write_to_file(text)
                    self._last_sent_timestamp = msg.get('timestamp')
                    status.total_sent += 1
                    self._add_log(text[:50], True)
                    status.last_execution_time = datetime.now().isoformat()
                except Exception as e:
                    status.last_error = str(e)
                    self._add_log(str(e)[:50], False, str(e))

                if stop_event.is_set():
                    break
                if stop_event.wait(timeout=self.config.send_interval):
                    break
        else:
            if stop_event.is_set():
                return

            texts = []
            last_ts = None
            for msg in messages:
                if stop_event.is_set():
                    break
                if not self._should_output_message(msg):
                    last_ts = msg.get('timestamp')
                    continue
                text = self._format_single_message(msg)
                texts.append(text)
                last_ts = msg.get('timestamp')

            if not texts:
                return

            try:
                if mode == 'browser':
                    combined_text = "\n".join(texts)
                    self._send_to_browser(combined_text)
                else:
                    for t in texts:
                        if stop_event.is_set():
                            break
                        self._write_to_file(t)
                self._last_sent_timestamp = last_ts
                status.total_sent += len(texts)
                self._add_log(f'批量{"发送" if mode == "browser" else "写入"} {len(texts)} 条', True)
                status.last_execution_time = datetime.now().isoformat()
            except Exception as e:
                status.last_error = str(e)
                self._add_log(str(e)[:50], False, str(e))

        status.status_message = f'已{"发送" if mode == "browser" else "写入"} {status.total_sent} 条'
        self._emit_status()

    def update_config(self, config_data: dict):
        self.config.update(config_data)
        self._save_config()
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            config_dict = self.config.to_dict()
            config_manager.save_config('output_config', config_dict)
        except Exception as e:
            print(f"[OutputManager] 保存配置失败: {e}")

    def get_config(self) -> dict:
        return self.config.to_dict()

    def get_status(self) -> dict:
        return self.status.to_dict()

    def get_send_logs(self, count: int = 20) -> list:
        return list(self._send_logs)[-count:]

    def start_picker(self) -> dict:
        if not self.status.browser_connected:
            return {'success': False, 'error': '浏览器未连接，请先打开目标网站'}
        result = self._send_command('start_picker')
        if result['success']:
            self._picker_active = True
        return result

    def stop_picker(self) -> dict:
        if not self.status.browser_connected:
            return {'success': False, 'error': '浏览器未连接'}
        result = self._send_command('stop_picker')
        if result['success']:
            self._picker_active = False
        return result

    def get_picker_result(self) -> dict:
        if not self.status.browser_connected:
            return {'success': False, 'error': '浏览器未连接', 'active': False}
        result = self._send_command('get_picker_result')
        if result['success']:
            picker_result = result['data']['result']
            return {'success': True, 'active': self._picker_active, 'result': picker_result}
        return {'success': False, 'error': result.get('error', '获取结果失败'), 'active': False}

    def resize_viewport(self, width: int, height: int) -> dict:
        """动态调整 Playwright 浏览器窗口的 viewport 尺寸"""
        if not self.status.browser_connected:
            return {'success': False, 'error': '浏览器未连接'}
        return self._send_command('resize_viewport', width=width, height=height)

    def get_viewport_info(self) -> dict:
        """获取当前 viewport 信息"""
        if not self.status.browser_connected:
            return {'success': False, 'error': '浏览器未连接'}
        return self._send_command('get_viewport_info')

    def open_website(self, url: str = None) -> dict:
        target_url = url or self.config.target_url
        if not target_url:
            return {'success': False, 'error': '未提供目标网站URL'}
        if self._picker_active:
            self.stop_picker()
        result = self._send_command('open_website', url=target_url)
        if result['success']:
            if not url:
                self.config.target_url = target_url
        else:
            self.status.last_error = f'页面加载失败: {result.get("error", "")}'
            self._emit_status()
        return result

    def close_browser(self):
        """快速关闭浏览器，给用户即时反馈"""
        # 立即更新状态
        self.status.browser_connected = False
        self.status.status_message = '浏览器已关闭'
        self._emit_status()
        self._broadcast('playwright_progress', {
            'phase': 'closed',
            'message': '浏览器已关闭'
        })
        
        # 在后台发送关闭命令，不等待结果
        if self._playwright_running:
            # 直接设置停止事件，让线程快速退出
            self._stop_event.set()
            # 在后台线程中执行清理，避免阻塞
            import threading
            t = threading.Thread(target=self._stop_playwright_thread, daemon=True)
            t.start()
    
    def shutdown(self):
        """
        关闭输出管理器，清理所有资源
        """
        print("[DanmakuOutputManager] 正在关闭...")
        
        # 停止所有输出
        try:
            self.stop()
        except Exception as e:
            print(f"[DanmakuOutputManager] 停止主输出失败: {e}")
        
        try:
            self.stop_browser_output()
        except Exception as e:
            print(f"[DanmakuOutputManager] 停止浏览器输出失败: {e}")
        
        try:
            self.stop_file_output()
        except Exception as e:
            print(f"[DanmakuOutputManager] 停止文件输出失败: {e}")
        
        # 关闭浏览器
        try:
            if self._picker_active:
                self.stop_picker()
        except Exception as e:
            print(f"[DanmakuOutputManager] 停止拾取器失败: {e}")
        
        # 停止 Playwright 线程
        try:
            self._stop_playwright_thread()
        except Exception as e:
            print(f"[DanmakuOutputManager] 停止 Playwright 线程失败: {e}")
        
        # 关闭 buffer
        try:
            self.buffer.shutdown()
        except Exception as e:
            print(f"[DanmakuOutputManager] 关闭 buffer 失败: {e}")
        
        print("[DanmakuOutputManager] 已关闭")


output_manager = DanmakuOutputManager()
