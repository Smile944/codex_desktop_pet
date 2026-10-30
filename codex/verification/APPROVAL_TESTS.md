# 真实人工审批验收

## 本机核对结果（2026-10-30）

| 人工操作 | 结果 |
|---|---|
| 允许：原生 CLI 仅本次允许 | 真实 PermissionRequest 产生待处理计数 1，桌宠任务进入 WAITING；printf 执行一次，待处理标记清除，任务恢复并完成 |
| 拒绝：原生 CLI No | 该构建产生 aborted by user / turn_aborted；待处理标记清除，任务退出等待 |
| 取消：独立运行取消入口，Control+C | 截图确认是取消测试，日志确认 interrupted；待处理标记为 0，任务退出等待 |

三种人工动作分别核对，不能因为拒绝的底层结果是 cancel，就省略独立取消操作。独立取消测试已另行完成。

本机为 Codex CLI 0.165.0-alpha.1.2，Hooks 功能启用，8 个用户级观察 Hook 已由用户人工信任。当前构建未加载插件包内 Hooks，故采用官方用户级 hooks.json 合并入口。不写入信任状态或修改日常审批策略。

## 安全与边界

观察器保持空 stdout、正常返回，不返回 allow、deny、permissionDecision、continue 等控制字段，不修改工具参数，不使用绕过 Hook 信任的参数。仅记录会话/轮次、工具匹配摘要和待处理计数，不保存命令、提示词、工具输出。正常非审批事件不创建状态文件，全部结束后删除 JSON。并发请求逐个解除，旧轮次回调不清除新轮次。

没有独立 PermissionResolved Hook。允许后通常在 PostToolUse 清除，拒绝通过 PreModelRequest/Stop 收尾，取消通过 Interrupt/日志 turn_aborted 收尾。因此不能承诺点击按钮瞬间切换；长命令执行中可能仍显示 WAITING。子 Agent 默认不触发顶层等待提示。

## 独立 decline 的能力检查

原生 CLI 的 No 在本次操作中中断会话，不等同于协议 decline（拒绝命令但继续本轮）。已通过真实 app-server 分别发起 require_escalated 命令审批（on-request + read-only）和普通脚本审批（untrusted + read-only）。两者 availableDecisions 都只有 accept、acceptWithExecpolicyAmendment、cancel，没有 decline；没有强行发送未提供的选项。诊断请求已撤回，未批准或执行其待审批命令。

`manual_decline.py` 保留为未来运行时能力诊断入口，仅在人为点击后回传服务器提供的 decline/cancel，没有允许路径。命令结果、请求解除、本轮状态来自真实 app-server，Hook 等待来自现有观察器，没有注入伪造审批。过期请求、终止和断线会使按钮失效，旧点击不会回传决策。该入口的单测不替代真实人工验收。

## 复现入口

在单独的交互式 Codex CLI 中使用 on-request + read-only，要求仅尝试一次需要人工审批的无害 printf，不访问个人文件/网络，不自动批准、不重试。审批出现后停留两秒观察 WAITING，再分别做仅本次允许、No、Control+C。注意不要选保存放行规则，否则后续可能不再弹出审批。

当前父聊天自身是 never 审批策略，不能在这里强行请求审批；真实验收通过独立交互式 CLI 完成。若环境没有弹出真实审批，则该轮不能计为验收。独立拒绝但继续仅在服务器明确提供 decline 时才能测试。

官方协议：https://learn.chatgpt.com/docs/app-server#approvals
官方 Hooks：https://learn.chatgpt.com/docs/hooks

重启边界：新 Host 只接受其启动后更新的 Hook 待处理记录；不会因回放旧未结束轮次而恢复历史 WAITING。代价是若审批已打开时重启桌宠，在没有新 Hook 更新前可能暂不显示该等待。该保守行为有回归测试覆盖。
