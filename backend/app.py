import asyncio
import json
import threading
import os
import signal
import sys
from contextlib import asynccontextmanager
from typing import List, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from queue import Queue, Empty

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.license import verify_license, get_machine_code, get_hardware_summary, save_license, check_license_status, clear_license
from backend.manager import RoomManager
from backend.models import (
    Room, RoomCreate, FilterConfig, MESSAGE_TYPES,
    OutputConfig, OutputStatus, PickerResult, SendLogEntry,
    AdvancedFilterConfig, FilterStats,
    WordBankEntry, WordBankCreate, WordBankUpdate, WordBankBatchImport,
    GameConfigModel, GuessRecord, RankingEntry
)
from backend.output_manager import output_manager
from backend.performance_monitor import performance_monitor
from backend.filter_engine import filter_engine
from backend.config_manager import config_manager
from backend.game_manager import GameManager

active_connections: Set[WebSocket] = set()

message_queue = Queue()

room_manager = RoomManager()

# 猜词游戏管理器
game_manager = GameManager()

# 全局关闭标志
_shutdown_event = threading.Event()

# [TEMP-DISABLE-LICENSE] 临时禁用许可证验证开关，设为 True 跳过验证，设为 False 恢复验证
_LICENSE_BYPASS = True

# 许可证验证状态
_license_verified = False
_license_checked = False

# 获取项目根目录
_project_root = config_manager.get_project_root()


def safe_json_serialize(message: dict) -> str:
    try:
        return json.dumps(message, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as e:
        print(f"[Broadcast] JSON 序列化失败: {e}, 消息类型: {message.get('message_type')}")
        return None


async def broadcast_worker():
    print("[Broadcast] broadcast_worker 已启动")
    while True:
        try:
            try:
                message = message_queue.get_nowait()
            except Empty:
                await asyncio.sleep(0.1)
                continue

            serialized = safe_json_serialize(message)
            if serialized is None:
                message_queue.task_done()
                continue

            conn_count = len(active_connections)
            print(f"[Broadcast] 广播消息: {message.get('message_type')} - {conn_count} 个连接")

            if conn_count == 0:
                message_queue.task_done()
                continue

            disconnected = []
            for connection in list(active_connections):
                try:
                    await connection.send_text(serialized)
                except WebSocketDisconnect:
                    print(f"[Broadcast] 连接已断开，移除")
                    disconnected.append(connection)
                except RuntimeError as e:
                    print(f"[Broadcast] 发送运行时错误: {e}")
                    disconnected.append(connection)
                except Exception as e:
                    print(f"[Broadcast] 发送失败: {type(e).__name__}: {e}")
                    disconnected.append(connection)
            for connection in disconnected:
                active_connections.discard(connection)

            message_queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Broadcast worker error: {e}")
            await asyncio.sleep(0.1)


def broadcast_message(message: dict):
    message_queue.put(message)
    # 过滤掉输出日志消息和系统事件，防止循环输出或误处理
    msg_type = message.get('message_type', '')
    if msg_type not in ['output_sent', 'output_status', 'output_error', 'playwright_progress']:
        output_manager.push_danmaku(message)
    performance_monitor.record_message()


room_manager.message_callback = broadcast_message
output_manager.set_broadcast_callback(broadcast_message)
game_manager.set_broadcast_callback(broadcast_message)
room_manager.game_guess_callback = game_manager.process_guess
room_manager.game_manager = game_manager


def shutdown_cleanup():
    """清理所有资源"""
    print("\n[App] 开始清理资源...")
    
    # 关闭所有 WebSocket 连接
    print("[App] 关闭 WebSocket 连接...")
    for conn in list(active_connections):
        try:
            asyncio.create_task(conn.close())
        except Exception as e:
            print(f"[App] 关闭连接失败: {e}")
    active_connections.clear()
    
    # 关闭房间管理器
    try:
        room_manager.shutdown()
    except Exception as e:
        print(f"[App] 关闭房间管理器失败: {e}")
    
    # 关闭输出管理器
    try:
        output_manager.shutdown()
    except Exception as e:
        print(f"[App] 关闭输出管理器失败: {e}")
    
    print("[App] 资源清理完成")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[App] 应用启动中...")
    task = asyncio.create_task(broadcast_worker())

    # 启动 Embedding 引擎（异步执行，不阻塞主启动流程）
    async def _init_embedding():
        try:
            # game_manager 内部已启动异步初始化线程，这里仅打印状态
            from backend.embedding_engine import embedding_engine

            print(f"[App] Embedding 模型: {embedding_engine.MODEL_NAME}")
            print(f"[App] Embedding 本地路径: {embedding_engine.LOCAL_DIR}")
        except Exception as e:
            print(f"[App] Embedding 模块导入失败（功能将降级）: {e}")

    await _init_embedding()

    yield

    print("[App] 应用关闭中...")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    # 在事件循环中调用清理
    await asyncio.get_event_loop().run_in_executor(None, shutdown_cleanup)


app = FastAPI(title="抖音直播弹幕抓取器", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dist = os.path.join(_project_root, 'frontend', 'dist')
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")


def init_license():
    global _license_verified, _license_checked
    # [TEMP-DISABLE-LICENSE] 当 _LICENSE_BYPASS 为 True 时跳过许可证验证
    if _LICENSE_BYPASS:
        _license_verified = True
        _license_checked = True
        print("[License] ⚠️ 许可证验证已临时禁用（_LICENSE_BYPASS=True）")
        return
    try:
        status = check_license_status()
        _license_verified = status.get('verified', False)
        _license_checked = True
        if _license_verified:
            print(f"[License] 许可证已验证通过")
        else:
            print(f"[License] 许可证未验证，机器码: {status.get('machine_code', 'N/A')[:16]}...")
    except Exception as e:
        _license_verified = False
        _license_checked = True
        print(f"[License] 许可证检查失败: {e}")


init_license()


@app.middleware("http")
async def license_middleware(request, call_next):
    # [TEMP-DISABLE-LICENSE] 当 _LICENSE_BYPASS 为 True 时跳过许可证拦截
    if _LICENSE_BYPASS:
        return await call_next(request)
    path = request.url.path
    if path.startswith('/api/license') or path == '/' or path.startswith('/assets') or path.startswith('/ws'):
        return await call_next(request)
    if path.startswith('/api/') and not _license_verified:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={"error": "license_required", "message": "请先验证许可证"})
    return await call_next(request)


@app.get("/")
async def root():
    frontend_path = os.path.join(_project_root, 'frontend', 'dist', 'index.html')
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path)
    return {"message": "抖音直播弹幕抓取器 API 服务已启动，请先构建前端"}


@app.get("/api/rooms", response_model=List[Room])
async def get_rooms():
    return room_manager.get_all_rooms()


@app.post("/api/rooms", response_model=Room)
async def create_room(room: RoomCreate):
    return room_manager.add_room(room.live_id, room.name)


@app.delete("/api/rooms/{room_id}")
async def delete_room(room_id: str):
    success = room_manager.remove_room(room_id)
    if not success:
        raise HTTPException(status_code=404, detail="Room not found")
    return {"success": True}


@app.post("/api/rooms/{room_id}/start")
async def start_room(room_id: str):
    success = room_manager.start_room(room_id)
    if not success:
        raise HTTPException(status_code=404, detail="Room not found")
    return {"success": True}


@app.post("/api/rooms/{room_id}/stop")
async def stop_room(room_id: str):
    success = room_manager.stop_room(room_id)
    if not success:
        raise HTTPException(status_code=404, detail="Room not found")
    return {"success": True}


@app.get("/api/filters", response_model=FilterConfig)
async def get_filters():
    return FilterConfig(enabled_types=room_manager.get_filter_config())


@app.put("/api/filters")
async def update_filters(config: FilterConfig):
    room_manager.update_filter(config.enabled_types)
    return {"success": True}


@app.get("/api/filters/advanced", response_model=AdvancedFilterConfig)
async def get_advanced_filters():
    config = room_manager.get_advanced_filter_config()
    # 确保返回的数据结构正确
    return config


@app.put("/api/filters/advanced")
async def update_advanced_filters(config: AdvancedFilterConfig):
    try:
        room_manager.update_advanced_filter(config)
        return {"success": True, "message": "配置已更新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"配置更新失败: {str(e)}")


@app.get("/api/filters/stats", response_model=FilterStats)
async def get_filter_stats():
    return filter_engine.get_stats()


@app.post("/api/filters/stats/reset")
async def reset_filter_stats():
    filter_engine.reset_stats()
    return {"success": True}


@app.get("/api/message-types")
async def get_message_types():
    return MESSAGE_TYPES


@app.get("/api/output/config", response_model=OutputConfig)
async def get_output_config():
    return output_manager.get_config()


@app.put("/api/output/config")
async def update_output_config(config: OutputConfig):
    output_manager.update_config(config.model_dump())
    return {"success": True}


@app.post("/api/output/start")
async def start_output():
    success = output_manager.start()
    return {"success": success, "status": output_manager.get_status()}


@app.post("/api/output/stop")
async def stop_output():
    output_manager.stop()
    return {"success": True, "status": output_manager.get_status()}


# ===== 浏览器输出独立控制 =====

@app.post("/api/output/browser/start")
async def start_browser_output():
    success = output_manager.start_browser_output()
    return {"success": success, "status": output_manager.browser_status.to_dict()}


@app.post("/api/output/browser/stop")
async def stop_browser_output():
    output_manager.stop_browser_output()
    return {"success": True, "status": output_manager.browser_status.to_dict()}


@app.get("/api/output/browser/status")
async def get_browser_output_status():
    return output_manager.browser_status.to_dict()


# ===== 文件输出独立控制 =====

@app.post("/api/output/file/start")
async def start_file_output():
    success = output_manager.start_file_output()
    return {"success": success, "status": output_manager.file_status.to_dict()}


@app.post("/api/output/file/stop")
async def stop_file_output():
    output_manager.stop_file_output()
    return {"success": True, "status": output_manager.file_status.to_dict()}


@app.get("/api/output/file/status")
async def get_file_output_status():
    return output_manager.file_status.to_dict()


@app.get("/api/output/status", response_model=OutputStatus)
async def get_output_status():
    return output_manager.get_status()


@app.post("/api/output/open-website")
async def open_website(url: str = None):
    if url:
        output_manager.config.target_url = url
    result = output_manager.open_website(url)
    return result


@app.post("/api/output/close-browser")
async def close_browser():
    output_manager.close_browser()
    return {"success": True}


@app.post("/api/output/picker/start")
async def start_picker():
    result = output_manager.start_picker()
    return result


@app.post("/api/output/picker/stop")
async def stop_picker():
    result = output_manager.stop_picker()
    return result


@app.get("/api/output/picker/result")
async def get_picker_result():
    result = output_manager.get_picker_result()
    return result


@app.get("/api/output/logs")
async def get_send_logs(count: int = 20):
    return output_manager.get_send_logs(count)


@app.post("/api/output/resize-viewport")
async def resize_viewport(width: int = 1280, height: int = 720):
    result = output_manager.resize_viewport(width, height)
    return result


@app.get("/api/output/viewport-info")
async def get_viewport_info():
    result = output_manager.get_viewport_info()
    return result


@app.get("/api/performance/stats")
async def get_performance_stats():
    return {
        'backend': performance_monitor.get_stats(),
        'buffer': output_manager.buffer.stats
    }


@app.websocket("/ws/danmaku")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    print(f"[WebSocket] 新连接，当前连接数: {len(active_connections)}")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WebSocket] 连接异常: {e}")
    finally:
        active_connections.discard(websocket)
        print(f"[WebSocket] 连接断开，当前连接数: {len(active_connections)}")


# ===== 许可证验证接口 =====

@app.get("/api/license/status")
async def api_license_status():
    global _license_verified
    status = check_license_status()
    _license_verified = status.get('verified', False)
    return {
        'verified': _license_verified,
        'machine_code': status.get('machine_code', ''),
        'hardware': status.get('hardware'),
        'verified_at': status.get('verified_at', ''),
    }


@app.get("/api/license/machine-code")
async def api_machine_code():
    return {
        'machine_code': get_machine_code(),
        'hardware': get_hardware_summary(),
    }


@app.post("/api/license/verify")
async def api_verify_license(data: dict):
    global _license_verified
    license_key = data.get('license_key', '').strip()
    if not license_key:
        raise HTTPException(status_code=400, detail="请输入许可证密钥")

    try:
        ok = verify_license(license_key)
        if ok:
            save_license(license_key)
            _license_verified = True
            return {'success': True, 'message': '许可证验证通过'}
        else:
            return {'success': False, 'message': '许可证密钥无效，请检查后重试'}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/license/logout")
async def api_logout():
    global _license_verified
    clear_license()
    _license_verified = False
    return {'success': True, 'message': '已清除许可证信息'}


# ===== 猜词游戏接口 =====

# --- 词库管理 ---

@app.get("/api/game/words")
async def get_game_words():
    return [w.model_dump() for w in game_manager.get_all_words()]


@app.post("/api/game/words")
async def add_game_word(word: WordBankCreate):
    entry = game_manager.add_word(
        answer=word.answer,
        hints=word.hints,
        category=word.category,
        difficulty=word.difficulty
    )
    return entry.model_dump()


@app.put("/api/game/words/{word_id}")
async def update_game_word(word_id: str, word: WordBankUpdate):
    entry = game_manager.update_word(word_id, **word.model_dump(exclude_none=True))
    if not entry:
        raise HTTPException(status_code=404, detail="词库条目未找到")
    return entry.model_dump()


@app.delete("/api/game/words/{word_id}")
async def delete_game_word(word_id: str):
    success = game_manager.remove_word(word_id)
    if not success:
        raise HTTPException(status_code=404, detail="词库条目未找到")
    return {"success": True}


@app.post("/api/game/words/batch")
async def batch_import_words(data: WordBankBatchImport):
    count = game_manager.batch_import([w.model_dump() for w in data.words])
    return {"success": True, "imported_count": count}


@app.get("/api/game/words/export")
async def export_game_words():
    words = game_manager.get_all_words()
    return [w.model_dump() for w in words]


# --- 游戏配置 ---

@app.get("/api/game/config")
async def get_game_config():
    return game_manager.get_config().model_dump()


@app.put("/api/game/config")
async def update_game_config(config: GameConfigModel):
    updated = game_manager.update_config(config.model_dump(exclude_unset=True))
    return updated.model_dump()


# --- 游戏控制 ---

@app.post("/api/game/start")
async def start_game():
    success = game_manager.start_game()
    if not success:
        raise HTTPException(status_code=400, detail="无法开始游戏，请检查词库是否为空或游戏已在运行")
    return {"success": True}


@app.post("/api/game/pause")
async def pause_game():
    success = game_manager.pause_game()
    if not success:
        raise HTTPException(status_code=400, detail="无法暂停，游戏未在运行")
    return {"success": True}


@app.post("/api/game/resume")
async def resume_game():
    success = game_manager.resume_game()
    if not success:
        raise HTTPException(status_code=400, detail="无法恢复，游戏未在暂停状态")
    return {"success": True}


@app.post("/api/game/stop")
async def stop_game():
    success = game_manager.stop_game()
    if not success:
        raise HTTPException(status_code=400, detail="游戏未在运行")
    return {"success": True}


@app.post("/api/game/next-round")
async def next_round():
    success = game_manager.next_round()
    if not success:
        raise HTTPException(status_code=400, detail="无法切换下一轮")
    return {"success": True}


@app.get("/api/game/state")
async def get_game_state():
    return game_manager.get_state()


@app.post("/api/game/hint")
async def show_hint():
    hint = game_manager.show_hint()
    if hint is None:
        raise HTTPException(status_code=400, detail="没有更多提示可用")
    return {"success": True, "hint": hint}


# --- 猜词与排行 ---

@app.get("/api/game/rankings")
async def get_game_rankings(limit: int = 20):
    rankings = game_manager.get_rankings(limit)
    return [r.model_dump() for r in rankings]


@app.get("/api/game/guesses")
async def get_game_guesses():
    return [g.model_dump() for g in game_manager.current_round_guesses]


# --- 历史记录 ---

@app.get("/api/game/history")
async def get_game_history(page: int = 1, page_size: int = 20):
    return game_manager.get_history(page, page_size)


@app.get("/api/game/history/{round_id}")
async def get_game_round_detail(round_id: str):
    detail = game_manager.get_round_detail(round_id)
    if not detail:
        raise HTTPException(status_code=404, detail="轮次记录未找到")
    return detail


@app.post("/api/game/history/clear")
async def clear_game_history():
    game_manager.clear_history()
    return {"success": True}


@app.get("/api/game/embedding/status")
async def get_embedding_status():
    """返回 Embedding 模型状态、预计算进度、关联度计算性能"""
    return {
        "embedding": game_manager.get_embedding_status(),
        "similarity_perf": game_manager.get_similarity_perf(),
    }


# 捕获所有其他路由，返回前端 index.html 以支持前端路由
# 必须放在所有 API 路由的后面！
@app.get("/{full_path:path}")
async def catch_all(full_path: str):
    # 如果是 API 请求或 WebSocket，直接返回 404
    if full_path.startswith("api/") or full_path.startswith("ws/"):
        raise HTTPException(status_code=404, detail="Not Found")
    
    # 否则返回前端页面
    frontend_path = os.path.join(_project_root, 'frontend', 'dist', 'index.html')
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path)
    return {"message": "抖音直播弹幕抓取器 API 服务已启动，请先构建前端"}


def run_server():
    """运行服务器"""
    import uvicorn
    import traceback
    
    print(f"[App] Python 路径: {sys.executable}")
    print(f"[App] 当前工作目录: {os.getcwd()}")
    print(f"[App] 项目根目录: {_project_root}")
    
    # 检查必要的路径和文件
    frontend_dist = os.path.join(_project_root, 'frontend', 'dist')
    print(f"[App] 前端构建目录: {frontend_dist}, 是否存在: {os.path.exists(frontend_dist)}")
    
    if os.path.exists(frontend_dist):
        index_html = os.path.join(frontend_dist, 'index.html')
        print(f"[App] 前端 index.html: {index_html}, 是否存在: {os.path.exists(index_html)}")
    
    # 信号处理
    def handle_signal(signum, frame):
        print(f"\n[App] 接收到信号 {signum}，正在关闭...")
        _shutdown_event.set()
    
    # 注册信号处理器
    if sys.platform != 'win32':
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
    
    try:
        print("[App] 正在启动 Uvicorn 服务器...")
        uvicorn.run(app, host="0.0.0.0", port=8000)
    except Exception as e:
        print(f"[App] 服务器启动失败: {e}")
        print(f"[App] 错误堆栈:\n{traceback.format_exc()}")
        raise


if __name__ == "__main__":
    run_server()
