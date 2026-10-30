# 完整动画库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 提供全部 106 动画、原版播放规则、分类点播和自定义角色包。
**Architecture:** 维持原生 Swift 桌宠，Python 负责可验证的素材转换、角色包管理和本机接口。统一 manifest 驱动原生及设置 UI。
**Tech Stack:** Python 3.9+、Swift/AppKit、FFmpeg、React。
**Spec:** docs/superpowers/specs/2026-10-30-full-animation-library-design.md

## Global Constraints
- 保留用户配置、Hooks 人工审批、Codex 额度与原插件身份。
- 固定上游版本，记录哈希和转换参数，保留许可；不提交本地证据或凭据。
- 原生图片按需加载，双架构构建，未知平台不声称通过。

## Review Focus
- 任意名称/路径/压缩包和符号链接：不得越出角色包。
- 导入中断/转换失败：当前角色及既有设置仍可用。
- 点播期间新审批或拖动：最新状态优先并能恢复。
- 同一帧名跨包：不得重用旧缓存。
- 全部素材首次播放：不得预载数百 MB 内存。

### Task 1: 完整素材和角色包管线
**Files:** codex/pet_packs.py, codex/test_pet_packs.py, scripts/import_full_library.py, assets/pet-manifest.json, assets/pet, assets/animation-library.json, codex/media-lock.json
**Interfaces:** manifest.clips 保留语义 ID，增加中文视频名 ID；animations/animationWeights/clipLabels 跟随原版。PackStore.list() -> list，resolve(id) -> assets directory，import_pack(path) -> pack metadata，play(id) 通过 host 发送 kind=play,clip。
- [x] 先测试并验证失败：包内路径隔离、非法压缩包、缺失素材、导入回滚。
- [x] 实现转换、完整106素材、角色包存储及固定工具依赖。
- [x] 运行 Python 测试和106源/全帧校验。

### Task 2: 原生播放和交互
**Files:** native/macos/Sources/AnimationModel.swift, PetController.swift, PetView.swift, 新纯播放规则辅助文件，Package.swift，native/macos/Tests，codex/verification
**Interfaces:** 消费上述 manifest；输入 kind=play,clip；选择角色由 host 重启 helper 并切换 assets 根。保留现有协议。
- [x] 先测试并验证失败：权重边界、一次点播和恢复、拖动优先、移动起止与屏幕边界。
- [x] 扩展模型、分类菜单、点击池、转身/移动、额度事件、按需缓存。
- [x] 执行可移植 Swift 断言和原生编译。

### Task 3: 设置与宿主集成
**Files:** codex/host.py, codex/client_bundle.py, codex/ui/animation-panel.js, codex/plugin/server.py, codex/plugin/app.js, codex/build.py
**Interfaces:** GET /plugins/dsh-dafeiyu/packs -> {packs,selected,manifest}; POST /plugins/dsh-dafeiyu/packs {action:select,id} 或 {action:import,path}; POST /plugins/dsh-dafeiyu/play {clip}。完整设置使用同一入口，原生 MCP App 通过工具桥调用。
- [x] 先测试并验证失败：选择和重新加载、非法动作、MCP 桥错误传递。
- [x] 加入设置动画面板与角色包入口、宿主安全检查及构建打包。
- [x] Python 全量回归、JS 桥、原生静态画面和打包回归。

### Task 4: 发布与验收
**Files:** README.md, codex/README.md, CHANGELOG.md, codex/plugin/plugin.json
- [x] 新增操作说明、真实边界、版本号；运行全量测试与独立审查。
- [x] 分别构建 arm64/x86_64，验证安装包、安装本机并保留配置。
- [ ] 提交推送并上传公开 release，核对资产 SHA256。
