# 贡献指南

感谢您考虑为多开浏览器管理器项目做出贡献！以下是一些指导原则，帮助您更好地参与项目开发。

## 贡献方式

### 1. 报告问题

如果您发现了bug或有新功能建议，请按照以下步骤操作：

1. 先查看[Issues](https://github.com/yourusername/reboot-chrome/issues)，确认问题是否已经被报告
2. 如果没有，请创建一个新的Issue，提供以下信息：
   - 清晰的标题和描述
   - 重现步骤（对于bug）
   - 预期行为和实际行为
   - 系统环境（Windows版本、Python版本）
   - 错误日志（如果有）
   - 截图（如果有助于理解问题）

### 2. 提交代码

我们欢迎任何形式的代码贡献，包括但不限于：
- 修复bug
- 改进现有功能
- 添加新功能
- 优化性能
- 完善文档

#### 贡献流程

1. Fork项目到您的GitHub账户
2. 创建一个新的分支：`git checkout -b feature/your-feature-name` 或 `git checkout -b fix/your-bug-fix`
3. 编写代码，确保符合项目的代码风格
4. 测试您的更改
5. 提交代码：`git commit -m "简短描述您的更改"`
6. 推送到您的Fork：`git push origin your-branch-name`
7. 创建一个Pull Request，详细描述您的更改

### 3. 代码风格

- 遵循Python PEP 8编码规范
- 为函数和模块添加适当的注释
- 保持代码简洁明了
- 避免引入不必要的依赖

### 4. 测试

- 确保您的更改不会破坏现有功能
- 添加适当的测试用例（如果适用）
- 在提交前运行脚本，确保能正常工作

## 开发环境设置

### 1. 克隆代码

```bash
git clone https://github.com/yourusername/reboot-chrome.git
cd reboot-chrome
```

### 2. 创建虚拟环境

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 运行开发版本

```bash
python reboot.py
```

## 项目结构

```
reboot-chrome/
├── reboot.py           # 主程序文件
├── config.json         # 配置文件（自动生成）
├── requirements.txt    # 依赖列表
├── logs/               # 日志文件夹（自动创建）
└── README.md           # 说明文档
```

## 联系方式

如有任何问题或建议，欢迎通过以下方式联系我们：
- [GitHub Issues](https://github.com/yourusername/reboot-chrome/issues)
- [GitHub Discussions](https://github.com/yourusername/reboot-chrome/discussions)

## 行为准则

请尊重所有贡献者，保持友好和专业的沟通。我们致力于创建一个包容和友好的社区。

## 许可证

您的贡献将被许可在MIT许可证下发布。
