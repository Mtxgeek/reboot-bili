# 多开浏览器管理器
一个用于管理多个浏览器窗口，定时重启以解决内存泄漏问题的工具。

**使用 Trea CN 软件开发**
主要用途 挂b站直播间时长 因为不会写发包 所以选择硬挂

## 功能特性

### 核心功能
- ✅ 自动启动多个浏览器窗口，支持Chrome和Edge浏览器
- ✅ 窗口自动斜向排列，从左上角开始向右下角错开
- ✅ 定时重启机制，解决浏览器内存泄漏问题
- ✅ 系统资源监控（CPU、内存）
- ✅ 超过阈值自动重启
- ✅ 支持从配置文件读取URL列表和参数

### 浏览器支持
- ✅ Microsoft Edge（自动检测）
- ✅ Google Chrome（自动检测）
- ✅ 支持自定义浏览器路径

### 日志管理
- ✅ 日志按天分割，存储在`logs`文件夹
- ✅ 日志文件名格式：`年月日.log`（如：2025-12-23.log）
- ✅ 完整的错误日志和运行状态记录

### 系统保护
- ✅ 浏览器启动保护期（90秒内不检查CPU阈值）
- ✅ 不干扰系统其他进程（如msedgewebview2.exe）
- ✅ 智能进程管理，只清理当前使用的浏览器进程

## 安装要求

### 系统要求
- Windows 10/11 64位系统
- Python 3.6+

### 依赖安装

```bash
pip install -r requirements.txt
```

## 快速开始

### 1. 首次运行

直接运行脚本，会自动创建默认配置文件 `config.json`：

```bash
python reboot.py
```

### 2. 配置文件

编辑 `config.json` 文件，自定义浏览器行为：

```json
{
    "restart_minutes": 60,                // 重启间隔（分钟）
    "max_cpu": 80,                        // CPU阈值（%）
    "max_memory": 85,                     // 内存阈值（%）
    "monitor_minutes": 1,                 // 监控间隔（分钟）
    "clean_cache": false,                 // 是否清理缓存
    "browsers": [                         // 浏览器实例配置
        {
            "name": "默认组1",
            "urls": [                     // 要打开的URL列表
                "https://www.4399.com",
                "https://www.acfun.cn",
                "https://live.bilibili.com"
            ]
        }
    ],
    "browser_settings": {                 // 窗口配置
        "window_offset_x": 120,           // 窗口横向偏移量
        "window_offset_y": 75             // 窗口纵向偏移量
    },
    "browser_type": 0                     // 浏览器类型（0:自动检测, 1:Edge, 2:Chrome）
}
```

### 3. 运行脚本

使用配置文件运行：

```bash
python reboot.py --config config.json
```

### 4. 命令行参数

```bash
python reboot.py [OPTIONS]

选项：
  --restart-seconds INTEGER   重启间隔时间(秒)，默认3600秒
  --max-cpu INTEGER           CPU使用率阈值(%)，默认80%
  --max-memory INTEGER        内存使用率阈值(%)，默认85%
  --config TEXT               配置文件路径(JSON格式)，默认config.json
  --clean-cache BOOLEAN       是否在退出时清理缓存，默认False
  --monitor-interval INTEGER  资源监控间隔(秒)，默认60秒
  --browser-path TEXT         自定义浏览器路径，默认自动检测
```

## 工作原理

1. **浏览器启动**：
   - 从配置文件读取URL列表
   - 每个URL使用单独窗口打开
   - 窗口自动斜向排列，从左上角开始

2. **资源监控**：
   - 定期检查CPU和内存使用率
   - 启动保护期内不检查CPU阈值
   - 超过阈值自动重启所有浏览器

3. **定时重启**：
   - 根据配置的间隔时间自动重启
   - 平滑关闭并重新启动所有浏览器窗口

4. **进程管理**：
   - 智能识别并管理浏览器进程
   - 只清理当前使用的浏览器类型
   - 不干扰系统其他进程

## 日志查看

日志文件存储在 `logs` 文件夹中，按天分割：

```
logs/
├── 2025-12-23.log      # 当日日志
└── 2025-12-22.log      # 昨日日志
```

## 常见问题

### 1. 浏览器窗口没有自动排列

- 确保已安装 `pywin32` 库
- 检查Windows权限设置
- 查看日志文件中的错误信息

### 2. 浏览器无法启动

- 检查浏览器是否正确安装
- 尝试手动指定浏览器路径
- 查看日志文件中的具体错误

### 3. 资源监控不准确

- 系统资源监控会有1秒延迟
- 浏览器启动90秒内不检查CPU阈值
- 可调整配置文件中的阈值参数

## 配置说明

### 核心配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `restart_minutes` | 整数 | 60 | 重启间隔（分钟） |
| `max_cpu` | 整数 | 80 | CPU使用率阈值（%） |
| `max_memory` | 整数 | 85 | 内存使用率阈值（%） |
| `monitor_minutes` | 整数 | 1 | 监控间隔（分钟） |
| `clean_cache` | 布尔值 | false | 是否清理缓存 |
| `browser_type` | 整数 | 0 | 浏览器类型（0:自动, 1:Edge, 2:Chrome） |

### 窗口配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `window_offset_x` | 整数 | 120 | 窗口横向偏移量 |
| `window_offset_y` | 整数 | 75 | 窗口纵向偏移量 |

## 系统资源占用

- **CPU**：正常运行时占用极低（<1%）
- **内存**：约20-30MB
- **磁盘**：仅日志文件占用空间，每天约几KB到几十KB

## 开发说明

### 项目结构

```
reboot-chrome/
├── reboot.py           # 主程序文件
├── config.json         # 配置文件（自动生成）
├── requirements.txt    # 依赖列表
├── logs/               # 日志文件夹（自动创建）
└── README.md           # 说明文档
```

### 主要模块

1. **BrowserManager**：核心管理类
2. **资源监控**：使用psutil库监控系统资源
3. **窗口管理**：使用win32gui库管理浏览器窗口
4. **日志系统**：使用logging模块实现日志管理

## 许可证

MIT License

## 更新日志

### v1.0.0 (2025-12-23)
- 初始版本发布
- 支持Chrome和Edge浏览器
- 窗口自动排列功能
- 定时重启机制
- 资源监控和自动重启
- 日志按天分割

## 联系方式

如有问题或建议，欢迎提交Issue或Pull Request。
