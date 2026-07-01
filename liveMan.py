#!/usr/bin/python
# coding:utf-8

# @FileName:    liveMan.py
# @Time:        2024/1/2 21:51
# @Author:      bubu
# @Project:     douyinLiveWebFetcher

import codecs
import gzip
import hashlib
import json
import os
import random
import re
import string
import subprocess
import sys
import threading
import time
import urllib.parse
from contextlib import contextmanager

import requests
import websocket

from ac_signature import get__ac_signature
from protobuf.douyin import *
from backend.logger import logger, install_exception_hooks

from urllib3.util.url import parse_url

# 安装全局异常钩子（只在主线程安装一次）
install_exception_hooks()




def _get_project_root() -> str:
    """获取项目根目录，兼容不同运行环境"""
    # 优先级1: __file__ 推导
    try:
        if __file__:
            root = os.path.dirname(os.path.abspath(__file__))
            if os.path.exists(os.path.join(root, 'sign.js')) or os.path.exists(os.path.join(root, 'liveMan.py')):
                return root
            logger.warning(f"[路径] __file__ 推导的路径 {root} 未找到关键文件，尝试其他方式")
    except NameError:
        pass
    
    # 优先级2: 从 sys.argv[0] 推导
    if sys.argv and sys.argv[0]:
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        if os.path.exists(os.path.join(script_dir, 'sign.js')) or os.path.exists(os.path.join(script_dir, 'liveMan.py')):
            logger.info(f"[路径] 从 sys.argv[0] 推导项目根目录: {script_dir}")
            return script_dir
    
    # 优先级3: 当前工作目录
    cwd = os.getcwd()
    if os.path.exists(os.path.join(cwd, 'sign.js')) or os.path.exists(os.path.join(cwd, 'liveMan.py')):
        logger.info(f"[路径] 使用当前工作目录: {cwd}")
        return cwd
    
    # 优先级4: 回退到 __file__ 推导
    try:
        if __file__:
            root = os.path.dirname(os.path.abspath(__file__))
            logger.warning(f"[路径] 回退到 __file__ 推导（未验证）: {root}")
            return root
    except NameError:
        pass
    
    logger.warning(f"[路径] 使用当前工作目录（最终回退）: {cwd}")
    return cwd


def _find_node_exe() -> str:
    """
    查找可用的 Node.js 可执行文件。
    优先级：1. Playwright 自带 node.exe  2. 系统 PATH 中的 node
    """
    # 尝试 Playwright 自带的 node.exe
    try:
        import playwright
        pw_node = os.path.join(os.path.dirname(playwright.__file__), 'driver', 'node.exe')
        if os.path.isfile(pw_node):
            logger.info(f"[JS引擎] 找到 Playwright Node.js: {pw_node}")
            return pw_node
    except ImportError:
        pass
    
    # 尝试系统 PATH 中的 node
    import shutil
    node_path = shutil.which('node')
    if node_path:
        logger.info(f"[JS引擎] 找到系统 Node.js: {node_path}")
        return node_path
    
    return None


def _exec_js_via_node(script_file: str, call_expr: str, timeout: int = 10) -> str:
    """
    通过 Node.js 子进程执行 JS 脚本并调用指定函数。
    :param script_file: JS 脚本文件路径
    :param call_expr: 调用表达式，如 "get_sign('abc')" 
    :param timeout: 超时秒数
    :return: 函数返回值的字符串形式
    """
    node_exe = _find_node_exe()
    if not node_exe:
        raise RuntimeError("未找到可用的 Node.js 可执行文件")

    # 构造 Node.js 执行脚本：加载 JS 文件，调用函数，输出 JSON 结果
    node_script = f'''
const fs = require('fs');
const script = fs.readFileSync({json.dumps(script_file)}, 'utf-8');
eval(script);
const result = {call_expr};
console.log(JSON.stringify(result));
'''
    try:
        proc = subprocess.run(
            [node_exe, '-e', node_script],
            capture_output=True, text=True, timeout=timeout,
            encoding='utf-8'
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Node.js 执行失败 (code={proc.returncode}): {proc.stderr.strip()}")
        output = proc.stdout.strip().split('\n')[-1]  # 取最后一行
        return json.loads(output)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Node.js 执行超时 ({timeout}s)")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Node.js 返回值解析失败: {e}, output: {proc.stdout}")


def generateSignature(wss, script_file='sign.js'):
    """
    生成 WebSocket 签名（使用 Node.js）
    """
    params = ("live_id,aid,version_code,webcast_sdk_version,"
              "room_id,sub_room_id,sub_channel_id,did_rule,"
              "user_unique_id,device_platform,device_type,ac,"
              "identity").split(',')
    wss_params = urllib.parse.urlparse(wss).query.split('&')
    wss_maps = {i.split('=')[0]: i.split("=")[-1] for i in wss_params}
    tpl_params = [f"{i}={wss_maps.get(i, '')}" for i in params]
    param = ','.join(tpl_params)
    md5 = hashlib.md5()
    md5.update(param.encode())
    md5_param = md5.hexdigest()
    
    # 处理相对路径，兼容打包环境
    if not os.path.isabs(script_file):
        project_root = _get_project_root()
        script_file = os.path.join(project_root, script_file)
    
    # 验证脚本文件存在
    if not os.path.exists(script_file):
        raise FileNotFoundError(f"签名脚本文件不存在: {script_file}，项目根目录: {_get_project_root()}")
    
    logger.info(f"[签名] 读取签名脚本: {script_file}")
    
    # 使用 Node.js 生成签名
    try:
        signature = _exec_js_via_node(script_file, f'get_sign("{md5_param}")')
        logger.info(f"[签名] 签名生成成功 (Node.js)")
        return signature
    except Exception as e:
        logger.error(f"[签名] 签名生成失败: {e}", exc_info=True)
        raise RuntimeError(f"签名生成失败: {e}")


class _NodeJsContext:
    """Node.js JS 上下文包装（通过子进程调用）"""
    def __init__(self, js_file: str):
        self._js_file = js_file
    
    def call(self, func_name, *args):
        args_json = ', '.join(json.dumps(a) for a in args)
        call_expr = f'{func_name}({args_json})'
        return _exec_js_via_node(self._js_file, call_expr)


def execute_js(js_file: str):
    """
    执行 JavaScript 文件，返回可调用上下文（使用 Node.js）
    """
    # 处理相对路径
    if not os.path.isabs(js_file):
        project_root = _get_project_root()
        js_file = os.path.join(project_root, js_file)
    
    return _NodeJsContext(js_file)


def generateMsToken(length=182):
    """
    产生请求头部cookie中的msToken字段，其实为随机的107位字符
    :param length:字符位数
    :return:msToken
    """
    random_str = ''
    base_str = string.ascii_letters + string.digits + '-_'
    _len = len(base_str) - 1
    for _ in range(length):
        random_str += base_str[random.randint(0, _len)]
    return random_str


class DouyinLiveWebFetcher:
    
    def __init__(self, live_id, abogus_file='a_bogus.js', message_callback=None, filter_types=None):
        """
        直播间弹幕抓取对象
        :param live_id: 直播间的直播id，打开直播间web首页的链接如：https://live.douyin.com/261378947940，
                        其中的261378947940即是live_id
        :param message_callback: 消息回调函数，接收 (room_id, message_type, data)
        :param filter_types: 消息类型过滤列表，只处理列表中的消息类型
        """
        # 处理 abogus_file 路径
        if not os.path.isabs(abogus_file):
            project_root = _get_project_root()
            self.abogus_file = os.path.join(project_root, abogus_file)
        else:
            self.abogus_file = abogus_file
        
        self.__ttwid = None
        self.__room_id = None
        self.session = requests.Session()
        self.live_id = live_id
        self.host = "https://www.douyin.com/"
        self.live_url = "https://live.douyin.com/"
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0"
        self.headers = {
            'User-Agent': self.user_agent
        }
        self.message_callback = message_callback
        self.filter_types = filter_types
        self.ws = None
        self.running = False
        self._heartbeat_thread = None
        self._heartbeat_stop_event = threading.Event()
        self._ws_thread = None
    
    def start(self):
        if self.running:
            logger.warning(f"直播间 {self.live_id} 已在运行")
            return
        self.running = True
        self._ws_thread = threading.Thread(target=self._connectWebSocket, daemon=True,
                                           name=f"ws-{self.live_id}")
        self._ws_thread.start()
        logger.info(f"开始抓取直播间: {self.live_id}")

    def stop(self):
        logger.info(f"正在停止直播间抓取: {self.live_id}")
        self.running = False
        self._heartbeat_stop_event.set()

        # 关闭 WebSocket 连接
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                logger.error(f"WebSocket 关闭异常: {e}")

        # 等待心跳线程结束
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)

        # 等待 WebSocket 线程结束（不能 join 自己）
        if self._ws_thread and self._ws_thread.is_alive() and self._ws_thread is not threading.current_thread():
            self._ws_thread.join(timeout=3.0)

        # 关闭 requests session
        try:
            self.session.close()
        except Exception as e:
            logger.error(f"Session 关闭异常: {e}")

        logger.info(f"直播间抓取已停止: {self.live_id}")
    
    def _emit_message(self, message_type, data):
        """
        发送消息到回调函数
        """
        if self.message_callback:
            try:
                self.message_callback(self.live_id, message_type, data)
            except Exception as e:
                logger.error(f"回调函数错误: {e}", exc_info=True)
    
    def _should_process(self, message_type):
        """
        检查是否应该处理该消息类型
        """
        if self.filter_types is None:
            return True
        return message_type in self.filter_types
    
    @property
    def ttwid(self):
        """
        产生请求头部cookie中的ttwid字段，访问抖音网页版直播间首页可以获取到响应cookie中的ttwid
        :return: ttwid
        """
        if self.__ttwid:
            return self.__ttwid
        headers = {
            "User-Agent": self.user_agent,
        }
        try:
            response = self.session.get(self.live_url, headers=headers, timeout=15)
            response.raise_for_status()
        except Exception as err:
            logger.error(f"【X】请求抖音首页获取 ttwid 失败: {err}")
            return None
        else:
            self.__ttwid = response.cookies.get('ttwid')
            if self.__ttwid:
                logger.debug("成功获取 ttwid")
            else:
                logger.warning("响应中未包含 ttwid cookie")
            return self.__ttwid
    
    @property
    def room_id(self):
        """
        根据直播间的地址获取到真正的直播间roomId，有时会有错误，可以重试请求解决
        :return:room_id
        """
        if self.__room_id:
            return self.__room_id
        url = self.live_url + self.live_id
        headers = {
            "User-Agent": self.user_agent,
            "cookie": f"ttwid={self.ttwid}&msToken={generateMsToken()}; __ac_nonce=0123407cc00a9e438deb4",
        }
        try:
            response = self.session.get(url, headers=headers, timeout=15)
            response.raise_for_status()
        except Exception as err:
            logger.error("【X】请求直播间URL错误", exc_info=True)
        else:
            match = re.search(r'roomId\\":\\"(\d+)\\"', response.text)
            if match is None or len(match.groups()) < 1:
                logger.warning("【X】响应中未找到 roomId，请检查直播间ID是否正确")
                # 不设置 self.__room_id，留空让重试或后续操作失败
                return None

            self.__room_id = match.group(1)
            logger.info(f"解析到 room_id: {self.__room_id}")
            return self.__room_id
    
    def get_ac_nonce(self):
        """
        获取 __ac_nonce
        """
        try:
            resp_cookies = self.session.get(self.host, headers=self.headers, timeout=10).cookies
            return resp_cookies.get("__ac_nonce")
        except Exception as e:
            logger.warning(f"获取 __ac_nonce 失败: {e}")
            return None
    
    def get_ac_signature(self, __ac_nonce: str = None) -> str:
        """
        获取 __ac_signature
        """
        __ac_signature = get__ac_signature(self.host[8:], __ac_nonce, self.user_agent)
        self.session.cookies.set("__ac_signature", __ac_signature)
        return __ac_signature
    
    def get_a_bogus(self, url_params: dict):
        """
        获取 a_bogus
        """
        url = urllib.parse.urlencode(url_params)
        ctx = execute_js(self.abogus_file)
        _a_bogus = ctx.call("get_ab", url, self.user_agent)
        return _a_bogus
    
    def get_room_status(self):
        """
        获取直播间开播状态:
        room_status: 2 直播已结束
        room_status: 0 直播进行中
        """
        try:
            msToken = generateMsToken()
            nonce = self.get_ac_nonce()
            if not nonce:
                logger.warning("获取 __ac_nonce 为空，跳过状态查询")
                return
            signature = self.get_ac_signature(nonce)
            room_id = self.room_id
            if not room_id:
                logger.warning("room_id 为空，跳过状态查询")
                return
        except Exception as e:
            logger.error(f"获取状态前置信息失败: {e}")
            return

        try:
            url = ('https://live.douyin.com/webcast/room/web/enter/?aid=6383'
                   '&app_name=douyin_web&live_id=1&device_platform=web&language=zh-CN&enter_from=page_refresh'
                   '&cookie_enabled=true&screen_width=5120&screen_height=1440&browser_language=zh-CN&browser_platform=Win32'
                   '&browser_name=Edge&browser_version=140.0.0.0'
                   f'&web_rid={self.live_id}'
                   f'&room_id_str={room_id}'
                   '&enter_source=&is_need_double_stream=false&insert_task_id=&live_reason=&msToken=' + msToken)
            query = parse_url(url).query
            params = {i[0]: i[1] for i in [j.split('=') for j in query.split('&')]}
            a_bogus = self.get_a_bogus(params)  # 计算a_bogus,成功率不是100%，出现失败时重试即可
            url += f"&a_bogus={a_bogus}"
            headers = self.headers.copy()
            headers.update({
                'Referer': f'https://live.douyin.com/{self.live_id}',
                'Cookie': f'ttwid={self.ttwid};__ac_nonce={nonce}; __ac_signature={signature}',
            })
            resp = self.session.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json().get('data')
            if data:
                room_status = data.get('room_status')
                user = data.get('user')
                if user:
                    user_id = user.get('id_str', '未知')
                    nickname = user.get('nickname', '未知')
                else:
                    user_id = '未知'
                    nickname = '未知'
                status_text = '正在直播' if not room_status else '已结束'
                logger.info(f"【{nickname}】[{user_id}]直播间：{status_text}.")
        except requests.RequestException as e:
            logger.warning(f"查询直播间状态网络请求失败: {e}")
        except Exception as e:
            logger.warning(f"查询直播间状态失败: {e}")
    
    def _connectWebSocket(self):
        """
        连接抖音直播间websocket服务器，请求直播间数据
        """
        # 先获取 room_id（可能触发网络请求）
        try:
            room_id = self.room_id
        except Exception as e:
            logger.error(f"获取 room_id 失败: {e}", exc_info=True)
            self._emit_message('error', {'message': f'获取 room_id 失败: {e}'})
            self.stop()
            return

        if not room_id:
            logger.error("无法获取 room_id，请检查直播间 ID 是否正确或网络连接")
            self._emit_message('error', {'message': '无法获取 room_id，请检查直播间 ID 或网络'})
            self.stop()
            return

        try:
            wss = ("wss://webcast100-ws-web-lq.douyin.com/webcast/im/push/v2/?app_name=douyin_web"
                   "&version_code=180800&webcast_sdk_version=1.0.14-beta.0"
                   "&update_version_code=1.0.14-beta.0&compress=gzip&device_platform=web&cookie_enabled=true"
                   "&screen_width=1536&screen_height=864&browser_language=zh-CN&browser_platform=Win32"
                   "&browser_name=Mozilla"
                   "&browser_version=5.0%20(Windows%20NT%2010.0;%20Win64;%20x64)%20AppleWebKit/537.36%20(KHTML,"
                   "%20like%20Gecko)%20Chrome/126.0.0.0%20Safari/537.36"
                   "&browser_online=true&tz_name=Asia/Shanghai"
                   "&cursor=d-1_u-1_fh-7392091211001140287_t-1721106114633_r-1"
                   f"&internal_ext=internal_src:dim|wss_push_room_id:{room_id}|wss_push_did:7319483754668557238"
                   f"|first_req_ms:1721106114541|fetch_time:1721106114633|seq:1|wss_info:0-1721106114633-0-0|"
                   f"wrds_v:7392094459690748497"
                   f"&host=https://live.douyin.com&aid=6383&live_id=1&did_rule=3&endpoint=live_pc&support_wrds=1"
                   f"&user_unique_id=7319483754668557238&im_path=/webcast/im/fetch/&identity=audience"
                   f"&need_persist_msg_count=15&insert_task_id=&live_reason=&room_id={room_id}&heartbeatDuration=0")

            # 生成签名
            try:
                signature = generateSignature(wss)
                wss += f"&signature={signature}"
            except FileNotFoundError as sig_err:
                logger.error(f"签名脚本文件缺失，无法连接: {sig_err}")
                self._emit_message('error', {'message': f'签名脚本文件缺失: {sig_err}，请检查打包是否完整'})
                self.stop()
                return
            except Exception as sig_err:
                logger.error(f"生成 WebSocket 签名失败: {sig_err}", exc_info=True)
                self._emit_message('error', {'message': f'签名生成失败: {sig_err}，请检查 py_mini_racer 是否正常'})
                self.stop()
                return

            headers = {
                "cookie": f"ttwid={self.ttwid}",
                'user-agent': self.user_agent,
            }
            self.ws = websocket.WebSocketApp(wss,
                                             header=headers,
                                             on_open=self._wsOnOpen,
                                             on_message=self._wsOnMessage,
                                             on_error=self._wsOnError,
                                             on_close=self._wsOnClose)
            logger.info(f"开始连接抖音 WebSocket (room_id={room_id})")
            self.ws.run_forever()
        except Exception as e:
            logger.error(f"WebSocket 连接错误: {e}", exc_info=True)
            self._emit_message('error', {'message': str(e)})
            self.stop()
    
    def _sendHeartbeat(self):
        """
        发送心跳包
        """
        logger.debug("心跳线程已启动")
        while not self._heartbeat_stop_event.is_set():
            try:
                if not self.running:
                    break
                heartbeat = PushFrame(payload_type='hb').SerializeToString()
                if self.ws:
                    self.ws.send(heartbeat, websocket.ABNF.OPCODE_PING)
            except Exception as e:
                logger.error(f"心跳包发送错误: {e}")
                if not self.running:
                    break
            # 使用可中断的等待
            if self._heartbeat_stop_event.wait(timeout=5.0):
                break
        logger.debug("心跳线程已停止")

    def _wsOnOpen(self, ws):
        """
        连接建立成功
        """
        logger.info("【√】WebSocket 连接成功")
        self._heartbeat_stop_event.clear()
        self._heartbeat_thread = threading.Thread(target=self._sendHeartbeat, daemon=True,
                                                   name=f"hb-{self.live_id}")
        self._heartbeat_thread.start()
    
    def _wsOnMessage(self, ws, message):
        """
        接收到数据
        :param ws: websocket实例
        :param message: 数据
        """
        if not self.running:
            return
        
        # 根据proto结构体解析对象
        package = PushFrame().parse(message)
        response = Response().parse(gzip.decompress(package.payload))
        
        # 返回直播间服务器链接存活确认消息，便于持续获取数据
        if response.need_ack:
            ack = PushFrame(log_id=package.log_id,
                            payload_type='ack',
                            payload=response.internal_ext.encode('utf-8')
                            ).SerializeToString()
            ws.send(ack, websocket.ABNF.OPCODE_BINARY)
        
        # 根据消息类别解析消息体
        for msg in response.messages_list:
            method = msg.method
            if not self._should_process(method):
                continue
            try:
                {
                    'WebcastChatMessage': self._parseChatMsg,  # 聊天消息
                    'WebcastGiftMessage': self._parseGiftMsg,  # 礼物消息
                    'WebcastLikeMessage': self._parseLikeMsg,  # 点赞消息
                    'WebcastMemberMessage': self._parseMemberMsg,  # 进入直播间消息
                    'WebcastSocialMessage': self._parseSocialMsg,  # 关注消息
                    'WebcastRoomUserSeqMessage': self._parseRoomUserSeqMsg,  # 直播间统计
                    'WebcastFansclubMessage': self._parseFansclubMsg,  # 粉丝团消息
                    'WebcastControlMessage': self._parseControlMsg,  # 直播间状态消息
                    'WebcastEmojiChatMessage': self._parseEmojiChatMsg,  # 聊天表情包消息
                    'WebcastRoomStatsMessage': self._parseRoomStatsMsg,  # 直播间统计信息
                    'WebcastRoomMessage': self._parseRoomMsg,  # 直播间信息
                    'WebcastRoomRankMessage': self._parseRankMsg,  # 直播间排行榜信息
                    'WebcastRoomStreamAdaptationMessage': self._parseRoomStreamAdaptationMsg,  # 直播间流配置
                }.get(method)(msg.payload)
            except Exception:
                pass
    
    def _wsOnError(self, ws, error):
        logger.error(f"WebSocket 错误: {error}")
        self._emit_message('ws_error', {'message': str(error)})
    
    def _wsOnClose(self, ws, *args):
        try:
            self.get_room_status()
        except Exception as e:
            logger.debug(f"获取直播间状态失败（非关键）: {e}")
        logger.info("WebSocket 连接已关闭")
    
    def _parseChatMsg(self, payload):
        """聊天消息"""
        message = ChatMessage().parse(payload)
        user_name = message.user.nick_name
        user_id = message.user.id
        content = message.content
        # 解析 rtf_content 检测嵌入表情
        has_image_emoji = False
        has_text_emoji = False
        emoji_details = []
        if message.rtf_content and message.rtf_content.pieces_list:
            for piece in message.rtf_content.pieces_list:
                if piece.image_value and piece.image_value.image:
                    has_image_emoji = True
                    emoji_details.append({'type': 'image_emoji', 'text': piece.string_value or ''})
                if piece.pattern_ref_value and piece.pattern_ref_value.key:
                    has_text_emoji = True
                    emoji_details.append({'type': 'text_emoji', 'text': piece.pattern_ref_value.default_pattern or piece.string_value or ''})
        data = {
            'type': 'chat',
            'user_name': user_name,
            'user_id': user_id,
            'content': content,
            'has_image_emoji': has_image_emoji,
            'has_text_emoji': has_text_emoji,
            'emoji_details': emoji_details,
        }
        print(f"【聊天msg】[{user_id}]{user_name}: {content}")
        self._emit_message('WebcastChatMessage', data)
    
    def _parseGiftMsg(self, payload):
        """礼物消息"""
        message = GiftMessage().parse(payload)
        user_name = message.user.nick_name
        gift_name = message.gift.name
        gift_cnt = message.combo_count
        data = {
            'type': 'gift',
            'user_name': user_name,
            'gift_name': gift_name,
            'gift_count': gift_cnt
        }
        print(f"【礼物msg】{user_name} 送出了 {gift_name}x{gift_cnt}")
        self._emit_message('WebcastGiftMessage', data)
    
    def _parseLikeMsg(self, payload):
        '''点赞消息'''
        message = LikeMessage().parse(payload)
        user_name = message.user.nick_name
        count = message.count
        data = {
            'type': 'like',
            'user_name': user_name,
            'count': count
        }
        print(f"【点赞msg】{user_name} 点了{count}个赞")
        self._emit_message('WebcastLikeMessage', data)
    
    def _parseMemberMsg(self, payload):
        '''进入直播间消息'''
        message = MemberMessage().parse(payload)
        user_name = message.user.nick_name
        user_id = message.user.id
        gender = ["女", "男"][message.user.gender] if hasattr(message.user, 'gender') else "未知"
        data = {
            'type': 'member',
            'user_name': user_name,
            'user_id': user_id,
            'gender': gender
        }
        print(f"【进场msg】[{user_id}][{gender}]{user_name} 进入了直播间")
        self._emit_message('WebcastMemberMessage', data)
    
    def _parseSocialMsg(self, payload):
        '''关注消息'''
        message = SocialMessage().parse(payload)
        user_name = message.user.nick_name
        user_id = message.user.id
        data = {
            'type': 'social',
            'user_name': user_name,
            'user_id': user_id,
            'action': 'follow'
        }
        print(f"【关注msg】[{user_id}]{user_name} 关注了主播")
        self._emit_message('WebcastSocialMessage', data)
    
    def _parseRoomUserSeqMsg(self, payload):
        '''直播间统计'''
        message = RoomUserSeqMessage().parse(payload)
        current = message.total
        total = message.total_pv_for_anchor
        data = {
            'type': 'room_stats',
            'current_viewers': current,
            'total_viewers': total
        }
        print(f"【统计msg】当前观看人数: {current}, 累计观看人数: {total}")
        self._emit_message('WebcastRoomUserSeqMessage', data)
    
    def _parseFansclubMsg(self, payload):
        '''粉丝团消息'''
        message = FansclubMessage().parse(payload)
        content = message.content
        data = {
            'type': 'fansclub',
            'content': content
        }
        print(f"【粉丝团msg】 {content}")
        self._emit_message('WebcastFansclubMessage', data)
    
    def _parseEmojiChatMsg(self, payload):
        '''聊天表情包消息'''
        message = EmojiChatMessage().parse(payload)
        user_name = message.user.nick_name if message.user else ''
        user_id = message.user.id if message.user else 0
        emoji_id = message.emoji_id
        default_content = message.default_content
        # 判断表情子类型
        has_image = bool(message.background_image and message.background_image.url_list)
        has_emoji_content = bool(message.emoji_content and message.emoji_content.pieces_list)
        if has_image:
            emoji_sub_type = 'image_emoji'
        elif has_emoji_content:
            emoji_sub_type = 'text_emoji'
        else:
            emoji_sub_type = 'image_emoji'  # EmojiChatMessage 默认为图片表情
        data = {
            'type': 'emoji',
            'user_name': user_name,
            'user_id': user_id,
            'emoji_id': emoji_id,
            'default_content': default_content,
            'emoji_sub_type': emoji_sub_type,
        }
        print(f"【聊天表情包id】 {emoji_id}")
        self._emit_message('WebcastEmojiChatMessage', data)
    
    def _parseRoomMsg(self, payload):
        message = RoomMessage().parse(payload)
        common = message.common
        room_id = common.room_id
        data = {
            'type': 'room',
            'room_id': room_id
        }
        print(f"【直播间msg】直播间id:{room_id}")
        self._emit_message('WebcastRoomMessage', data)
    
    def _parseRoomStatsMsg(self, payload):
        message = RoomStatsMessage().parse(payload)
        display_long = message.display_long
        data = {
            'type': 'room_stats_ext',
            'display_long': display_long
        }
        print(f"【直播间统计msg】{display_long}")
        self._emit_message('WebcastRoomStatsMessage', data)
    
    def _parseRankMsg(self, payload):
        message = RoomRankMessage().parse(payload)
        ranks_list = []
        for rank in message.ranks_list:
            ranks_list.append({
                'user_name': rank.user.nick_name if rank.user else '',
                'user_id': rank.user.id if rank.user else 0,
                'score': rank.score_str,
                'profile_hidden': rank.profile_hidden
            })
        data = {
            'type': 'rank',
            'ranks_list': ranks_list
        }
        print(f"【直播间排行榜msg】")
        self._emit_message('WebcastRoomRankMessage', data)
    
    def _parseControlMsg(self, payload):
        '''直播间状态消息'''
        message = ControlMessage().parse(payload)
        data = {
            'type': 'control',
            'status': message.status
        }
        self._emit_message('WebcastControlMessage', data)
        
        if message.status == 3:
            print("直播间已结束")
            self.stop()
    
    def _parseRoomStreamAdaptationMsg(self, payload):
        message = RoomStreamAdaptationMessage().parse(payload)
        adaptationType = message.adaptation_type
        data = {
            'type': 'stream_adaptation',
            'adaptation_type': adaptationType
        }
        print(f'直播间adaptation: {adaptationType}')
        self._emit_message('WebcastRoomStreamAdaptationMessage', data)
