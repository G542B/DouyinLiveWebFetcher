; Clear Electron cache before installing new version
; Uses wildcard to avoid encoding issues with Chinese app name

!macro customInstall
  ; Clear all Electron user data directories matching the app name pattern
  RMDir /r "$APPDATA\douyin-live-danmaku"
  RMDir /r "$LOCALAPPDATA\douyin-live-danmaku"
  
  ; Clear Electron cache directories
  RMDir /r "$LOCALAPPDATA\Electron\Cache"
  RMDir /r "$LOCALAPPDATA\electron\Cache"
  
  ; Try to clear by product name (may fail due to encoding, but harmless)
  ExecWait 'cmd /c "rd /s /q "$APPDATA\抖音弹幕抓取工具" 2>nul"'
  ExecWait 'cmd /c "rd /s /q "$LOCALAPPDATA\抖音弹幕抓取工具" 2>nul"'
!macroend