// useDraggableDialog.js
// 给 Element Plus 的 <el-dialog> 启用 header 拖拽 + 边缘调整大小
// 使用方式：传入 el-dialog 的 ref 实例，在 dialog 的 @opened 事件中调用 initDraggable
//          可选传入 options：{ resizable, minWidth, minHeight, maxHeightRatio, maxWidthRatio }
import { onUnmounted, nextTick } from 'vue'

export function useDraggableDialog(dialogRef, options = {}) {
  const {
    resizable = false,
    minWidth = 320,
    minHeight = 220,
    // 弹窗允许占视口的最大高度比例（0-1），防止弹窗超出浏览器可视区域
    maxHeightRatio = 0.95,
    maxWidthRatio = 0.98
  } = options

  // ============= 事件处理器引用（统一管理 mouse + touch） =============
  let moveHandler = null
  let upHandler = null
  let mouseDownHandler = null
  let touchStartHandler = null
  let resizeMoveHandler = null
  let resizeUpHandler = null
  let resizeDownHandler = null
  let resizeTouchStartHandler = null
  let windowResizeHandler = null
  let currentDialogEl = null
  let currentHeader = null

  // ============= 统一坐标提取（兼容 mouse + touch） =============
  const getClientXY = (e) => {
    if (e.touches && e.touches.length > 0) {
      return { x: e.touches[0].clientX, y: e.touches[0].clientY }
    }
    if (e.changedTouches && e.changedTouches.length > 0) {
      return { x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY }
    }
    return { x: e.clientX, y: e.clientY }
  }

  // ============= 清理所有事件监听 =============
  const cleanup = () => {
    if (moveHandler) {
      document.removeEventListener('mousemove', moveHandler)
      document.removeEventListener('touchmove', moveHandler, { passive: false })
      moveHandler = null
    }
    if (upHandler) {
      document.removeEventListener('mouseup', upHandler)
      document.removeEventListener('touchend', upHandler)
      document.removeEventListener('touchcancel', upHandler)
      upHandler = null
    }
    if (resizeMoveHandler) {
      document.removeEventListener('mousemove', resizeMoveHandler)
      document.removeEventListener('touchmove', resizeMoveHandler, { passive: false })
      resizeMoveHandler = null
    }
    if (resizeUpHandler) {
      document.removeEventListener('mouseup', resizeUpHandler)
      document.removeEventListener('touchend', resizeUpHandler)
      document.removeEventListener('touchcancel', resizeUpHandler)
      resizeUpHandler = null
    }
    if (mouseDownHandler && currentHeader) {
      currentHeader.removeEventListener('mousedown', mouseDownHandler)
      mouseDownHandler = null
    }
    if (touchStartHandler && currentHeader) {
      currentHeader.removeEventListener('touchstart', touchStartHandler, { passive: false })
      touchStartHandler = null
    }
    if (resizeDownHandler && currentDialogEl) {
      currentDialogEl.removeEventListener('mousedown', resizeDownHandler)
      resizeDownHandler = null
    }
    if (resizeTouchStartHandler && currentDialogEl) {
      currentDialogEl.removeEventListener('touchstart', resizeTouchStartHandler, { passive: false })
      resizeTouchStartHandler = null
    }
    if (windowResizeHandler) {
      window.removeEventListener('resize', windowResizeHandler)
      windowResizeHandler = null
    }
    currentDialogEl = null
    currentHeader = null
  }

  // ============= 计算在视口内允许的最大宽高（防止超出浏览器可视区域） =============
  const computeMaxSize = () => {
    return {
      maxW: Math.floor(window.innerWidth * maxWidthRatio),
      maxH: Math.floor(window.innerHeight * maxHeightRatio)
    }
  }

  // ============= 根据 dialog 当前 top 位置动态更新 max-height =============
  // 确保底部不超出视口；始终用 getBoundingClientRect 获取真实 top，避免 CSS/inline style 不同步
  const updateMaxHeight = (dialogEl) => {
    const rect = dialogEl.getBoundingClientRect()
    const currentTop = rect.top
    const vh = window.innerHeight
    const maxH = vh - currentTop - 10 // 留 10px 底部余量
    dialogEl.style.maxHeight = Math.max(minHeight, maxH) + 'px'
  }

  // ============= 拖拽期间禁用 transition，保证跟随鼠标/手指的响应性 =============
  const setTransition = (dialogEl, on) => {
    dialogEl.style.transition = on ? '' : 'none'
  }

  // ============= 首次拖拽/调整时切换为绝对定位 =============
  const ensureAbsolutePosition = (dialogEl) => {
    if (!dialogEl.style.left || dialogEl.style.left === '') {
      const rect = dialogEl.getBoundingClientRect()
      dialogEl.style.position = 'absolute'
      dialogEl.style.left = Math.round(rect.left) + 'px'
      dialogEl.style.top = Math.round(rect.top) + 'px'
      dialogEl.style.width = Math.round(rect.width) + 'px'
      dialogEl.style.transform = 'none'
      dialogEl.style.margin = '0'
      updateMaxHeight(dialogEl)
    }
  }

  // ============= 查找 el-dialog 的实际 DOM 元素（兼容 append-to-body 场景） =============
  const findDialogEl = (comp) => {
    if (!comp) return null

    // 策略1：$el 是有效 DOM 元素且包含 header（非 append-to-body 场景）
    const rootEl = comp.$el
    if (rootEl && rootEl.nodeType === 1 && typeof rootEl.querySelector === 'function') {
      const header = rootEl.querySelector('.el-dialog__header')
      if (header) return rootEl
    }

    // 策略2：Element Plus 暴露的 dialogRef（append-to-body 场景）
    // el-dialog 组件通过 defineExpose 暴露 dialogRef，指向 .el-dialog 元素
    const exposedDialog = comp.dialogRef
    if (exposedDialog) {
      const el = exposedDialog.$el || exposedDialog
      if (el && el.nodeType === 1) {
        // 找到包含该 dialog 的 overlay（有 modal 时存在）
        const overlay = el.closest('.el-overlay')
        if (overlay) return overlay
        // :modal="false" 时无 overlay，直接返回 dialog 元素
        // 确认该元素内有 header
        if (el.querySelector('.el-dialog__header')) return el
      }
    }

    // 策略3：从 document 中查找最近打开的弹窗 overlay
    const overlays = document.querySelectorAll('.el-overlay')
    for (let i = overlays.length - 1; i >= 0; i--) {
      const dialog = overlays[i].querySelector('.el-dialog')
      if (dialog) return overlays[i]
    }

    // 策略4：:modal="false" + append-to-body 场景，无 overlay
    // 直接从 body 下查找可见的 el-dialog
    const dialogs = document.querySelectorAll('body > .el-dialog, body > div > .el-dialog')
    for (let i = dialogs.length - 1; i >= 0; i--) {
      const d = dialogs[i]
      if (d.offsetParent !== null || d.style.display !== 'none') {
        if (d.querySelector('.el-dialog__header')) return d
      }
    }

    return null
  }

  // ============= 主初始化函数 =============
  const init = () => {
    cleanup()
    nextTick(() => {
      const comp = dialogRef.value
      if (!comp) return

      const dialogEl = findDialogEl(comp)
      if (!dialogEl) return
      currentDialogEl = dialogEl

      const header = dialogEl.querySelector('.el-dialog__header')
      if (!header) return
      currentHeader = header

      header.style.cursor = 'move'
      header.style.touchAction = 'none' // 防止触摸时页面滚动

      // ============= 拖拽状态 =============
      const startState = { active: false, startX: 0, startY: 0, originLeft: 0, originTop: 0 }

      // ============= 拖拽移动（统一 mouse + touch） =============
      const onMove = (e) => {
        if (!startState.active) return
        e.preventDefault() // 阻止触摸时页面滚动
        const { x, y } = getClientXY(e)
        const rect = dialogEl.getBoundingClientRect()
        const dx = x - startState.startX
        const dy = y - startState.startY
        const vw = window.innerWidth
        const vh = window.innerHeight
        // 限制在视口范围内，留 40px 标题栏可见
        const newLeft = Math.max(0, Math.min(startState.originLeft + dx, vw - rect.width))
        const newTop = Math.max(0, Math.min(startState.originTop + dy, vh - 40))
        dialogEl.style.left = newLeft + 'px'
        dialogEl.style.top = newTop + 'px'
        dialogEl.style.transform = 'none'
        dialogEl.style.margin = '0'
        // 拖拽后动态更新 max-height
        updateMaxHeight(dialogEl)
      }

      // ============= 拖拽释放 =============
      const onUp = () => {
        startState.active = false
        setTransition(dialogEl, true)
        if (moveHandler) {
          document.removeEventListener('mousemove', moveHandler)
          document.removeEventListener('touchmove', moveHandler, { passive: false })
          moveHandler = null
        }
        if (upHandler) {
          document.removeEventListener('mouseup', upHandler)
          document.removeEventListener('touchend', upHandler)
          document.removeEventListener('touchcancel', upHandler)
          upHandler = null
        }
      }

      // ============= 拖拽开始（统一逻辑） =============
      const onStart = (e) => {
        // 只响应左键（mouse）或触摸
        if (e.type === 'mousedown' && e.button !== 0) return
        // 不响应 header 内关闭按钮的点击
        if (e.target.closest('.el-dialog__headerbtn')) return
        // 不响应 resize 手柄区域的点击（防止误触发拖拽）
        if (e.target.closest('.dialog-resize-handle')) return

        ensureAbsolutePosition(dialogEl)

        const { x, y } = getClientXY(e)
        startState.active = true
        startState.startX = x
        startState.startY = y
        startState.originLeft = parseFloat(dialogEl.style.left)
        startState.originTop = parseFloat(dialogEl.style.top)

        setTransition(dialogEl, false)
        moveHandler = onMove
        upHandler = onUp
        document.addEventListener('mousemove', onMove)
        document.addEventListener('touchmove', onMove, { passive: false })
        document.addEventListener('mouseup', onUp)
        document.addEventListener('touchend', onUp)
        document.addEventListener('touchcancel', onUp)
        e.preventDefault()
      }

      // 绑定鼠标和触摸事件
      mouseDownHandler = onStart
      touchStartHandler = onStart
      header.addEventListener('mousedown', mouseDownHandler)
      header.addEventListener('touchstart', touchStartHandler, { passive: false })

      // ============= 调整大小（resizable） =============
      if (resizable) {
        // 清理旧手柄
        dialogEl.querySelectorAll('.dialog-resize-handle').forEach(el => el.remove())

        // 8 个方向：n, s, e, w, ne, nw, se, sw
        const directions = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']
        directions.forEach(dir => {
          const handle = document.createElement('div')
          handle.className = `dialog-resize-handle dialog-resize-${dir}`
          handle.dataset.dir = dir
          handle.style.touchAction = 'none'
          dialogEl.appendChild(handle)
        })

        const resizeState = { active: false, dir: '', startX: 0, startY: 0, originW: 0, originH: 0, originL: 0, originT: 0 }

        // ============= 调整大小移动 =============
        const onResizeMove = (e) => {
          if (!resizeState.active) return
          e.preventDefault()
          const { x, y } = getClientXY(e)
          const dx = x - resizeState.startX
          const dy = y - resizeState.startY
          const dir = resizeState.dir
          const { maxW, maxH } = computeMaxSize()
          let newW = resizeState.originW
          let newH = resizeState.originH
          let newL = resizeState.originL
          let newT = resizeState.originT

          // 横向
          if (dir.includes('e')) {
            newW = Math.max(minWidth, Math.min(resizeState.originW + dx, maxW))
          } else if (dir.includes('w')) {
            const proposedW = resizeState.originW - dx
            newW = Math.max(minWidth, Math.min(proposedW, maxW))
            // 左侧调整：左边界与宽度联动
            newL = resizeState.originL + (resizeState.originW - newW)
            // 防止左侧被推出视口
            if (newL < 0) {
              newW = newW + newL
              newL = 0
            }
          }

          // 纵向：高度始终不超过视口内容区
          if (dir.includes('s')) {
            newH = Math.max(minHeight, Math.min(resizeState.originH + dy, maxH))
          } else if (dir.includes('n')) {
            const proposedH = resizeState.originH - dy
            newH = Math.max(minHeight, Math.min(proposedH, maxH))
            newT = resizeState.originT + (resizeState.originH - newH)
            if (newT < 0) {
              newH = newH + newT
              newT = 0
            }
          }

          // 浏览器可视区域二次校验（保险）
          const vw = window.innerWidth
          const vh = window.innerHeight
          if (newL + newW > vw) newW = vw - newL
          if (newT + newH > vh - 20) newH = vh - 20 - newT

          dialogEl.style.width = newW + 'px'
          dialogEl.style.height = newH + 'px'
          dialogEl.style.left = newL + 'px'
          dialogEl.style.top = newT + 'px'
          dialogEl.style.transform = 'none'
          dialogEl.style.margin = '0'
          // resize 后动态更新 max-height
          updateMaxHeight(dialogEl)
        }

        // ============= 调整大小释放 =============
        const onResizeUp = () => {
          resizeState.active = false
          setTransition(dialogEl, true)
          if (resizeMoveHandler) {
            document.removeEventListener('mousemove', resizeMoveHandler)
            document.removeEventListener('touchmove', resizeMoveHandler, { passive: false })
            resizeMoveHandler = null
          }
          if (resizeUpHandler) {
            document.removeEventListener('mouseup', resizeUpHandler)
            document.removeEventListener('touchend', resizeUpHandler)
            document.removeEventListener('touchcancel', resizeUpHandler)
            resizeUpHandler = null
          }
        }

        // ============= 调整大小开始（统一逻辑） =============
        const onResizeStart = (e) => {
          const target = e.target
          if (!target.classList?.contains('dialog-resize-handle')) return
          if (e.type === 'mousedown' && e.button !== 0) return

          ensureAbsolutePosition(dialogEl)

          const { x, y } = getClientXY(e)
          const rect = dialogEl.getBoundingClientRect()
          resizeState.active = true
          resizeState.dir = target.dataset.dir
          resizeState.startX = x
          resizeState.startY = y
          resizeState.originW = rect.width
          resizeState.originH = rect.height
          resizeState.originL = parseFloat(dialogEl.style.left) || rect.left
          resizeState.originT = parseFloat(dialogEl.style.top) || rect.top

          setTransition(dialogEl, false)
          resizeMoveHandler = onResizeMove
          resizeUpHandler = onResizeUp
          document.addEventListener('mousemove', onResizeMove)
          document.addEventListener('touchmove', onResizeMove, { passive: false })
          document.addEventListener('mouseup', onResizeUp)
          document.addEventListener('touchend', onResizeUp)
          document.addEventListener('touchcancel', onResizeUp)
          e.preventDefault()
          e.stopPropagation()
        }

        resizeDownHandler = onResizeStart
        resizeTouchStartHandler = onResizeStart
        dialogEl.addEventListener('mousedown', resizeDownHandler)
        dialogEl.addEventListener('touchstart', resizeTouchStartHandler, { passive: false })
      }

      // ============= 窗口 resize 监听 =============
      windowResizeHandler = () => {
        if (!dialogEl) return
        const rect = dialogEl.getBoundingClientRect()
        const vw = window.innerWidth
        const vh = window.innerHeight

        // 位置修正：确保弹窗不超出新视口
        let needUpdate = false
        if (rect.left + rect.width > vw) {
          dialogEl.style.left = Math.max(0, vw - rect.width) + 'px'
          needUpdate = true
        }
        if (rect.top + rect.height > vh) {
          dialogEl.style.top = Math.max(0, vh - rect.height) + 'px'
          needUpdate = true
        }
        // 宽度修正
        if (rect.width > vw) {
          dialogEl.style.width = vw + 'px'
          needUpdate = true
        }

        // 高度修正
        if (needUpdate || dialogEl.style.maxHeight) {
          updateMaxHeight(dialogEl)
        }
      }
      window.addEventListener('resize', windowResizeHandler)
    })
  }

  onUnmounted(() => {
    cleanup()
  })

  return { initDraggable: init, cleanup }
}
