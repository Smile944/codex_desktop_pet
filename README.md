# 大肥鱼 · Codex 桌面宠物

将 QCYTSN/dsh-dafeiyu 的原版角色、动画、声音与设置卡片适配到 Codex。当前支持 **macOS 本机源码安装**，不需要 npm。

插件版本 0.3.4，桌面应用版本 0.3.1。Codex 原生插件详情页提供启用开关、1%–100% 角色大小和“打开完整设置”；完整设置会在程序内弹出。

## 下载后怎样使用

**需要下载整个仓库并运行安装器。只安装 codex/plugin 目录，不能启动桌面角色。** 安装器会依次构建原生程序、安装用户级后台服务、注册 Codex 本地插件。

前提：

- macOS，安装了 Codex.app，或包含 Codex CLI 的 ChatGPT.app，应用位于 /Applications。
- Python 3.9 或更新版本。安装器优先使用本机现有 Codex Python，也可使用系统或 Homebrew 的 Python。
- Apple Command Line Tools，包含 Swift 编译器和 macOS SDK。未安装时先在终端运行 `xcode-select --install`，按 Apple 提示完成安装。构建桌宠无需完整 Xcode。

下载或克隆后，在完整源码目录运行：

```bash
bash Install.command --check
bash Install.command
```

第一条只检查依赖，不更改安装。也可以在 Finder 双击 Install.command。若 macOS 提示权限或来源问题，可使用上面的终端命令；安装包目前使用本机临时签名，没有 Developer ID 公证。

安装完成后，在 Codex 中进入“设置 → 插件 → 大肥鱼 · Codex”。如果尚未刷新，重新进入插件页，或在方便时重启 Codex。通过“打开完整设置”调整气泡、声音、活跃程度等。

仓库若保持私有，其他人需要具有仓库读取权限才能下载。代码内不包含任何用户的 GitHub、Codex 或 DeepSeek 凭据，每位用户读取自己的本机 Codex 状态和账户额度。

## 功能

- 原版角色及 16 段动画，透明桌面窗口、拖动、摸头、右键菜单、气泡与多任务卡。
- 跟随本机 Codex 的思考、工具工作、完成、错误和明确等待事件。
- Codex 账户额度、剩余比例和重置时间，按接口实际返回的数据展示。
- 角色大小 1%–100%，步进 1%；气泡大小独立。
- 原生插件设置入口与完整设置弹窗。

桌面应用安装到 `~/Applications/大肥鱼 · Codex.app`，用户级启动项为 `local.codex.bigfish`。设置及本地端点在 `~/Library/Application Support/Codex BigFish/`，插件市场和启动脚本由每台机器的安装器生成，不使用开发者电脑路径。

右键“本次关闭”后，在设置中把“启用大肥鱼”关闭再开启即可恢复；完整重启 Codex 也会解除本次关闭。双击桌面伴侣应用会打开设置。

## 当前限制

- 目前只提供 macOS 适配；没有验证 Windows / Linux 的 Codex 接入。
- 这是源码安装流程，不是免依赖、下载即运行的通用安装包。不要复制其他机器已经构建的 .app；启动器会记录构建时选定的 Python 路径。清理或移动该 Python 后需重新安装。
- 原生权限审批的精确同步依赖宿主共享状态接口。当前环境未提供该端点时，观察器报告不可用；不将权限请求意图冒充实际等待。
- 主聊天区任意悬浮注入不在公开插件接口内；提供独立桌面角色和程序内设置面板。
- 全屏/Spaces、拔掉显示器后的恢复、完整宿主退出重开、声音和系统通知仍有实际验收边界。
- 已进行 91,994 组有限静态视觉对照（所有动画帧在 55%/80%/100% 下比较，加卡片与显隐矩阵），像素哈希一致；同机统一文案并清除实时渐变后比较，不等于全部系统场景和实时过渡均已验收。

## 测试与手动构建

```bash
python3 -B -m unittest discover -s codex -p 'test_*.py'
python3 -B codex/build.py
```

原版纯 Swift 核心有 Swift Package 测试：完整 Xcode 可用时在仓库根目录运行 `swift test`。只装 Command Line Tools 的环境可能缺 XCTest，可运行 `python3 -B codex/verification/run_native_portable.py` 验证原始断言；这不冒充官方 XCTest。全量静态绘制检查可在 build.py 生成源码副本后运行 `codex/verification/run_full_visual.py`，生成的本机证据不会纳入源码仓库。

## 卸载（保留用户设置）

```bash
python3 -B codex/install.py --uninstall
```

再在 Codex 插件页卸载“大肥鱼 · Codex”；或使用本机 Codex CLI 执行 `codex plugin remove codex-bigfish@codex-bigfish-local`。第一条只移除桌面应用和自动启动，不代替插件卸载。

## 来源与许可证

本项目基于 [QCYTSN/dsh-dafeiyu](https://github.com/QCYTSN/dsh-dafeiyu) 0.1.22 的原版实现进行 Codex 适配。原始代码 MIT 版权声明保留在 LICENSE。当前角色动画来源于 [PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet)，保留其 MIT 许可证；鼠标光标采用 Chromium BSD 3-Clause 许可证；React、ReactDOM、MCP Apps SDK 保留各自许可证。详情见 [素材声明](ASSET_LICENSE.md)。本项目与 OpenAI 或 DeepSeek 无官方隶属关系。
