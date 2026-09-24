# dev_co

供 Codex 和 Claude Code 共用的开发协作技能。围绕当前目标、小步交付、按影响验证和项目记忆组织持续开发；资料按当前任务需要展开。

## 适用范围

| 当前任务 | 默认使用 dev_co |
| --- | --- |
| 软件/系统产品规划、持续功能开发、复杂修复、恢复开发和交接 | 是 |
| 开发或改造评测系统，以及当前开发增量的验证 | 是 |
| 独立评测、模型对比、结果分析、调研报告 | 否 |
| 一次性脚本、孤立的小修改、普通代码问答、单次审查 | 否 |

按本轮任务意图判断；项目目录、已有当前记录或历史上使用过技能，都不足以单独触发。用户可以明确选用或退出，也可以选择其他主流程。个人项目不默认要求 PR，不因小改就跑全量 E2E。

## 安装

先克隆仓库，已有本地仓库则直接进入目录：

```sh
git clone https://github.com/yaoziyaoguai/dev_co.git ~/work_space/dev_co
cd ~/work_space/dev_co
```

在 macOS/Linux 上，可以将两个宿主的技能入口都链接到这一份源码。以下命令需要 Python 3.10+；发现任一已有安装会先退出，不覆盖或移动用户文件。已有安装请先比较、备份，再决定是否替换。

```sh
python3 - <<'PY'
from pathlib import Path

source = Path.cwd().resolve()
if not (source / "SKILL.md").is_file():
    raise SystemExit("请在 dev_co 仓库根目录执行。")
targets = [Path.home() / host / "skills/dev_co" for host in (".codex", ".claude")]
existing = [str(path) for path in targets if path.exists() or path.is_symlink()]
if existing:
    raise SystemExit("请先检查并备份已有安装：\n" + "\n".join(existing))
for target in targets:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(source, target_is_directory=True)
print("Codex 和 Claude Code 已链接到：", source)
PY
```

使用自定义 `CODEX_HOME` 时，将 Codex 的目标改为该目录下的 `skills/dev_co`。其他环境也可以复制技能文件到宿主的技能目录；两个独立副本需要自行保持同步。

安装后在新会话中使用。Codex 可明确调用 `$dev_co`，Claude Code 可调用 `/dev_co`；已有会话若加载了旧内容，重新读取技能即可。技能允许宿主自动匹配，但这不等于所有任务都默认进入它。

### 可选的全局入口

需要更稳定的自动选择时，把下面的路由约定合并到 Codex 的 `~/.codex/AGENTS.md` 和 Claude Code 的 `~/.claude/CLAUDE.md`；自定义 `CODEX_HOME` 时使用对应位置。保留已有约定，不用这段文字替换整份文件。

```markdown
### Development Skill Routing

- Choose `dev_co` by the current task's intent: load it for scoping a software/system product to build, sustained feature development, complex or multi-step repairs, and development recovery or handoff. Building or refactoring an evaluation system qualifies; verification of the current development increment stays within that workflow.
- Do not auto-load `dev_co` for standalone evaluations, benchmarks or model comparisons, results analysis, reports or research, code questions or one-off reviews, throwaway scripts, or small isolated text/configuration/bug fixes. A software repository, code execution, a current-state file, or previous `dev_co` use is not sufficient. Follow applicable project requirements without starting this workflow. Honor explicit invocation, opt-out, and a user-selected primary workflow.
- When applicable, load it before substantive development using the host's native skill-invocation tool, or read its installed `SKILL.md`. Resolve the catalog path, falling back to `~/.codex/skills/dev_co/SKILL.md` or `~/.claude/skills/dev_co/SKILL.md`; do not rely solely on implicit matching. Reuse loaded content, reloading only after changes or context loss; read references only as needed.
```

这只是入口约定，实际权限和指令优先级仍由宿主决定。`lfg`、`review`、`qa` 在本技能内仅按用户明确选择使用；本仓库不会修改这些技能自身的安装或调用策略。

## 内容结构

```text
SKILL.md                    精简核心、适用边界与按需入口
agents/openai.yaml          Codex 展示信息和隐式调用策略
references/                 新项目、研究、架构、原型、交付、记忆及验证指南
scripts/project_workflow.py 项目摘要、声明范围的验证和证据核对
scripts/workflow_hooks.py   可选的宿主 Hook 配置生成与事件适配
tests/test_workflow.py      标准库行为测试
```

项目记忆优先沿用已有文件。持续开发或交接确有需要而又没有当前记录时，才使用 `docs/CURRENT.md`；历史通过链接追溯，不复制成多份现行计划。

## 可选辅助命令

辅助脚本仅依赖 Python 3.10+ 标准库，进程管理适用于 macOS/Linux。从仓库根目录查看用法：

```sh
python3 scripts/project_workflow.py --help
python3 scripts/workflow_hooks.py --help
```

`init` 按需初始化当前记录，`brief` 输出有界摘要，`verify` 执行声明的本地检查，`gate` 核对这些检查的证据。接入已有记录和配置检查前，阅读[辅助脚本说明](references/helpers-and-hooks.md)。

通过 `gate` 只说明声明范围内的证据仍匹配；它不证明测试充分、真实服务可用、已经部署或用户验收，也不授予任何操作权限。脚本不隔离网络、不硬控预算、不自动脱敏日志。

Hook 默认不启用。生成配置、审阅、合并和宿主信任步骤均见[辅助脚本说明](references/helpers-and-hooks.md)；更换仓库位置后，已生成的绝对路径配置需要重新核对。

## 验证与维护

```sh
python3 -m unittest discover -s tests -v
```

测试覆盖旧记录兼容、证据过期、失败和中断处理、进程清理、路径边界及 Hook 事件适配；临时项目会在测试结束后清理，不需要外部服务。Hook 协议测试不等于宿主实际集成验证，启用 Hook 后仍应验证对应会话行为。

技能目录可以通过上面的链接直接使用本仓库。修改后运行受影响的检查；涉及触发范围时，另外用适用和不适用任务验证实际选择，不因文字校验通过就认定行为正确。

名称 `dev_co` 使用用户指定的下划线。一些只允许连字符的通用模板校验器会拒绝这个名称；已在 Codex CLI 0.154.0 和 Claude Code 2.1.280 中验证实际加载，不能把模板命名检查描述为通过。

仓库尚未指定开源许可证。
