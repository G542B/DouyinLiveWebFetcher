import sys
import os
from typing import Dict, List, Optional, Callable
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from liveMan import DouyinLiveWebFetcher
from .models import Room, MESSAGE_TYPES, AdvancedFilterConfig
from .filter_engine import filter_engine
from .config_manager import config_manager


class RoomManager:
    def __init__(self, message_callback: Optional[Callable] = None):
        self.rooms: Dict[str, Room] = {}
        self.fetchers: Dict[str, DouyinLiveWebFetcher] = {}
        self.message_callback = message_callback
        # 游戏猜词回调（由app.py设置）
        self.game_guess_callback: Optional[Callable] = None
        # 游戏管理器引用（由app.py设置，用于提问识别分流）
        self.game_manager = None
        # 默认只启用用户交互类消息类型（排除系统/内部消息）
        self.filter_config: List[str] = [
            'WebcastChatMessage',
            'WebcastGiftMessage',
            'WebcastLikeMessage',
            'WebcastMemberMessage',
            'WebcastSocialMessage',
            'WebcastFansclubMessage',
            'WebcastEmojiChatMessage',
            'WebcastRoomUserSeqMessage',
        ]
        
        # 尝试加载保存的配置
        saved_config = config_manager.load_config('filter_config')
        if saved_config:
            try:
                advanced_config = AdvancedFilterConfig(**saved_config)
                self.filter_config = advanced_config.enabled_types.copy()
                filter_engine.update_config(advanced_config)
            except Exception as e:
                print(f"[RoomManager] 加载配置失败，使用默认配置: {e}")
                default_advanced_config = AdvancedFilterConfig()
                default_advanced_config.enabled_types = self.filter_config.copy()
                filter_engine.update_config(default_advanced_config)
        else:
            default_advanced_config = AdvancedFilterConfig()
            default_advanced_config.enabled_types = self.filter_config.copy()
            filter_engine.update_config(default_advanced_config)
    
    def add_room(self, live_id: str, name: Optional[str] = None) -> Room:
        room_id = f"room_{live_id}"
        if room_id in self.rooms:
            return self.rooms[room_id]
        
        room = Room(
            id=room_id,
            live_id=live_id,
            name=name or f"直播间 {live_id}",
            status='stopped',
            created_at=datetime.now()
        )
        self.rooms[room_id] = room
        return room
    
    def remove_room(self, room_id: str) -> bool:
        if room_id not in self.rooms:
            return False
        
        self.stop_room(room_id)
        del self.rooms[room_id]
        return True
    
    def start_room(self, room_id: str) -> bool:
        import traceback
        if room_id not in self.rooms:
            print(f"[RoomManager] 未找到房间: {room_id}")
            return False
        
        if room_id in self.fetchers:
            print(f"[RoomManager] 房间已在运行: {room_id}")
            return True
        
        room = self.rooms[room_id]
        print(f"[RoomManager] 正在启动房间: {room.name} (live_id: {room.live_id})")
        
        def callback(live_id, msg_type, data):
            try:
                if self.message_callback:
                    message = {
                        'room_id': room_id,
                        'live_id': live_id,
                        'message_type': msg_type,
                        'data': data,
                        'timestamp': datetime.now().isoformat()
                    }

                    # 表情包 partial 过滤：移除表情部分，保留文本
                    if (filter_engine.config.emoji_filter.enabled
                        and filter_engine.config.emoji_filter.strategy == 'partial'
                        and msg_type == 'WebcastChatMessage'):
                        data = dict(data)
                        if data.get('has_image_emoji') and filter_engine.config.emoji_filter.filter_image_emoji:
                            data['has_image_emoji'] = False
                            data['emoji_details'] = [d for d in data.get('emoji_details', []) if d['type'] != 'image_emoji']
                        if data.get('has_text_emoji') and filter_engine.config.emoji_filter.filter_text_emoji:
                            data['has_text_emoji'] = False
                            data['emoji_details'] = [d for d in data.get('emoji_details', []) if d['type'] != 'text_emoji']
                        message['data'] = data

                    # 独立表情包消息在 partial 模式下转为文本消息
                    if (filter_engine.config.emoji_filter.enabled
                        and filter_engine.config.emoji_filter.strategy == 'partial'
                        and msg_type == 'WebcastEmojiChatMessage'):
                        default_content = data.get('default_content', '')
                        if default_content:
                            message['message_type'] = 'WebcastChatMessage'
                            message['data'] = {
                                'type': 'chat',
                                'user_name': data.get('user_name', ''),
                                'user_id': data.get('user_id', 0),
                                'content': default_content,
                                'has_image_emoji': False,
                                'has_text_emoji': False,
                                'emoji_details': [],
                            }

                    allowed, reason = filter_engine.should_allow(message)
                    if allowed:
                        # 游戏模式下提取猜词
                        if msg_type == 'WebcastChatMessage' and self.game_guess_callback:
                            user_name = data.get('user_name', '')
                            content = data.get('content', '')
                            if content:
                                # 先检查是否为提问类弹幕（仅游戏运行中且问答功能开启时）
                                if self.game_manager and self.game_manager.is_question(content):
                                    result = self.game_manager.process_question(user_name, content)
                                    if result:
                                        # 提问类弹幕已由process_question处理并广播，不进入弹幕流和猜词流程
                                        return
                                # 非提问类弹幕走原有猜词流程
                                self.game_guess_callback(user_name, content)

                        self.message_callback(message)
            except Exception as e:
                print(f"[RoomManager] 消息回调处理失败: {e}")
        
        try:
            fetcher = DouyinLiveWebFetcher(
                live_id=room.live_id,
                message_callback=callback,
                filter_types=None
            )
            
            self.fetchers[room_id] = fetcher
            fetcher.start()
            room.status = 'running'
            print(f"[RoomManager] 房间启动成功: {room.name}")
            return True
        except FileNotFoundError as e:
            print(f"[RoomManager] 启动直播间失败 - 文件缺失: {e}")
            print(f"[RoomManager] 错误堆栈:\n{traceback.format_exc()}")
            # 清理
            if room_id in self.fetchers:
                del self.fetchers[room_id]
            room.status = 'error'
            # 通过回调通知前端
            if self.message_callback:
                try:
                    self.message_callback({
                        'room_id': room_id,
                        'live_id': room.live_id,
                        'message_type': 'error',
                        'data': {'message': f'文件缺失: {e}'},
                        'timestamp': datetime.now().isoformat()
                    })
                except Exception:
                    pass
            return False
        except Exception as e:
            print(f"[RoomManager] 启动直播间失败: {e}")
            print(f"[RoomManager] 错误堆栈:\n{traceback.format_exc()}")
            # 如果启动失败，清理一下
            if room_id in self.fetchers:
                try:
                    self.fetchers[room_id].stop()
                except Exception as stop_error:
                    print(f"[RoomManager] 停止失败的 fetcher 时出错: {stop_error}")
                del self.fetchers[room_id]
            room.status = 'error'
            # 通过回调通知前端
            if self.message_callback:
                try:
                    self.message_callback({
                        'room_id': room_id,
                        'live_id': room.live_id,
                        'message_type': 'error',
                        'data': {'message': f'启动失败: {e}'},
                        'timestamp': datetime.now().isoformat()
                    })
                except Exception:
                    pass
            return False
    
    def stop_room(self, room_id: str) -> bool:
        if room_id not in self.fetchers:
            return False
        
        fetcher = self.fetchers[room_id]
        fetcher.stop()
        del self.fetchers[room_id]
        
        if room_id in self.rooms:
            self.rooms[room_id].status = 'stopped'
        return True
    
    def get_room(self, room_id: str) -> Optional[Room]:
        return self.rooms.get(room_id)
    
    def get_all_rooms(self) -> List[Room]:
        return list(self.rooms.values())
    
    def update_filter(self, enabled_types: List[str]) -> None:
        self.filter_config = enabled_types
        
        config = filter_engine.config
        config.enabled_types = enabled_types
        filter_engine.update_config(config)
        
        # 保存配置
        self._save_config()
    
    def update_advanced_filter(self, config: AdvancedFilterConfig) -> None:
        self.filter_config = config.enabled_types
        filter_engine.update_config(config)
        
        # 保存配置
        self._save_config()
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            config_dict = filter_engine.config.model_dump()
            config_manager.save_config('filter_config', config_dict)
        except Exception as e:
            print(f"[RoomManager] 保存配置失败: {e}")
    
    def get_filter_config(self) -> List[str]:
        return self.filter_config.copy()
    
    def get_advanced_filter_config(self) -> AdvancedFilterConfig:
        return AdvancedFilterConfig(**filter_engine.config.model_dump())
    
    def shutdown(self):
        """
        停止所有房间并清理资源
        """
        print("[RoomManager] 正在停止所有房间...")
        # 复制一份房间列表，避免在迭代时修改
        room_ids = list(self.rooms.keys())
        for room_id in room_ids:
            self.stop_room(room_id)
        # 清空房间列表
        self.rooms.clear()
        self.fetchers.clear()
        print("[RoomManager] 所有房间已停止，资源已清理")
