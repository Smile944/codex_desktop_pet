# 验证记录

2026-10-29 在 macOS 14.4、Swift 5.10 与可用 Python 环境上验证。分发副本已独立运行，不依赖开发目录中的额外文件。

- 分发副本中的 Python 单元测试（初版源码快照）：57/57 通过，包括配置、事件解析、原生插件设置契约、安装脚本、含空格路径的插件启动器。
- `bash Install.command --check`：通过，只检查环境，没有安装或重启宿主。
- `python3 -B codex/build.py`：成功编译本机原生 Helper 和完整应用；打包 3,453 个素材文件哈希一致，签名检查通过。此次验证没有用分发副本覆盖用户已安装的桌宠。
- 原先已安装版本的原生设置入口：用户截图确认插件详情页有启用/大小控件，点击后在宿主内打开完整设置弹窗。
- 原版 Swift portable 断言：35 个方法、144 条断言；加原版/适配控制器与几何检查，合计 767 条断言通过。不是官方 XCTest 运行器。
- 原版与适配版有限静态视觉：16 段动画、3,444 帧在 55%/80%/100% 下逐帧比较，加卡片及显隐矩阵，共 91,994 组像素哈希一致。比较统一宿主默认文案并清除实时渐变，使用同机字体和 1× bitmap。

实际验收已确认拖动、摸头、右键菜单、透明区域点击穿透、拖到另一显示器，以及程序内打开完整设置。全屏/Spaces、不同缩放和拔屏恢复、完整退出重开、声音通知仍有未覆盖场景；权限审批精确同步也取决于宿主状态接口。详细范围见 README。

本机诊断日志、个人配置、截图和历史工具输出不随源码分发；验证器可在各自机器上重新生成本地证据。端到端测试不是对其他 macOS 版本或 Intel Mac 的验收承诺。

## 0.4.0 独立安装包

- 68 项 Python 单元测试通过（系统 Python 3.9 与内置 Python 3.12）。新增迁移后 MCP 初始化、安装失败回退、设置保留、归档 SHA256/路径检查及 fallback Python 隔离回归。
- arm64、x86_64 分别编译原生 Helper/安装界面，内置固定摘要的 CPython 3.12.16（20261026），3453 个素材文件与原版一致；应用签名及 DMG 校验通过。
- 实际挂载各 DMG，在含中文和空格的临时用户目录安装（不启动真实用户 LaunchAgent），推出 DMG 后运行已安装 Python/MCP，验证完整设置 HTML、动画清单、9 个工具。
- 在临时 HOME/CODEX_HOME 中使用本机真实 Codex CLI 注册插件；原生 app-server 发现 bigfish、9 个工具及 openai/settings，toolsError=null。未更改真实用户的插件注册、桌宠或设置。
- arm64 直接运行；x86_64 在本机 Rosetta 下运行，不等同于 Intel 真机或 macOS 13 验收。
- 新安装器的 --check 原生入口执行通过；未声称已人工验收 GUI 点击流程、浏览器下载后 Gatekeeper 提示或完整宿主重启。无 Developer ID，因此仅临时签名，未公证。
- 独立只读代码审查未发现 Critical/Important 问题；发现既有 fallback 启动路径未传递 -E/-s，已用先失败后通过的回归测试补齐。

复现：

```bash
python3 -B codex/verification/verify_release.py codex/dist/releases/Codex-BigFish-0.4.0-macOS-arm64.dmg
python3 -B codex/verification/verify_release.py codex/dist/releases/Codex-BigFish-0.4.0-macOS-x86_64.dmg
```

第二条需要本机能执行 x86_64（Intel 或已安装 Rosetta）；否则加 --static-only，仅检查静态文件与迁移签名。无需为使用 Apple 芯片安装包安装 Rosetta。

## 0.4.1 气泡额度倒计时

- 72 项 Python 测试通过（系统 Python 3.9 与安装包内 Python 3.12）。覆盖跨天/小时、不足一小时、到期不展示旧比例、缺失重置时间，以及升级时等待旧后台服务移除。
- 真实本机升级复现并修复 launchctl bootout 异步退出竞态；升级后 Helper 正常运行，snapshot 的额度摘要使用“X 天 X 小时”格式，原设置文件字节保持一致。未将个人额度或截图纳入仓库。
- 两种最终 DMG 的签名、挂载/推出后迁移、内置运行环境及真实 Codex CLI 插件发现均通过；Intel 仍为 Rosetta 验证，未声称 Intel 真机验收。
- 倒计时格式和安装等待逻辑均经过独立只读审查，无确认缺陷。
