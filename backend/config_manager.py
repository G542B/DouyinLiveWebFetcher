import os
import json
import sys
from typing import Optional


class ConfigManager:
    _instance: Optional['ConfigManager'] = None
    _config_dir: str
    _config_file: str

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # 获取项目根目录
        self._project_root = self._get_project_root()
        self._config_dir = os.path.join(self._project_root, 'config')
        self._config_file = os.path.join(self._config_dir, 'app_config.json')
        
        print(f"[ConfigManager] 项目根目录: {self._project_root}")
        print(f"[ConfigManager] 配置目录: {self._config_dir}")
        
        # 确保配置目录存在
        try:
            os.makedirs(self._config_dir, exist_ok=True)
            print(f"[ConfigManager] 配置目录已创建/存在")
        except Exception as e:
            print(f"[ConfigManager] 创建配置目录失败: {e}")
            # 如果无法在项目根目录创建，尝试使用用户目录
            try:
                user_home = os.path.expanduser("~")
                self._config_dir = os.path.join(user_home, '.douyin_danmaku')
                self._config_file = os.path.join(self._config_dir, 'app_config.json')
                os.makedirs(self._config_dir, exist_ok=True)
                print(f"[ConfigManager] 已切换到用户目录配置: {self._config_dir}")
            except Exception as e2:
                print(f"[ConfigManager] 用户目录配置也失败: {e2}")
    
    def _get_project_root(self) -> str:
        """获取项目根目录，兼容不同运行环境"""
        print(f"[ConfigManager] sys.argv[0]: {sys.argv[0]}")
        print(f"[ConfigManager] sys.executable: {sys.executable}")
        
        # 检查是否是打包环境
        if getattr(sys, 'frozen', False):
            print(f"[ConfigManager] 检测到打包环境")
            # 首先尝试获取当前脚本所在目录（run.py）
            if hasattr(sys, '_MEIPASS'):
                # PyInstaller 打包环境
                print(f"[ConfigManager] PyInstaller _MEIPASS: {sys._MEIPASS}")
                # 对于 electron 打包，app 应该在 resources/app 下
                # 尝试向上查找包含 run.py 的目录
                candidate = os.path.dirname(sys.executable)
                print(f"[ConfigManager] 候选目录 (executable 目录): {candidate}")
                
                # 先尝试查找是否有 resources/app 目录
                resources_app = os.path.join(candidate, 'resources', 'app')
                if os.path.exists(resources_app):
                    print(f"[ConfigManager] 找到 resources/app 目录")
                    return resources_app
                
                # 或者尝试从 sys._MEIPASS 向上查找
                if os.path.exists(sys._MEIPASS):
                    candidate = sys._MEIPASS
                    # 检查是否包含 run.py
                    if os.path.exists(os.path.join(candidate, 'run.py')):
                        print(f"[ConfigManager] 找到包含 run.py 的目录")
                        return candidate
                    
                    # 检查父目录
                    parent = os.path.dirname(candidate)
                    if os.path.exists(os.path.join(parent, 'run.py')):
                        print(f"[ConfigManager] 在父目录找到 run.py")
                        return parent
            
            # 尝试从当前工作目录查找
            cwd = os.getcwd()
            print(f"[ConfigManager] 当前工作目录: {cwd}")
            if os.path.exists(os.path.join(cwd, 'run.py')):
                print(f"[ConfigManager] 在当前工作目录找到 run.py")
                return cwd
            
            # 如果都找不到，尝试使用包含当前模块的目录的父目录
            try:
                current_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.dirname(current_dir)
                print(f"[ConfigManager] 使用模块路径推导: {project_root}")
                return project_root
            except (NameError, Exception):
                pass
        
        # 非打包环境或 fallback
        try:
            # 首先尝试从 __file__ 推导
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            print(f"[ConfigManager] 使用 __file__ 推导: {project_root}")
            return project_root
        except NameError:
            # 如果 __file__ 不可用，使用当前工作目录
            print(f"[ConfigManager] 使用当前工作目录: {os.getcwd()}")
            return os.getcwd()
    
    def get_project_root(self) -> str:
        """获取项目根目录"""
        return self._project_root
    
    def get_resource_path(self, relative_path: str) -> str:
        """获取资源文件的绝对路径"""
        return os.path.join(self._project_root, relative_path)
    
    def load_config(self, key: str, default=None):
        """加载配置项"""
        try:
            if not os.path.exists(self._config_file):
                return default
            with open(self._config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            return config_data.get(key, default)
        except Exception as e:
            print(f"[ConfigManager] 加载配置失败: {e}")
            return default
    
    def save_config(self, key: str, value):
        """保存配置项"""
        config_data = {}
        if os.path.exists(self._config_file):
            try:
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
            except Exception as e:
                print(f"[ConfigManager] 读取现有配置失败: {e}")
        
        config_data[key] = value
        
        try:
            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            print(f"[ConfigManager] 配置已保存: {key}")
        except Exception as e:
            print(f"[ConfigManager] 保存配置失败: {e}")
    
    def load_all_config(self) -> dict:
        """加载所有配置"""
        try:
            if not os.path.exists(self._config_file):
                return {}
            with open(self._config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ConfigManager] 加载所有配置失败: {e}")
            return {}


# 全局实例
config_manager = ConfigManager()
