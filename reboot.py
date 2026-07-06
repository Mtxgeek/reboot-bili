"""
多开浏览器管理器 - 定时重启解决内存泄漏
适用于5800H CPU + 32GB RAM + 2GB显存环境
使用 Trea CN 软件开发
参考 Java StarBotBilibiliLiveOnPlugin 的浏览器刷新逻辑
"""

import os
import sys
import time
import psutil
import logging
from logging.handlers import TimedRotatingFileHandler
import subprocess
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import argparse
import urllib.request
import urllib.error
import urllib.parse

# ====================== 常量定义 ======================
# 默认配置
DEFAULT_RESTART_SECONDS = 3600  # 默认1小时
DEFAULT_MAX_CPU = 80
DEFAULT_MAX_MEMORY = 85
DEFAULT_CONFIG_FILE = 'config.json'
DEFAULT_MONITOR_INTERVAL = 60
DEFAULT_CLEAN_CACHE = False  # 不再清理缓存，使用浏览器默认缓存

# 监控间隔（秒）
MONITOR_INTERVAL = 60
SCHEDULE_CHECK_INTERVAL = 60
START_DELAY = 2  # 浏览器实例启动间隔
STOP_DELAY = 15  # 强制重启前等待时间

# Windows 浏览器配置
DEFAULT_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
]

# Edge浏览器默认路径
DEFAULT_EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
]

# ====================== Chrome DevTools Protocol 配置 ======================
DEFAULT_DEBUG_PORT = 9222
DEBUG_PORT_LOCK = threading.Lock()
CURRENT_DEBUG_PORT = DEFAULT_DEBUG_PORT

# 创建logs文件夹（如果不存在）
logs_dir = 'logs'
os.makedirs(logs_dir, exist_ok=True)

# 配置日志 - 使用TimedRotatingFileHandler实现按天分割
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 创建文件处理器，按天分割日志，文件名格式为 YYYY-MM-DD.log
file_handler = TimedRotatingFileHandler(
    filename=os.path.join(logs_dir, datetime.now().strftime('%Y-%m-%d') + '.log'),
    when='midnight',  # 每天午夜分割
    interval=1,  # 每天分割一次
    backupCount=7,  # 保留7天的备份日志文件
    encoding='utf-8'
)
# 设置文件名后缀格式
file_handler.suffix = '%Y-%m-%d'
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# 创建控制台处理器
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# 移除现有处理器（防止重复）
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# 添加新处理器
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

class BrowserManager:
    def __init__(self, restart_seconds: int = DEFAULT_RESTART_SECONDS, 
                 max_cpu_percent: int = DEFAULT_MAX_CPU, 
                 max_memory_percent: int = DEFAULT_MAX_MEMORY,
                 browser_configs: Optional[List[Dict]] = None,
                 monitor_interval: int = DEFAULT_MONITOR_INTERVAL,
                 clean_cache_on_exit: bool = DEFAULT_CLEAN_CACHE,
                 custom_browser_path: Optional[str] = None,
                 browser_type: int = 0):
        """
        初始化浏览器管理器
        
        Args:
            restart_seconds: 重启间隔（秒）
            max_cpu_percent: CPU使用率阈值（%）
            max_memory_percent: 内存使用率阈值（%）
            browser_configs: 浏览器实例配置列表
            monitor_interval: 资源监控间隔（秒）
            clean_cache_on_exit: 是否在退出时清理缓存
            custom_browser_path: 自定义浏览器路径
            browser_type: 浏览器类型选择（0:自动检测, 1:Edge, 2:Chrome, 3:QQ浏览器）
        """
        self.restart_seconds = restart_seconds
        self.max_cpu_percent = max_cpu_percent
        self.max_memory_percent = max_memory_percent
        self.monitor_interval = monitor_interval
        self.clean_cache_on_exit = clean_cache_on_exit
        self.custom_browser_path = custom_browser_path
        self.browser_type = browser_type  # 添加浏览器类型
        self.browser_processes = []
        self.is_running = False
        # 浏览器启动保护期（秒），期间不进行CPU阈值检查
        self.STARTUP_PROTECTION_PERIOD = 90
        # 记录最后一次启动时间
        self.last_start_time = None
        # 启动锁，防止重复启动
        self.startup_lock = threading.Lock()
        self.is_starting = False
        # 初始化调试端口
        global CURRENT_DEBUG_PORT
        with DEBUG_PORT_LOCK:
            self.debug_port = CURRENT_DEBUG_PORT
            CURRENT_DEBUG_PORT += 1
        logger.info(f"使用调试端口: {self.debug_port}")
        
        # 默认浏览器配置
        self.browser_configs = browser_configs or [
            {
                "name": "默认组1",
                "urls": [
                    "https://www.4399.com",
                    "https://www.acfun.cn",
                    "https://live.bilibili.com"
                ]
            }
        ]
        
        # 只支持 Windows 系统
        if not sys.platform.lower() == "win32":
            logger.error("该脚本仅支持 Windows 10/11 系统")
            sys.exit(1)
        
        # 预先检测浏览器路径，避免重复调用
        self.browser_path = self.detect_browser_path()
        
        # 如果未找到浏览器且不是自动检测模式，尝试自动检测
        if not self.browser_path and self.browser_type != 0:
            logger.warning(f"未找到指定的浏览器类型 {self.browser_type}，尝试自动检测")
            self.browser_type = 0
            self.browser_path = self.detect_browser_path()
        
        # 如果仍然未找到浏览器，退出程序
        if not self.browser_path:
            logger.error("无法找到任何浏览器路径，请确保已安装Chrome、Edge或QQ浏览器")
            sys.exit(1)
        
    def detect_browser_path(self) -> Optional[str]:
        """检测Windows系统Chrome、Edge或QQ浏览器路径"""
        # 优先使用自定义浏览器路径
        if self.custom_browser_path:
            if os.path.exists(self.custom_browser_path):
                logger.info(f"使用自定义浏览器路径: {self.custom_browser_path}")
                return self.custom_browser_path
            else:
                logger.error(f"自定义浏览器路径不存在: {self.custom_browser_path}")
        
        # 根据浏览器类型选择检测顺序
        browser_type = self.browser_type
        browser_names = {1: "Edge", 2: "Chrome"}
        
        # 定义浏览器检测函数
        def detect_edge():
            """检测Edge浏览器"""
            # 检查默认Edge安装路径
            for edge_path in DEFAULT_EDGE_PATHS:
                if os.path.exists(edge_path):
                    logger.info(f"检测到Edge浏览器路径: {edge_path}")
                    return edge_path
            
            # 尝试从注册表获取Edge路径
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe", 0, winreg.KEY_READ) as key:
                    reg_path = winreg.QueryValue(key, None)
                    if os.path.exists(reg_path):
                        logger.info(f"从注册表获取Edge路径: {reg_path}")
                        return reg_path
            except Exception as e:
                logger.error(f"从注册表获取Edge路径失败: {str(e)}")
            return None
        
        def detect_chrome():
            """检测Chrome浏览器"""
            # 检查默认Chrome安装路径
            for chrome_path in DEFAULT_CHROME_PATHS:
                if os.path.exists(chrome_path):
                    logger.info(f"检测到Chrome浏览器路径: {chrome_path}")
                    return chrome_path
            
            # 尝试从注册表获取Chrome路径
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe", 0, winreg.KEY_READ) as key:
                    reg_path = winreg.QueryValue(key, None)
                    if os.path.exists(reg_path):
                        logger.info(f"从注册表获取Chrome路径: {reg_path}")
                        return reg_path
            except Exception as e:
                logger.error(f"从注册表获取Chrome路径失败: {str(e)}")
            return None
        
        # 根据browser_type选择检测顺序
        if browser_type == 0:
            # 自动检测：先Edge（系统自带），再Chrome
            logger.info("浏览器类型设置为自动检测，按Edge -> Chrome顺序检测")
            edge_path = detect_edge()
            if edge_path:
                return edge_path
            chrome_path = detect_chrome()
            if chrome_path:
                return chrome_path
        elif browser_type == 1:
            # 仅检测Edge
            logger.info("浏览器类型设置为Edge，仅检测Edge浏览器")
            edge_path = detect_edge()
            if edge_path:
                return edge_path
        elif browser_type == 2:
            # 仅检测Chrome
            logger.info("浏览器类型设置为Chrome，仅检测Chrome浏览器")
            chrome_path = detect_chrome()
            if chrome_path:
                return chrome_path
        else:
            logger.error(f"无效的浏览器类型: {browser_type}，使用自动检测")
            # 自动检测
            edge_path = detect_edge()
            if edge_path:
                return edge_path
            chrome_path = detect_chrome()
            if chrome_path:
                return chrome_path
        
        logger.error("未找到指定的浏览器路径，请确保已安装对应浏览器")
        return None
    
    def get_default_user_data_dir(self) -> Optional[str]:
        """获取浏览器默认用户数据目录，确保使用现有账户的cookie"""
        try:
            appdata_local = os.environ.get('LOCALAPPDATA', '')
            if 'chrome' in self.browser_path.lower():
                return os.path.join(appdata_local, 'Google', 'Chrome', 'User Data')
            elif 'edge' in self.browser_path.lower():
                return os.path.join(appdata_local, 'Microsoft', 'Edge', 'User Data')
        except Exception as e:
            logger.warning(f"获取默认用户数据目录失败: {str(e)}")
        return None

    def create_browser_args(self, url: str) -> List[str]:
        """创建浏览器启动参数，使用默认用户数据目录保留cookie，添加远程调试端口"""
        if not self.browser_path:
            raise FileNotFoundError("浏览器路径未找到")
        
        is_chrome = 'chrome' in self.browser_path.lower()
        
        args = [
            self.browser_path,
            "--remote-debugging-address=127.0.0.1",
            f"--remote-debugging-port={self.debug_port}",
        ]
        
        user_data_dir = self.get_default_user_data_dir()
        if user_data_dir:
            args.append(f"--user-data-dir={user_data_dir}")
            args.append("--profile-directory=Default")
        
        args.extend([
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-extensions",
            "--disable-plugins",
            "--disable-popup-blocking",
        ])
        
        if is_chrome:
            args.extend([
                "--enable-automation",
                "--disable-infobars",
                "--disable-site-isolation-trials",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-blink-features=AutomationControlled",
            ])
        
        args.append(url)
        
        return args
    
    def open_urls_in_tabs(self, profile_idx: int, urls: List[str]) -> None:
        """启动浏览器并通过CDP打开多个URL，先打开about:blank等待CDP就绪"""
        try:
            if not urls:
                logger.warning(f"浏览器实例 {profile_idx} 的URL列表为空，跳过启动")
                return
            
            logger.info(f"为浏览器实例 {profile_idx} 打开 {len(urls)} 个窗口...")
            
            args = self.create_browser_args("about:blank")
            
            logger.info("启动浏览器窗口，先打开about:blank等待CDP就绪...")
            
            process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            )
            
            self.browser_processes.append(process)
            logger.info(f"浏览器窗口已启动 (PID: {process.pid})")
            
            logger.info("等待CDP就绪...")
            if self.is_devtools_ready(max_retries=30, retry_delay=1.0):
                logger.info("CDP就绪，开始通过CDP打开配置的URL")
                
                for url in urls:
                    try:
                        response = self.send_cdp_request("GET", f"/json/new?{urllib.parse.quote(url, safe='')}")
                        if response:
                            logger.info(f"通过CDP打开URL成功: {url}")
                        else:
                            logger.warning(f"通过CDP打开URL失败: {url}")
                    except Exception as e:
                        logger.warning(f"CDP打开URL出错: {url} - {str(e)}")
            else:
                logger.warning("CDP不可用，回退到subprocess方式打开URL")
                for url in urls:
                    try:
                        args = self.create_browser_args(url)
                        process = subprocess.Popen(
                            args,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
                        )
                        self.browser_processes.append(process)
                        logger.info(f"通过subprocess打开URL: {url} (PID: {process.pid})")
                        time.sleep(START_DELAY)
                    except Exception as e:
                        logger.error(f"打开URL {url} 失败：{str(e)}")
            
            logger.info(f"所有窗口已启动")
            
        except Exception as e:
            logger.error(f"处理浏览器实例 {profile_idx} 时出错：{str(e)}")
            logger.exception("处理浏览器实例错误堆栈:")
            return
    
    def monitor_resources(self):
        """监控系统资源使用情况"""
        while self.is_running:
            try:
                # 获取系统资源使用情况
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                
                logger.info(f"系统资源 - CPU: {cpu_percent}%, 内存: {memory.percent}%")
                
                # 检查是否处于浏览器启动保护期
                in_startup_protection = False
                if self.last_start_time:
                    elapsed = (datetime.now() - self.last_start_time).total_seconds()
                    if elapsed < self.STARTUP_PROTECTION_PERIOD:
                        in_startup_protection = True
                        logger.info(f"处于浏览器启动保护期 ({elapsed:.1f}秒 < {self.STARTUP_PROTECTION_PERIOD}秒)，跳过CPU阈值检查")
                
                # 检查是否超过阈值（启动保护期内跳过CPU检查）
                if not in_startup_protection and cpu_percent > self.max_cpu_percent:
                    logger.warning(f"CPU使用率过高: {cpu_percent}% > {self.max_cpu_percent}%")
                    self.force_restart("CPU使用率过高")
                    
                if memory.percent > self.max_memory_percent:
                    logger.warning(f"内存使用率过高: {memory.percent}% > {self.max_memory_percent}%")
                    self.force_restart("内存使用率过高")
                    
                # 监控浏览器进程
                self.check_browser_processes()
                
                # 健康检查：如果浏览器进程全部退出，重新启动
                # 检查 is_starting 标志，防止重复启动
                if not self.browser_processes and self.browser_configs and not self.is_starting:
                    logger.warning("所有浏览器进程已退出，准备重新启动...")
                    # 先确保完全停止所有进程（包括残留）
                    self.stop_all_browsers(cleanup_residual=True)
                    # 等待短暂时间，确保资源完全释放
                    time.sleep(5)
                    # 再重新启动
                    self.start_all_browsers()
                
                time.sleep(self.monitor_interval)
                
            except psutil.AccessDenied as e:
                logger.error(f"监控过程中权限不足: {str(e)}")
                time.sleep(self.monitor_interval)
            except psutil.NoSuchProcess as e:
                logger.error(f"监控过程中进程不存在: {str(e)}")
                time.sleep(self.monitor_interval)
            except Exception as e:
                logger.error(f"监控过程中出错: {str(e)}")
                # 记录完整错误堆栈
                logger.exception("监控错误堆栈:")
                time.sleep(self.monitor_interval)
    
    def check_browser_processes(self):
        """检查浏览器进程状态，适配Chrome/Edge/QQ浏览器多进程架构"""
        # 对于浏览器的多进程架构，直接启动返回的进程可能很快退出
        # 我们只需要检查是否还有当前使用的浏览器进程在运行即可
        
        # 如果浏览器路径为None，直接清空进程列表
        if not self.browser_path:
            self.browser_processes.clear()
            return
        
        # 检查系统中是否还有当前使用的浏览器进程在运行
        browser_running = False
        try:
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    name = proc.info['name'] or ''
                    exe = proc.info['exe'] or ''
                    
                    # 根据当前使用的浏览器类型检查对应进程
                    browser_path_lower = self.browser_path.lower()
                    if 'chrome' in browser_path_lower:
                        # 检查Chrome进程
                        if ('chrome.exe' in name.lower()) and ('chrome' in exe.lower()):
                            browser_running = True
                            break
                    elif 'msedge' in browser_path_lower:
                        # 检查Edge进程
                        if ('msedge.exe' in name.lower()) and ('msedge' in exe.lower()):
                            browser_running = True
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.error(f"检查系统进程时出错: {str(e)}")
        
        # 如果没有浏览器进程在运行，清空进程列表
        if not browser_running:
            self.browser_processes.clear()
        else:
            # 保留至少一个进程在列表中，避免健康检查触发重启
            if not self.browser_processes:
                # 创建一个虚拟进程对象，只用于占位
                class DummyProcess:
                    def poll(self):
                        return None
                self.browser_processes.append(DummyProcess())
        
        # 不再记录单个进程退出信息，避免误报
        return
    
    def force_restart(self, reason: str = "资源使用过高"):
        """使用 CDP 刷新浏览器页面，而不是强制 kill 进程"""
        logger.warning(f"刷新所有浏览器页面 - 原因: {reason}")
        
        # 使用启动锁防止重复启动
        with self.startup_lock:
            if self.is_starting:
                logger.warning("浏览器正在启动中，跳过重复重启")
                return
            self.is_starting = True
            
            try:
                # 使用 CDP 刷新所有页面
                if self.is_devtools_ready():
                    self.refresh_all_pages()
                else:
                    # 如果 CDP 不可用，回退到强制重启
                    logger.warning("CDP 不可用，回退到强制重启")
                    try:
                        self.stop_all_browsers(cleanup_residual=True)
                    except Exception as e:
                        logger.error(f"停止浏览器进程失败，继续尝试启动: {str(e)}")
                    time.sleep(STOP_DELAY)
                    try:
                        self._start_browsers_internal()
                    except Exception as e:
                        logger.error(f"启动浏览器进程失败: {str(e)}")
                        logger.exception("启动浏览器错误堆栈:")
            finally:
                self.is_starting = False
    
    def restart_with_configured_urls(self):
        """按照配置的URL数量重新启动浏览器，确保窗口数量与配置一致"""
        logger.info("按照配置的URL数量重新启动浏览器...")
        # 停止所有浏览器进程（包括残留）
        self.stop_all_browsers(cleanup_residual=True)
        # 等待进程完全退出
        time.sleep(STOP_DELAY)
        # 按照配置的URL数量重新启动
        self.start_all_browsers()
    
    def stop_all_browsers(self, cleanup_residual: bool = False):
        """停止所有浏览器进程，确保进程完全退出
        
        Args:
            cleanup_residual: 是否清理残留的浏览器进程，默认False表示不清理
        """
        logger.info("正在停止所有浏览器进程...")
        
        try:
            # 尝试使用 CDP 优雅关闭页面（使用静默模式，避免产生警告日志）
            try:
                if self.is_devtools_ready(silent=True):
                    self.close_all_pages()
                    logger.debug("已通过CDP关闭所有页面")
            except Exception as e:
                # 静默失败，直接使用进程终止方式，不记录警告日志
                logger.debug(f"CDP关闭页面失败，使用进程终止方式: {str(e)}")
            
            # 根据参数决定是否清理残留进程
            if cleanup_residual:
                # 清理浏览器残留进程
                try:
                    self.cleanup_chrome_processes()
                except Exception as e:
                    logger.warning(f"清理浏览器进程时发生错误，继续执行: {str(e)}")
                
                # 等待进程完全退出
                try:
                    self.wait_for_process_exit()
                except Exception as e:
                    logger.warning(f"等待进程退出时发生错误，继续执行: {str(e)}")
            
            # 清空浏览器进程记录
            self.browser_processes.clear()
            
            logger.info("停止所有浏览器进程完成")
        except Exception as e:
            logger.error(f"停止浏览器进程时发生错误: {str(e)}")
            logger.exception("停止浏览器进程错误堆栈:")
            # 即使发生错误，也要清空进程记录，确保可以重新启动
            self.browser_processes.clear()
    
    def wait_for_process_exit(self):
        """等待浏览器进程完全退出"""
        max_wait_seconds = 15
        check_interval = 2
        elapsed = 0
        
        while elapsed < max_wait_seconds:
            browser_running = self.is_browser_process_running()
            if not browser_running:
                logger.info("所有浏览器进程已退出")
                return
            logger.info(f"等待浏览器进程退出... ({elapsed}/{max_wait_seconds}秒)")
            time.sleep(check_interval)
            elapsed += check_interval
        
        logger.warning(f"等待 {max_wait_seconds} 秒后仍有浏览器进程，强制继续")
    
    def is_browser_process_running(self):
        """检查是否有浏览器进程在运行"""
        if not self.browser_path:
            return False
        
        browser_path_lower = self.browser_path.lower()
        try:
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    name = proc.info['name'] or ''
                    exe = proc.info['exe'] or ''
                    
                    if 'chrome' in browser_path_lower:
                        if ('chrome.exe' in name.lower()) and ('chrome' in exe.lower()):
                            return True
                    elif 'msedge' in browser_path_lower:
                        if ('msedge.exe' in name.lower()) and ('msedge' in exe.lower()):
                            return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.error(f"检查浏览器进程时出错: {str(e)}")
        
        return False
    
    def get_devtools_base_url(self):
        """获取 DevTools 基础 URL"""
        return f"http://127.0.0.1:{self.debug_port}"
    
    def send_cdp_request(self, method: str, path: str) -> Optional[str]:
        """发送 CDP 请求"""
        try:
            url = f"{self.get_devtools_base_url()}{path}"
            req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.read().decode('utf-8')
        except urllib.error.URLError as e:
            logger.debug(f"CDP 请求失败: {e}")
            return None
        except Exception as e:
            logger.debug(f"CDP 请求异常: {e}")
            return None
    
    def is_devtools_ready(self, max_retries: int = 3, retry_delay: float = 1.0, silent: bool = False) -> bool:
        """检查 DevTools 是否可用，支持重试机制
        
        Args:
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）
            silent: 是否静默模式（不记录警告日志）
            
        Returns:
            True if DevTools is ready, False otherwise
        """
        for attempt in range(max_retries):
            response = self.send_cdp_request("GET", "/json/version")
            if response is not None:
                if attempt > 0 and not silent:
                    logger.info(f"CDP 连接成功（第 {attempt + 1} 次尝试）")
                return True
            logger.debug(f"CDP 连接失败，第 {attempt + 1}/{max_retries} 次尝试")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
        
        if not silent:
            logger.warning(f"CDP 连接失败，已尝试 {max_retries} 次，端口: {self.debug_port}")
            # 检查端口是否被占用
            self._check_port_status()
        return False
    
    def _check_port_status(self):
        """检查调试端口状态，帮助诊断CDP失败原因"""
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', self.debug_port))
            if result == 0:
                logger.warning(f"端口 {self.debug_port} 已被占用，但CDP不可用")
            else:
                logger.warning(f"端口 {self.debug_port} 未被监听")
            sock.close()
        except Exception as e:
            logger.error(f"检查端口状态失败: {str(e)}")
    
    def list_page_targets(self) -> List[Dict]:
        """列出所有页面目标"""
        response = self.send_cdp_request("GET", "/json/list")
        if not response:
            return []
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return []
    
    def reload_target(self, target_id: str) -> bool:
        """刷新指定的页面目标"""
        response = self.send_cdp_request("GET", f"/json/reload/{target_id}")
        return response is not None
    
    def close_target(self, target_id: str) -> bool:
        """关闭指定的页面目标"""
        response = self.send_cdp_request("GET", f"/json/close/{target_id}")
        return response is not None
    
    def refresh_all_pages(self):
        """按照配置的URL数量重新加载浏览器，确保窗口数量与配置一致"""
        targets = self.list_page_targets()
        page_count = sum(1 for t in targets if t.get('type') == 'page')
        logger.info(f"找到 {len(targets)} 个页面目标，其中 {page_count} 个页面")
        
        # 先关闭所有现有页面（排除浏览器默认标签页，避免关闭后浏览器重启时自动打开）
        for target in targets:
            target_id = target.get('id')
            target_type = target.get('type')
            target_url = target.get('url')
            
            if target_type == 'page' and target_id:
                # 跳过浏览器默认的newtab页面，让浏览器自己管理
                if target_url and (target_url.startswith('edge://newtab') or target_url.startswith('chrome://newtab')):
                    logger.info(f"跳过浏览器默认标签页: {target_url}")
                    continue
                    
                logger.info(f"关闭页面: {target_url} (target_id: {target_id})")
                if self.close_target(target_id):
                    time.sleep(0.5)
                    if self.is_target_closed(target_id):
                        logger.info(f"页面已关闭: {target_url}")
                    else:
                        logger.warning(f"页面未真正关闭: {target_url}")
                else:
                    logger.warning(f"关闭页面失败: {target_url}")
        
        # 等待页面关闭
        time.sleep(1)
        
        # 按照配置的URL数量重新打开，而不是按现有窗口数量
        logger.info(f"按照配置重新打开 {len(self.browser_configs)} 个浏览器实例...")
        for idx, config in enumerate(self.browser_configs):
            urls = config.get('urls', [])
            logger.info(f"打开 {config['name']}: {len(urls)} 个URL")
            for url in urls:
                logger.info(f"打开URL: {url}")
                self.open_url(url)
                time.sleep(START_DELAY)
        
        # 计算配置的总URL数量
        total_urls = sum(len(config.get('urls', [])) for config in self.browser_configs)
        if total_urls > 0:
            logger.info(f"所有页面已重新打开")
    
    def close_all_pages(self):
        """关闭所有页面"""
        targets = self.list_page_targets()
        logger.info(f"找到 {len(targets)} 个页面目标")
        
        for target in targets:
            target_id = target.get('id')
            target_type = target.get('type')
            target_url = target.get('url')
            
            if target_type == 'page' and target_id:
                logger.info(f"关闭页面: {target_url} (target_id: {target_id})")
                if self.close_target(target_id):
                    # 验证是否真的关闭了
                    if self.is_target_closed(target_id):
                        logger.info(f"成功关闭页面: {target_url}")
                    else:
                        logger.warning(f"页面未真正关闭: {target_url}")
                else:
                    logger.warning(f"关闭页面失败: {target_url}")
    
    def is_target_closed(self, target_id: str) -> bool:
        """验证目标是否真的关闭了"""
        time.sleep(1)  # 等待1秒让页面关闭
        targets = self.list_page_targets()
        for target in targets:
            if target.get('id') == target_id:
                return False
        return True
    
    def open_url(self, url: str) -> Optional[str]:
        """使用 subprocess 启动新浏览器窗口打开页面，确保使用新窗口而不是新标签页"""
        try:
            args = [
                self.browser_path,
                "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={self.debug_port}",
                "--new-window",
            ]
            
            # Chrome需要额外的参数来启用CDP
            if 'chrome' in self.browser_path.lower():
                args.extend([
                    "--enable-automation",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-infobars",
                ])
            
            args.append(url)
            
            process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            )
            
            self.browser_processes.append(process)
            logger.info(f"成功打开页面: {url} (PID: {process.pid})")
            time.sleep(START_DELAY)
            
            return str(process.pid)
        except Exception as e:
            logger.error(f"打开页面失败: {url}, 错误: {e}")
            return None
    
    def cleanup_chrome_processes(self):
        """清理残留的浏览器进程，但只清理当前使用的浏览器类型"""
        try:
            # 如果浏览器路径为None，不清理任何进程
            if not self.browser_path:
                logger.warning("浏览器路径为None，跳过进程清理")
                return
            
            for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
                try:
                    # 跳过当前脚本进程
                    if proc.pid == os.getpid():
                        continue
                    
                    # 获取进程信息
                    name = proc.info['name'] or ''
                    
                    # 跳过msedgewebview2.exe进程
                    if 'msedgewebview2.exe' in name.lower():
                        continue
                    
                    # 跳过chrome.exe进程中的webview2相关进程
                    exe = proc.info['exe'] or ''
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    
                    # 清理当前使用的浏览器进程，排除Steam等其他进程
                    is_browser = False
                    browser_type = "unknown"
                    
                    # 根据当前使用的浏览器类型，只清理对应类型的进程
                    browser_path_lower = self.browser_path.lower()
                    if 'chrome' in browser_path_lower:
                        # 只清理Chrome进程
                        if 'chrome' in name.lower() and 'steam' not in name.lower():
                            if 'chrome' in exe.lower() or 'chrome' in cmdline.lower():
                                if 'steam' not in exe.lower() and 'steam' not in cmdline.lower():
                                    is_browser = True
                                    browser_type = "Chrome"
                    elif 'msedge' in browser_path_lower:
                        # 只清理Edge进程
                        if 'msedge.exe' in name.lower():
                            if 'msedge' in exe.lower() or 'edge' in exe.lower() or 'msedge' in cmdline.lower():
                                if 'steam' not in exe.lower() and 'steam' not in cmdline.lower():
                                    is_browser = True
                                    browser_type = "Edge"

                    
                    if is_browser:
                        proc.terminate()
                        logger.info(f"清理残留{browser_type}进程: {proc.pid}, 名称: {name}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    # 忽略没有权限或不存在的进程
                    pass
                except Exception as e:
                    logger.error(f"检查进程 {proc.pid} 时出错: {str(e)}")
        except Exception as e:
            logger.error(f"清理浏览器进程时出错: {str(e)}")
    
    def start_all_browsers(self):
        """启动所有配置的浏览器实例，使用启动锁防止重复启动"""
        # 使用启动锁防止重复启动
        with self.startup_lock:
            if self.is_starting:
                logger.warning("浏览器正在启动中，跳过重复启动")
                return
            self.is_starting = True
            
            try:
                self._start_browsers_internal()
            finally:
                self.is_starting = False
    
    def _start_browsers_internal(self):
        """内部方法：启动所有配置的浏览器实例（不带锁）"""
        logger.info(f"启动 {len(self.browser_configs)} 个浏览器实例...")
        
        # 启动前清理所有浏览器进程，确保新进程可以正常绑定CDP端口
        logger.info("启动前清理浏览器进程...")
        self.cleanup_chrome_processes()
        time.sleep(2)
        
        # 记录浏览器启动时间
        self.last_start_time = datetime.now()
        
        # 清空之前的进程列表
        self.browser_processes.clear()
        
        for idx, config in enumerate(self.browser_configs):
            logger.info(f"打开 {config['name']}: {config['urls']}")
            # 每个URL使用单独窗口打开
            self.open_urls_in_tabs(idx + 1, config['urls'])
            
            # 避免同时启动所有实例造成资源冲击
            time.sleep(START_DELAY)  # 实例间启动间隔
        
        # 启动完成后校验页面数量
        self.validate_and_adjust_page_count()
    
    def validate_and_adjust_page_count(self):
        """校验并调整页面数量，确保与配置一致"""
        # 计算配置的总URL数量
        expected_count = sum(len(config.get('urls', [])) for config in self.browser_configs)
        
        if expected_count == 0:
            return
        
        # 等待页面启动完成
        time.sleep(3)
        
        # 检查CDP是否可用
        if not self.is_devtools_ready(silent=True):
            logger.debug("CDP不可用，跳过页面数量校验")
            return
        
        # 获取当前打开的页面列表
        targets = self.list_page_targets()
        
        # 过滤出实际的页面（排除浏览器默认页面如newtab）
        current_pages = []
        default_pages = []
        for t in targets:
            if t.get('type') == 'page':
                url = t.get('url', '')
                if url.startswith('edge://') or url.startswith('chrome://'):
                    default_pages.append(t)
                else:
                    current_pages.append(t)
        
        current_count = len(current_pages)
        
        logger.info(f"页面数量校验 - 期望: {expected_count}, 实际: {current_count} (含 {len(default_pages)} 个浏览器默认页面)")
        
        # 如果实际数量超过期望数量，关闭多余页面
        if current_count > expected_count:
            excess_count = current_count - expected_count
            logger.warning(f"发现 {excess_count} 个多余页面，正在关闭...")
            
            # 按URL过滤，只保留配置中的URL页面
            configured_urls = set()
            for config in self.browser_configs:
                configured_urls.update(config.get('urls', []))
            
            # 找出需要关闭的页面（不在配置中的URL）
            pages_to_close = []
            for target in current_pages:
                target_url = target.get('url', '')
                # 跳过配置中的URL
                if any(configured_url in target_url for configured_url in configured_urls):
                    continue
                pages_to_close.append(target)
            
            # 如果没有找到多余的配置外页面，关闭最早打开的页面（最后启动的通常在列表末尾）
            if not pages_to_close:
                # 关闭列表末尾的多余页面（最新打开的）
                pages_to_close = current_pages[-excess_count:]
            
            # 关闭多余页面
            for target in pages_to_close[:excess_count]:
                target_id = target.get('id')
                target_url = target.get('url')
                logger.info(f"关闭多余页面: {target_url}")
                if self.close_target(target_id):
                    logger.info(f"成功关闭多余页面: {target_url}")
                else:
                    logger.warning(f"关闭多余页面失败: {target_url}")
    
    def scheduled_restart(self):
        """定时重启任务"""
        next_restart = datetime.now() + timedelta(seconds=self.restart_seconds)
        logger.info(f"计划 {self.restart_seconds // 60} 分钟后重启: {next_restart.strftime('%Y-%m-%d %H:%M:%S')}")
        
        while self.is_running:
            current_time = datetime.now()
            if current_time >= next_restart:
                logger.info("执行定时重启...")
                self.force_restart("定时重启")
                next_restart = datetime.now() + timedelta(seconds=self.restart_seconds)
                logger.info(f"下次重启计划: {next_restart.strftime('%Y-%m-%d %H:%M:%S')}")
            
            time.sleep(SCHEDULE_CHECK_INTERVAL)  # 检查计划任务间隔
    
    def run(self):
        """主运行循环"""
        self.is_running = True
        
        try:
            # 启动浏览器
            self.start_all_browsers()
            
            # 启动监控线程
            monitor_thread = threading.Thread(target=self.monitor_resources, daemon=True)
            monitor_thread.start()
            
            # 启动定时重启线程
            restart_thread = threading.Thread(target=self.scheduled_restart, daemon=True)
            restart_thread.start()
            
            logger.info("浏览器管理器已启动，按Ctrl+C停止...")
            
            # 主线程等待
            while self.is_running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("收到停止信号...")
        except Exception as e:
            logger.error(f"运行过程中出错: {str(e)}")
        finally:
            self.is_running = False
            self.stop_all_browsers(cleanup_residual=True)
            logger.info("浏览器管理器已停止")

def main():
    parser = argparse.ArgumentParser(description='多开浏览器管理器')
    parser.add_argument('--restart-seconds', type=int, default=DEFAULT_RESTART_SECONDS, 
                       help=f'重启间隔时间(秒)，默认{DEFAULT_RESTART_SECONDS}秒')
    parser.add_argument('--max-cpu', type=int, default=DEFAULT_MAX_CPU,
                       help=f'CPU使用率阈值(%%)，默认{DEFAULT_MAX_CPU}%%')
    parser.add_argument('--max-memory', type=int, default=DEFAULT_MAX_MEMORY,
                       help=f'内存使用率阈值(%%)，默认{DEFAULT_MAX_MEMORY}%%')
    parser.add_argument('--config', type=str, default=DEFAULT_CONFIG_FILE,
                       help=f'配置文件路径(JSON格式)，默认{DEFAULT_CONFIG_FILE}')
    parser.add_argument('--clean-cache', type=bool, default=DEFAULT_CLEAN_CACHE,
                       help=f'是否在退出时清理缓存，默认{DEFAULT_CLEAN_CACHE}')
    parser.add_argument('--monitor-interval', type=int, default=DEFAULT_MONITOR_INTERVAL,
                       help=f'资源监控间隔(秒)，默认{DEFAULT_MONITOR_INTERVAL}秒')
    parser.add_argument('--browser-path', type=str,
                       help='自定义浏览器路径，默认自动检测')
    parser.add_argument('--group', type=int, default=0,
                       help='配置组序号（从1开始），默认0表示使用所有配置组')
    
    args = parser.parse_args()
    
    # 初始配置
    restart_seconds = args.restart_seconds
    max_cpu = args.max_cpu
    max_memory = args.max_memory
    monitor_interval = args.monitor_interval
    clean_cache_on_exit = args.clean_cache
    custom_browser_path = args.browser_path
    browser_type = 0  # 默认自动检测
    browser_configs = None
    selected_group_index = args.group
    
    # 如果配置文件不存在，创建默认配置文件
    if not os.path.exists(args.config):
        logger.info(f"配置文件 {args.config} 不存在，创建默认配置文件")
        # 默认配置
        default_config = {
            "restart_minutes": 60,
            "max_cpu": 80,
            "max_memory": 85,
            "monitor_minutes": 1,
            "clean_cache": False,
            "browser_type": 0,
            "browser_groups": [
                {
                    "name": "配置1",
                    "urls": [
                        "https://live.bilibili.com/1732027424",
                        "https://live.bilibili.com/1732027424"
                    ]
                },
                {
                    "name": "配置2",
                    "urls": [
                        "https://live.bilibili.com/24568787",
                        "https://live.bilibili.com/24568787"
                    ]
                }
            ]
        }
        try:
            with open(args.config, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
            logger.info(f"默认配置文件已创建: {args.config}")
        except PermissionError as e:
            logger.error(f"无法创建配置文件（权限不足）: {str(e)}")
        except Exception as e:
            logger.error(f"创建配置文件失败: {str(e)}")
    
    # 如果有配置文件，从文件读取配置
    if os.path.exists(args.config):
        try:
            with open(args.config, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 兼容旧配置字段名
                # 先检查restart_minutes（分钟），再检查restart_seconds（秒），最后检查restart_hours（小时）
                restart_seconds = restart_seconds
                if 'restart_minutes' in config:
                    restart_seconds = config['restart_minutes'] * 60
                elif 'restart_seconds' in config:
                    restart_seconds = config['restart_seconds']
                elif 'restart_hours' in config:
                    restart_seconds = config['restart_hours'] * 3600
                max_cpu = config.get('max_cpu', max_cpu)
                max_memory = config.get('max_memory', max_memory)
                # 先检查monitor_minutes（分钟），再检查monitor_interval（秒）
                if 'monitor_minutes' in config:
                    monitor_interval = config['monitor_minutes'] * 60
                else:
                    monitor_interval = config.get('monitor_interval', monitor_interval)
                clean_cache_on_exit = config.get('clean_cache', clean_cache_on_exit)
                custom_browser_path = config.get('browser_path', custom_browser_path)
                browser_type = config.get('browser_type', 0)
                
                # 支持新的 browser_groups 字段和旧的 browsers 字段
                browser_groups = config.get('browser_groups', [])
                if browser_groups:
                    browser_configs = browser_groups
                else:
                    browser_configs = config.get('browsers', browser_configs)
                
                # 如果指定了配置组序号，选择对应的配置组
                if selected_group_index > 0 and browser_configs:
                    if selected_group_index <= len(browser_configs):
                        selected_group = browser_configs[selected_group_index - 1]
                        browser_configs = [selected_group]
                        logger.info(f"已选择配置组 {selected_group_index}: {selected_group.get('name', '未知')}")
                    else:
                        logger.warning(f"配置组序号 {selected_group_index} 超出范围，共有 {len(browser_configs)} 个配置组")
                
            logger.info(f"已加载配置文件: {args.config}")
        except json.JSONDecodeError as e:
            logger.error(f"配置文件格式错误（JSON解析失败）: {str(e)}")
        except PermissionError as e:
            logger.error(f"无法读取配置文件（权限不足）: {str(e)}")
        except Exception as e:
            logger.error(f"读取配置文件失败: {str(e)}")
    else:
        logger.warning(f"配置文件 {args.config} 不存在，使用默认配置")
    
    # 验证配置合理性
    if restart_seconds <= 0:
        logger.warning(f"重启间隔 {restart_seconds} 秒不合理，使用默认值 {DEFAULT_RESTART_SECONDS}")
        restart_seconds = DEFAULT_RESTART_SECONDS
    
    if max_cpu <= 0 or max_cpu > 100:
        logger.warning(f"CPU阈值 {max_cpu}% 不合理，使用默认值 {DEFAULT_MAX_CPU}")
        max_cpu = DEFAULT_MAX_CPU
    
    if max_memory <= 0 or max_memory > 100:
        logger.warning(f"内存阈值 {max_memory}% 不合理，使用默认值 {DEFAULT_MAX_MEMORY}")
        max_memory = DEFAULT_MAX_MEMORY
    
    if monitor_interval <= 0:
        logger.warning(f"监控间隔 {monitor_interval} 秒不合理，使用默认值 {DEFAULT_MONITOR_INTERVAL}")
        monitor_interval = DEFAULT_MONITOR_INTERVAL
    
    # 创建管理器并运行
    manager = BrowserManager(
        restart_seconds=restart_seconds,
        max_cpu_percent=max_cpu,
        max_memory_percent=max_memory,
        browser_configs=browser_configs,
        monitor_interval=monitor_interval,
        clean_cache_on_exit=clean_cache_on_exit,
        custom_browser_path=custom_browser_path,
        browser_type=browser_type
    )
    
    # 显示当前配置
    logger.info(f"当前配置：")
    logger.info(f"  重启间隔: {restart_seconds // 60} 分钟")
    logger.info(f"  CPU阈值: {max_cpu}%")
    logger.info(f"  内存阈值: {max_memory}%")
    logger.info(f"  监控间隔: {monitor_interval // 60} 分钟")
    logger.info(f"  清理缓存: {clean_cache_on_exit}")
    logger.info(f"  浏览器实例数: {len(manager.browser_configs)}")
    
    manager.run()

if __name__ == "__main__":
    main()