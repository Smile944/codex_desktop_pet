# 大肥鱼 · Codex 桌面宠物

将 QCYTSN/dsh-dafeiyu 的原版角色、动画、声音与设置卡片适配到 Codex。提供 **macOS 独立安装包**及源码安装，不需要 npm。

插件及桌面应用版本 0.6.0。Codex 原生插件详情页提供启用开关、1%–100% 角色大小和“打开完整设置”；完整设置会在程序内弹出。

## 普通用户：下载安装包

打开 [Releases 下载页](https://github.com/Smile944/codex_desktop_pet/releases/latest)，下载与你的 Mac 芯片对应的 DMG：

- Apple 芯片（M1/M2/M3/M4 等）：`macOS-arm64.dmg`。
- Intel 芯片：`macOS-x86_64.dmg`。此包为交叉编译版本，尚未在 Intel 真机验收。

要求 **macOS 13+**，以及已经安装到 `/Applications` 的 Codex.app，或包含 Codex CLI 的 ChatGPT.app。安装包自带 Python 和预编译桌宠，**无需另装 Python、npm、Swift 或 Command Line Tools**。安装过程无需下载依赖或管理员密码。

1. 打开 DMG，双击“安装大肥鱼 · Codex.app”，点击“安装”。
2. 完成后进入 Codex → 设置 → 插件 → 大肥鱼 · Codex。列表未刷新时重新进入或重启 Codex。
3. 安装完成后即可推出磁盘、删除 DMG。运行环境已经复制到用户应用目录。

**首次打开：**当前是临时签名版本，没有 Apple Developer ID 公证。若 macOS 拦截，请在“系统设置 → 隐私与安全性”核对来源后选择“仍要打开”，按系统提示继续。无需关闭 Gatekeeper。只有具备 Apple Developer ID 证书并完成公证后，才能进一步减少来源提示。

升级重新运行新版安装器，保留已有设置。卸载可双击 DMG 内的“卸载桌宠.command”，再在 Codex 插件页卸载插件；用户设置保留。桌宠仍需本机 Codex 正常登录才能显示对应账户额度。

## 启用真实审批状态同步

安装器会检测宿主 Hooks 功能；支持且已启用时，将 8 个观察 Hook 合并到本机 Codex 用户配置旁的 `hooks.json`（通常为 `~/.codex/hooks.json`），保留原有 Hook 并备份。当前构建未发现插件包内的 Hooks，故采用官方用户级入口。

安装或更新后，在聊天输入框附近点击 **Review hooks／检查 Hooks**，仅选中状态说明为“大肥鱼：仅观察审批状态”的 8 项，点击 **Allow selected／允许所选**。CLI 用户可输入 `/hooks` 完成审查。安装器不修改信任记录，也不自动启用宿主功能；未启用或不支持 Hooks 时跳过这一配置，基础桌宠仍可使用。

观察器不输出 `allow`、`deny` 等审批决定，不更改工具参数、不保存放行规则。它仅保存会话/轮次、待处理计数和匹配摘要；不保存原始命令或工具输出。卸载桌宠后，已有 Hook 命令会成为无操作；可在 `/hooks` 中禁用或移除配置。

已按本机实际行为分别核对：允许并执行、原生界面 No 拒绝（本机构建产生中断）、Control+C 取消后的等待清除。**独立 decline 并继续会话尚不可验收**，不算作已通过。详细步骤和协议边界见 [审批验收说明](codex/verification/APPROVAL_TESTS.md)。

## 开发者：源码安装

**需要下载整个仓库并运行安装器。只安装 codex/plugin 目录，不能启动桌面角色。** 安装器会依次构建原生程序、安装用户级后台服务、注册 Codex 本地插件。

前提（首次源码构建会下载固定版本媒体工具源码，用 Command Line Tools 自带的 C 编译工具和 make 构建）：

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

仓库公开，任何人均可下载。代码及安装包不包含任何用户的 GitHub、Codex 或 DeepSeek 凭据，每位用户读取自己的本机 Codex 状态和账户额度。

## 功能

- 完整收录 PC2005-cloud/dsh-pet 固定版本的 **106 个动画视频、25,423 帧**，包含小动作、玩耍、吃什么、时节、文字、点击、拖动与状态动作。透明桌面窗口、拖动、摸头、气泡与多任务卡保持原生。
- 原版分类随机权重、五种点击回应、转身和有边界的移动；右键“动画点播”按分类选择，或在完整设置的“动画库”中搜索点播。点播完成恢复最新 Codex 状态，审批和拖动优先。
- 导入自定义角色包并切换角色；角色包各自拥有素材，不会混用原版人物。
- 跟随本机 Codex 的思考、工具工作、完成、错误和明确等待事件；可通过受信任的 PermissionRequest Hooks 同步真实审批等待。
- Codex 账户额度、剩余比例和重置时间，按接口实际返回的数据展示。气泡按距离重置的时间显示“X 天 X 小时额度剩余 XX%”，每分钟更新；不足一小时单独提示，到期等待额度刷新。接口未提供重置时间时保留额度窗口名称。
- 角色大小 1%–100%，步进 1%；气泡大小独立。
- 原生插件设置入口与完整设置弹窗。

桌面应用安装到 `~/Applications/大肥鱼 · Codex.app`，用户级启动项为 `local.codex.bigfish`。设置及本地端点在 `~/Library/Application Support/Codex BigFish/`，插件市场和启动脚本由每台机器的安装器生成，不使用开发者电脑路径。

右键“本次关闭”后，在设置中把“启用大肥鱼”关闭再开启即可恢复；完整重启 Codex 也会解除本次关闭。双击桌面伴侣应用会打开设置。

## 动画与角色包

完整设置 → **动画库与角色包**：选择动画分类或输入中文名称后点播；“随机动画”开关可停止待机随机动作和移动，仍能手动点播和点击角色。“减少动态效果”会减少播放与运动，开启时不适合验收完整动画。

右键角色 → **动画点播**也可分类选择。106 项是同一原版角色的不同动作，仓库没有额外成品角色包；不同人物须导入对应素材。

自定义角色沿用上游布局：

```text
pet/
  cat-config.json
  cat-animation/
    呼吸.webm
    挥手.webm
```

`cat-animation/webm/` 子目录也受支持。配置含 `animations`、`animationWeights`，可选 `pets[0].name`；动画池名称必须与 WebM 文件名一致（不含扩展名）。在设置中输入该 `cat-config.json` 的本机绝对路径或单角色 ZIP 路径，点击“导入角色包”。导入完成后从角色列表选择，失败不更改当前角色。仅接受透明 VP9 WebM，单包最多 160 段、每段不超过 60 秒、源文件合计不超过 512 MiB。转换在本机进行，不上传素材，不运行包内代码；导入可能需数分钟，期间等待完成。导入角色存于用户数据目录的 `packs/`。

维护者可用 `scripts/import_full_library.py` 从固定上游源码重新转换，转换保留完整 640×360 画布以避免裁切道具，24 fps、透明 WebP q68（有损压缩，并非逐像素无损复制视频）。源视频 SHA256 和每段帧数见 `assets/animation-library.json`。

## 当前限制

- 目前只提供 macOS 适配；没有验证 Windows / Linux 的 Codex 接入。
- 独立安装包自带运行环境；源码构建的普通 .app 则仍绑定构建时选定的 Python，请勿当作独立安装包转发。源码安装使用的 Python 被清理或移动后需重新安装。
- 独立包最低 macOS 13，Apple 芯片版在 macOS 14.4 上验证。Intel 版提供交叉编译产物，尚未进行 Intel 真机回归。当前未做 Apple Developer ID 公证，可能出现首次打开提示。
- 审批观察需要宿主支持并启用 Hooks，且由用户审查并信任。当前在 Codex CLI 0.165.0-alpha.1.2 上验证。未信任时不会接收审批 Hook；不会通过工具调用意图猜测真实审批。允许后通常等工具返回清除等待，拒绝/取消导致中断后清除，不承诺点击按钮瞬间切换。桌宠重启后不会恢复未经新事件确认的旧审批；若在审批已打开时重启桌宠，可能暂不显示等待，后续新审批正常同步。当前两种命令审批请求均未提供独立 decline（拒绝但继续）选项。
- 主聊天区任意悬浮注入不在公开插件接口内；提供独立桌面角色和程序内设置面板。
- 全屏/Spaces、拔掉显示器后的恢复、完整宿主退出重开、声音和系统通知仍有实际验收边界。
- 旧版 16 个逻辑动作曾通过 91,994 组有限静态视觉对照。0.6.0 扩展库另逐一检查全部 25,423 帧的解码、透明度、尺寸及源哈希；这不等于 106 个动作在真实桌面上的所有实时转场和交互均已人工验收。

## 测试与手动构建

```bash
python3 -B -m unittest discover -s codex -p 'test_*.py'
python3 -B codex/build.py
```

原版纯 Swift 核心有 Swift Package 测试：完整 Xcode 可用时在仓库根目录运行 `swift test`。只装 Command Line Tools 的环境可能缺 XCTest，可运行 `python3 -B codex/verification/run_native_portable.py` 验证原始断言；这不冒充官方 XCTest。全量静态绘制检查可在 build.py 生成源码副本后运行 `codex/verification/run_full_visual.py`，生成的本机证据不会纳入源码仓库。

维护者制作独立安装包（构建机需要 Python 和 Command Line Tools）：

```bash
python3 -B codex/release.py --arch arm64
python3 -B codex/release.py --arch x86_64
```

脚本使用 `codex/media-lock.json` 固定版本的 FFmpeg/libvpx/libwebp 源码构建最小 LGPL 媒体转换程序，并下载 `codex/runtime-lock.json` 固定版本的 Python Standalone Builds，校验 SHA256，交叉编译、签署并生成 `codex/dist/releases/` 下的 DMG。运行环境及产物不提交 Git；Python 及依赖许可证保存在安装包内 `runtime-licenses/` 和 Python 自带的 LICENSE.txt 中。

## 卸载（保留用户设置）

```bash
python3 -B codex/install.py --uninstall
```

再在 Codex 插件页卸载“大肥鱼 · Codex”；或使用本机 Codex CLI 执行 `codex plugin remove codex-bigfish@codex-bigfish-local`。第一条只移除桌面应用和自动启动，不代替插件卸载。

## 来源与许可证

本项目基于 [QCYTSN/dsh-dafeiyu](https://github.com/QCYTSN/dsh-dafeiyu) 0.1.22 的原版实现进行 Codex 适配。原始代码 MIT 版权声明保留在 LICENSE。当前角色动画来源于 [PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet)，保留其 MIT 许可证；鼠标光标采用 Chromium BSD 3-Clause 许可证；React、ReactDOM、MCP Apps SDK 保留各自许可证。详情见 [素材声明](ASSET_LICENSE.md)。本项目与 OpenAI 或 DeepSeek 无官方隶属关系。
