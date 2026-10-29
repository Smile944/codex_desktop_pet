# 独立 macOS 安装包

用户已要求制作包含运行环境的安装包，完成后继续上传同一公共 GitHub 仓库。

## 方案与边界

使用两个 DMG（arm64、x86_64），内含原生安装应用、预编译桌宠及校验过的独立 Python。用户双击安装应用，无需 Python、npm、Swift 或 Command Line Tools。依赖已安装的 Codex/ChatGPT CLI，最低 macOS 13。保留原版功能和用户设置。

不采用源码引导器（仍需编译环境），不制作需要管理员权限的系统级 pkg。现有机器无 Developer ID 证书，因此使用临时签名；不能声称已公证。README 和发布页说明首次打开方式。Intel 包交叉编译，明确区分二进制检查与 Intel 真机验收。

## 执行与验证

1. 为安装路径写测试：安装后 LaunchAgent 和 MCP 使用已安装包内 Python，下载目录移除后仍可用；缺失/损坏源不破坏现有应用；保留设置。
2. 复用 install.py 和 install_plugin.py，增加独立运行环境选择及安装前检查。为 GUI 提供 portable_install.py（--check 只读）。
3. 为 build.py 增加架构、运行环境、输出参数，增加原生 Installer.swift 和 release.py。固定运行环境下载 URL/SHA256，保留第三方许可证。DMG 附卸载入口、说明和 SHA256 清单。
4. 两种架构构建、签名验证、挂载/路径迁移检查；arm64 实际运行内置 Python 和 MCP 初始化，完整 Python 测试。新安装回归使用临时目录，不覆盖现有桌宠。
5. 独立代码审查、处理影响安装的问题，更新 README/TESTING，提交并快进 main，创建 GitHub Release 上传 DMG/校验文件，核对远端文件大小和摘要。

## 重点检查

空格/中文路径，下载盘卸载后存活，升级中断，错误架构，缺少宿主，签名和运行环境许可证，归档里不包含本机用户路径/凭据，安装失败给出可操作说明。
