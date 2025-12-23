"""
多开浏览器管理器 - 定时重启解决内存泄漏
适用于5800H CPU + 32GB RAM + 2GB显存环境
使用 Trea CN 软件开发
"""

import os
import sys
import time
import signal
import psutil
import logging
from logging.handlers import TimedRotatingFileHandler
import subprocess
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import argparse

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
START_DELAY = 3.5  # 浏览器实例启动间隔
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

# 创建logs文件夹（如果不存在）
logs_dir = 'logs'
os.makedirs(logs_dir, exist_ok=True)

# 配置日志 - 使用TimedRotatingFileHandler实现按天分割
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 创建文件处理器，按天分割日志，使用年月日格式命名
file_handler = TimedRotatingFileHandler(
    filename=os.path.join(logs_dir, datetime.now().strftime('%Y-%m-%d') + '.log'),
    when='midnight',  # 每天午夜分割
    interval=1,  # 每天分割一次
    backupCount=7,  # 保留7天的日志文件
    encoding='utf-8'
)
# 设置文件名后缀格式，备份文件格式为：年月日.log.%Y-%m-%d
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
                 window_settings: Optional[Dict] = None,
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
            window_settings: 窗口配置
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
        self.browser_profiles = []
        # 浏览器启动保护期（秒），期间不进行CPU阈值检查
        self.STARTUP_PROTECTION_PERIOD = 90
        # 记录最后一次启动时间
        self.last_start_time = None
        
        # 窗口配置，从参数获取
        self.window_settings = window_settings or {
            'window_offset_x': 120,
            'window_offset_y': 75
        }
        
        # 提取窗口配置参数
        self.window_offset_x = self.window_settings.get('window_offset_x', 120)
        self.window_offset_y = self.window_settings.get('window_offset_y', 75)
        
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
    
    def get_screen_resolution(self):
        """获取Windows屏幕分辨率"""
        try:
            import win32api
            width = win32api.GetSystemMetrics(0)
            height = win32api.GetSystemMetrics(1)
            logger.info(f"检测到屏幕分辨率: {width}x{height}")
            return width, height
        except Exception as e:
            logger.error(f"获取屏幕分辨率失败: {str(e)}")
            return 1920, 1080  # 默认分辨率
    
    def create_browser_args(self, url: str) -> List[str]:
        """创建浏览器启动参数，每个URL使用单独窗口"""
        if not self.browser_path:
            raise FileNotFoundError("浏览器路径未找到")
        
        # 使用浏览器默认窗口大小，不强制设置
        args = [
            self.browser_path,
            "--new-window",  # 每个URL使用新窗口打开
            url,  # 当前要打开的URL
        ]
        
        return args
    
    def open_urls_in_tabs(self, profile_idx: int, urls: List[str]) -> None:
        """每个URL使用单独窗口打开，并斜着错开排布"""
        try:
            # 验证URL列表非空
            if not urls:
                logger.warning(f"浏览器实例 {profile_idx} 的URL列表为空，跳过启动")
                return
            
            logger.info(f"为浏览器实例 {profile_idx} 打开 {len(urls)} 个窗口...")
            
            # 先启动所有浏览器窗口，不立即调整位置
            started_processes = []
            for window_idx, url in enumerate(urls):
                try:
                    # 创建浏览器启动参数
                    args = self.create_browser_args(url)
                    
                    logger.info(f"启动浏览器窗口，打开URL: {url}")
                    
                    # 启动浏览器进程
                    process = subprocess.Popen(
                        args,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
                    )
                    
                    started_processes.append((window_idx, process, url))
                    # 将进程添加到browser_processes列表中，用于健康检查
                    self.browser_processes.append(process)
                    logger.info(f"浏览器窗口已启动 (PID: {process.pid})")
                    
                    # 避免同时启动所有窗口造成资源冲击
                    time.sleep(START_DELAY)
                    
                except FileNotFoundError as e:
                    logger.error(f"打开URL {url} 失败：浏览器路径不存在 - {str(e)}")
                except Exception as e:
                    logger.error(f"打开URL {url} 失败：{str(e)}")
            
            # 所有窗口启动后，等待并尝试查找所有窗口
            logger.info(f"所有窗口已启动，开始查找浏览器窗口...")
            
            # 窗口错开排布（Windows）
            if sys.platform == "win32":
                try:
                    import win32gui
                    import win32con
                    import win32process
                    
                    # 获取我们启动的进程ID列表
                    our_process_ids = [proc.pid for _, proc, _ in started_processes]
                    logger.info(f"我们启动的进程ID: {our_process_ids}")
                    
                    # 最多尝试10次，每次等待3秒，直到找到所有窗口
                    max_attempts = 10
                    found_windows = []
                    
                    def find_our_browser_windows(hwnd, extra):
                        """只查找我们启动的浏览器窗口"""
                        try:
                            # 获取窗口类名
                            class_name = win32gui.GetClassName(hwnd)
                            
                            # 检查是否为浏览器窗口
                            if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
                                if "Chrome_WidgetWin" in class_name or "Edge_WidgetWin" in class_name:
                                    # 获取窗口所属的进程ID
                                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                                    # 添加所有可见的浏览器窗口，不限制进程ID
                                    found_windows.append((hwnd, class_name, pid))
                                    logger.debug(f"找到窗口: hwnd={hwnd}, class={class_name}, pid={pid}")
                        except Exception as e:
                            logger.debug(f"查找窗口时出错: {e}")
                    
                    # 重试机制：最多尝试10次，每次等待3秒
                    attempt = 0
                    required_windows = len(started_processes)
                    
                    while attempt < max_attempts:
                        attempt += 1
                        # 清空之前的结果
                        found_windows.clear()
                        # 查找所有浏览器窗口
                        win32gui.EnumWindows(find_our_browser_windows, None)
                        
                        logger.info(f"尝试 {attempt}/{max_attempts}: 找到 {len(found_windows)} 个我们启动的浏览器窗口，需要 {required_windows} 个")
                        
                        # 当找到的窗口数量达到或超过需要的数量时进行调整
                        if len(found_windows) >= required_windows:
                            logger.info(f"找到 {len(found_windows)} 个我们启动的浏览器窗口，开始调整位置...")
                            break
                        else:
                            # 等待3秒后重试
                            logger.info(f"等待3秒后重试...")
                            time.sleep(3)
                    
                    # 如果找到了足够的窗口，进行位置调整
                    if len(found_windows) >= required_windows:
                        # 调整前 required_windows 个窗口的位置
                        for idx in range(required_windows):
                            hwnd = found_windows[idx][0]
                            # 计算窗口位置
                            pos_x = idx * self.window_offset_x
                            pos_y = idx * self.window_offset_y
                            
                            # 设置窗口位置，不改变大小，不限制在桌面范围内
                            win32gui.SetWindowPos(
                                hwnd,
                                win32con.HWND_NOTOPMOST,
                                pos_x,         # 窗口左上角X坐标
                                pos_y,         # 窗口左上角Y坐标
                                0,  # 不改变宽度
                                0,  # 不改变高度
                                win32con.SWP_SHOWWINDOW | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE | win32con.SWP_NOSIZE  # 显示窗口，不改变大小和Z顺序，不激活
                            )
                            logger.info(f"已调整窗口位置: ({pos_x}, {pos_y}) (窗口句柄: {hwnd}, 进程ID: {found_windows[idx][2]})")
                            # 记录浏览器窗口信息
                            self.browser_profiles.append({
                                'pid': found_windows[idx][2],  # 保存实际的进程ID
                                'hwnd': hwnd,  # 保存窗口句柄
                                'window_idx': idx,
                                'profile_idx': profile_idx,
                                'url': started_processes[idx][2],
                                'start_time': datetime.now()
                            })
                    else:
                        logger.warning(f"尝试 {max_attempts} 次后仍未找到足够的浏览器窗口，找到 {len(found_windows)} 个，需要 {required_windows} 个，跳过位置调整")
                        logger.info(f"当前系统中所有浏览器窗口: ")
                        # 临时查找所有浏览器窗口用于调试
                    all_browser_windows = []
                    def find_all_browser_windows(hwnd, extra):
                        try:
                            if win32gui.IsWindowVisible(hwnd):
                                class_name = win32gui.GetClassName(hwnd)
                                if "Chrome_WidgetWin" in class_name or "Edge_WidgetWin" in class_name:
                                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                                    title = win32gui.GetWindowText(hwnd)
                                    all_browser_windows.append((hwnd, class_name, pid, title))
                        except:
                            pass
                    win32gui.EnumWindows(find_all_browser_windows, None)
                    for hwnd, class_name, pid, title in all_browser_windows:
                        logger.info(f"  hwnd={hwnd}, class={class_name}, pid={pid}, title={title[:30]}...")
                
                except ImportError as e:
                    logger.warning(f"无法导入win32gui模块，跳过窗口位置调整: {str(e)}")
                except Exception as e:
                    logger.error(f"调整窗口位置失败: {str(e)}")
                    logger.exception("窗口调整错误堆栈:")
            
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
                if not self.browser_processes and self.browser_configs:
                    logger.warning("所有浏览器进程已退出，准备重新启动...")
                    # 先确保完全停止所有进程（包括残留）
                    self.stop_all_browsers()
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
        """强制重启所有浏览器"""
        logger.warning(f"强制重启所有浏览器 - 原因: {reason}")
        self.stop_all_browsers()
        time.sleep(STOP_DELAY)  # 等待完全关闭
        self.start_all_browsers()
    
    def stop_all_browsers(self):
        """停止所有浏览器进程"""
        logger.info("正在停止所有浏览器进程...")
        
        # 清理Chrome残留进程
        self.cleanup_chrome_processes()
        
        # 清空浏览器窗口记录
        self.browser_profiles.clear()
        self.browser_processes.clear()
    
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
    
    def cleanup_cache(self):
        """清理浏览器缓存目录（已废弃，使用浏览器默认缓存）"""
        # 不再清理浏览器缓存，使用浏览器默认的缓存管理
        logger.info("已废弃：不再清理浏览器缓存，使用浏览器默认缓存")
    
    def start_all_browsers(self):
        """启动所有配置的浏览器实例"""
        logger.info(f"启动 {len(self.browser_configs)} 个浏览器实例...")
        # 记录浏览器启动时间
        self.last_start_time = datetime.now()
        
        # 清空之前的进程列表和窗口记录
        self.browser_processes.clear()
        self.browser_profiles.clear()
        
        for idx, config in enumerate(self.browser_configs):
            logger.info(f"打开 {config['name']}: {config['urls']}")
            # 每个URL使用单独窗口打开
            self.open_urls_in_tabs(idx + 1, config['urls'])
            
            # 避免同时启动所有实例造成资源冲击
            time.sleep(START_DELAY)  # 实例间启动间隔
    
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
            self.stop_all_browsers()
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
    window_settings = None
    
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
            "browsers": [
                {
                    "name": "默认组1",
                    "urls": [
                        "https://www.4399.com",
                        "https://www.acfun.cn",
                        "https://live.bilibili.com"
                    ]
                }
            ],
            "browser_settings": {
                "window_offset_x": 120,
                "window_offset_y": 75
            },
            "browser_type": 0
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
                browser_configs = config.get('browsers', browser_configs)
                # 从配置文件读取窗口设置
                window_settings = config.get('browser_settings', None)
            logger.info(f"已加载配置文件: {args.config}")
            if window_settings:
                logger.info(f"已加载窗口配置: {window_settings}")
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
        window_settings=window_settings,
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