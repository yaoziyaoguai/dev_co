# 历次宿主与回归验证记录

本文件归档 `dev_co` 各重要版本在双宿主（Codex CLI / Claude Code）与多操作系统（macOS / Linux）上的验证结果。日常安装与使用说明见 [README.md](../README.md)。

## 2026-11-23 v4 审计修复与仓库自举验证

围绕宿主恢复预算、Git 异常与超时边界、目录软链覆盖、混合标题指纹、信号清理与文档体系完成修复，并新增 `devco-repository.json` 自举规则与跨平台 GitHub Actions CI 矩阵。

| 验证 | 实际结果 |
| --- | --- |
| `SessionStart` 字节预算 | Codex 按 3,800 UTF-8 字节守卫（低于 `additionalContextLimit: 4000`），长中文目标按 UTF-8 字节提取并显式标记截断，保留末尾验收与下一步；手工 `brief` 仍完整返回短记录。 |
| Git 与软链边界 | 损坏 `.git` 或权限异常拒绝静默降级为无 Git 遍历；`git_value` 超时显式报错，`brief` 工作树查询超时输出明确核对提示；指向祖先或部分覆盖的目录软链均被拦截。 |
| 信号与跨环境锁 | `SIGHUP` 与 `SIGTERM` 一并清理子进程组并释放 `verify.lock`；`owner.json` 记录 `host` 与启动时间，跨容器共享目录不再将异机锁误报为已退出进程。 |
| 链接、模板与评测 | 4 空格嵌套列表失效链接可检出，列表内代码围栏保持忽略；`.env*` 大小写不敏感拦截并放行 `.env.example` 等无密钥模板；`eval_scenarios.py verify-clean` 增加 `.git/refs` 比对。 |
| Linux 双环境回归与自检 | 默认 UTF-8 与 `LC_ALL=C PYTHONUTF8=0 PYTHONCOERCECLOCALE=0` 各通过全部 187 项标准库单元测试；`repository_check.py` 对本仓 40 个文件与 19 份 Markdown 文档（含本地锚点）自检通过，0 失效引用。 |

## 2026-11-22 v3 修复验证

Codex CLI 0.166.0 和 Claude Code 2.1.330 均从临时 Git 项目的子项目 `src/` 目录启动。两宿主先使用本地固定响应，再在修复版本 `a3435b7` 上各跑一次实际模型会话。两轮均由真实 CLI 加载和执行 Hook，使用会话级临时配置。

| 验证 | 实际结果 |
| --- | --- |
| 固定响应的 `SessionStart` | 子项目的 `docs` 软链指向父仓共享目录。有独立 `CURRENT.md` 时，两宿主都收到子项目标记。子项目没有独立记录时，两宿主都收到父仓标记。 |
| 固定响应的 `PreToolUse` | 配置精确匹配 `Bash`。正常检查通过时，命令创建了测试文件。向就绪检查注入 `RuntimeError` 后，Hook 以退出码 2 结束，两宿主都报告拦截，测试文件均未创建。 |
| 实际响应模型 | Codex 使用 `gpt-6.2-sol`，Claude Code 使用现有配置返回的 `zcode/GLM-5.3`。 |
| 实际模型的 `SessionStart` | `docs` 软链指向含干扰标记的父仓共享目录。两模型都准确回显了子项目自身 `CURRENT.md` 的随机标记。 |
| 实际模型的 `PreToolUse` | 向就绪检查注入 `RuntimeError` 后，Hook 返回退出码 2。两宿主均拦截各自唯一一次 `Bash` 调用，测试文件均未创建。 |
| macOS 全量回归 | Python 3.14.7 下，默认 UTF-8 和 `LC_ALL=C PYTHONUTF8=0 PYTHONCOERCECLOCALE=0` 各通过 175 项，各跳过 1 项仅适用于 Linux 文件系统的用例。 |
| Linux 全量回归 | Python 3.11.2 下，使用严格 ASCII 环境及实际挂载为 `noexec` 的 `/tmp`，176 项全部通过。 |
| 评测场景 | 22 个场景均完成初始化和只读核对。独立审查场景仅有预期的两处未暂存差异。 |

## 2026-11-22 de-slop 接入验证

在临时 Git 项目中使用独立安装的 `de-slop` 验证技能加载、调用顺序和修改范围。

| 验证 | 实际结果 |
| --- | --- |
| 双宿主加载 | Codex CLI 0.166.0 用 `$de-slop`，Claude Code 2.1.330 用 `/de-slop`。两个宿主都识别了技能并完成只读报告 |
| 持续开发 | Codex 实现汇总后检查并清理本轮未跟踪的 `amounts.py`，保留外部 JSON 校验和同文件历史函数。随后运行最终测试和 `verify --reuse`，`gate` 返回 0 |
| 独立清理 | Claude Code 自行选用 `de-slop`，仅清理本轮差异中的内部兜底。历史函数及暂存区保持原样，3 项针对性测试通过 |
| 只读验收 | Codex 在 `dev_co` 回合使用 `de-slop` 仅报告。前后的文件内容、Git 状态和暂存区差异一致 |
| 标准库回归 | Linux 上 Python 3.11.2 的严格 ASCII 环境通过全部 155 项。macOS 上 Python 3.12.2 通过 154 项，跳过 1 项 Linux 专属用例 |

## 2026-11-22 验证记录

| 验证 | 实际结果 |
| --- | --- |
| 标准库回归 | Linux 上 Python 3.11.2 的严格 ASCII 环境通过全部 154 项。macOS 上 Python 3.12.2 通过 153 项，跳过 1 项 Linux 专属用例 |
| 真实宿主 Hook | Codex CLI 0.166.0 和 Claude Code 2.1.330 均在临时 Git 项目中从子目录启动，读取 `--root` 和 `--state` 指定记录的独有标记。正常场景的 `Bash` 调用创建了测试文件。向 `PreToolUse` 注入 `RuntimeError` 后，脚本返回退出码 2，两个宿主都拦截了同一个工具调用 |

## 2026-11-21 验证记录

| 验证 | 实际结果 |
| --- | --- |
| 标准库回归 | macOS 上 Python 3.12.2 全套 133 项通过，Python 3.14.7 的 39 项相关检查通过 |
| 证据复用 | 同一临时项目中，有效证据仍只需 1 次输入快照。证据过期后的重跑从 4 次降到 3 次，写入证据后的输入变更仍会被最终检查发现 |
| 安装 | 在临时宿主目录验证双宿主链接、单宿主选择、已有安装和损坏链接的保护 |
| 真实宿主 Hook | 对 `ff99eb9` 的改动进行实测。Codex CLI 0.166.0 和 Claude Code 2.1.330 均在启动时读取指定子项目的记录，正常 `Bash` 调用成功。向 `PreToolUse` 注入 `RuntimeError` 后，脚本返回退出码 2，两个宿主都拦下了测试命令 |
| Hook 配置 | `clear`、`fork` 匹配和长摘要回退通过本地测试。真实会话实测覆盖 `startup` 和选定工具的异常拦截 |

此前还在本地演练了两模块报价 CLI、老项目增量维护、证据失效与 scope 错配，并核对了 Codex、Claude Code、OpenCode、ZCode 的共用安装链接。[2026-11-08 验证版本](https://github.com/yaoziyaoguai/dev_co/commit/72a7fdd6ef99361bf43a11d5e729e32d852de745)
