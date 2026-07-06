#!/usr/bin/env python3
"""启动脚本 - 支持选择配置组"""

import os
import sys
import json
import subprocess

def load_config(config_path):
    """加载配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载配置文件失败: {e}")
        return None

def main():
    base_path = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_path, 'config.json')
    
    # 检查配置文件是否存在
    if not os.path.exists(config_path):
        print(f"配置文件不存在: {config_path}")
        input("按回车键退出...")
        return
    
    # 加载配置文件
    config = load_config(config_path)
    if not config:
        input("按回车键退出...")
        return
    
    # 获取配置组列表
    browser_groups = config.get('browser_groups', [])
    if not browser_groups:
        browser_groups = config.get('browsers', [])
    
    if not browser_groups:
        print("配置文件中没有找到配置组")
        input("按回车键退出...")
        return
    
    # 显示配置组选择菜单
    print("=" * 50)
    print("    选择要启动的配置组")
    print("=" * 50)
    for i, group in enumerate(browser_groups, 1):
        group_name = group.get('name', f'配置组{i}')
        url_count = len(group.get('urls', []))
        print(f"{i}. {group_name} ({url_count} 个URL)")
    print("=" * 50)
    
    # 获取用户选择
    while True:
        try:
            choice = int(input("请输入配置组序号: "))
            if 1 <= choice <= len(browser_groups):
                break
            print(f"请输入 1-{len(browser_groups)} 之间的数字")
        except ValueError:
            print("请输入有效的数字")
    
    # 启动主程序，传递配置组参数（使用非阻塞模式）
    selected_group = browser_groups[choice - 1]
    group_name = selected_group.get('name', f'配置组{choice}')
    
    print(f"\n正在启动配置组: {group_name}")
    print("启动浏览器管理程序...")
    
    # 使用非阻塞模式启动子进程，避免Ctrl+C异常
    try:
        subprocess.Popen([sys.executable, os.path.join(base_path, 'reboot.py'), '--group', str(choice)])
        print("浏览器管理程序已启动")
    except Exception as e:
        print(f"启动失败: {e}")
        input("按回车键退出...")

if __name__ == "__main__":
    main()