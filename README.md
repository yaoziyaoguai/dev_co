# dev_co

给刚开始用 AI 做完整项目，又经常把目标和上下文聊丢的人。

![dev_co：两个开发工具共用一本当前计划，沿着小步骤推进](assets/dev-co-cover.png)

`dev_co` 是供 Codex 和 Claude Code 共用的开发协作技能。它让 Agent 在持续开发中维护当前目标、分清决定和想法、交付能检查的小结果，并留下下一次接手需要的记录。

它来自我和 AI 协作时遇到的麻烦和顾虑：边做边改主意，担心旧要求仍被沿用；换了 Agent，又得重新解释项目；只改一个小模块，也可能等来一整套回归。于是，我和 AI 把这些问题逐条整理成了这份技能。

**这是一套有个人取舍的工作习惯，主要给遇到类似问题的新手参考。** 如果你的项目已经有清楚的需求管理、交接和验证流程，沿用原流程就好，也可以只借用其中几条。

我把这次复盘、试用中的反例和设计取舍写在了这篇文章里：[我把和 AI 开发时反复踩的坑，写成了 dev_co](https://wangjinkun333.me/blog/dev-co-for-beginners)。

## 你可能会用到它

- 经常补充新想法，却没说清哪些替换旧要求、哪些只是候选。
- 在 Codex 和 Claude Code 之间切换，项目记忆各留一份，接手时互相冲突。
- 看着 Agent 一直忙，却不确定这一轮有什么可以实际试用的结果。
- 不知道这次该测多少，容易在漏测和无理由的全量回归之间来回摆。
- 装了很多技能，担心它们自动触发后把简单工作变复杂。

使用时，你仍然要决定想解决的问题、接受哪些取舍，并查看实际结果。技能负责提醒和组织过程，不能代替这些判断，也不能保证模型每次都照做。

## 一轮开发会怎样推进

目标已经清楚的持续开发，通常按这个节奏走：

1. **恢复当前状态。** 读项目入口和当前记录，确认有效目标，再沿导航看相关代码。
2. **选一个可交付结果。** 说清这一轮做什么、暂缓什么、怎样判断完成。可发现的信息先自己查。
3. **实现这一小步。** 沿用已经接受的要求和授权；新想法先记为候选，明确改向才替换旧决定。
4. **按影响验证。** 先做最小有意义的检查，完成项目要求，有依据时再扩大范围。
5. **留下接手信息。** 更新有效决定、验证结果、尚未确认的部分和下一步。

新项目如果连用途和第一版都没想清楚，先收敛这些问题。它不要求把所有阶段从头跑一遍，也不替个人项目强制增加 PR。

## 安装

适用于 Codex / Claude Code。下面的共用安装方式面向 macOS/Linux，需要 Git 和 Python 3.10+。

```sh
git clone https://github.com/yaoziyaoguai/dev_co.git ~/work_space/dev_co
cd ~/work_space/dev_co
```

然后把两个宿主的入口链接到同一份源码。以下命令发现任一已有安装就会退出，不覆盖或移动文件；已有安装请先比较、备份，再决定是否替换。

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

使用自定义 `CODEX_HOME` 时，将 Codex 的目标改为该目录下的 `skills/dev_co`。只用一个宿主，可以只保留相应目标。其他环境可以复制技能文件到宿主的技能目录；两个独立副本需要自行同步。

安装后开启新会话。Codex 用 `$dev_co`，Claude Code 用 `/dev_co`。已有会话读过旧版时，需要重新读取技能。

## 先拿一个真实的小任务试用

在 Codex 中可以这样开始；Claude Code 把 `$dev_co` 换成 `/dev_co`：

```text
使用 $dev_co 继续这个项目。先读已有记录，确认现在有效的目标。
这一轮只解决 CSV 导入丢失前导零的问题，保留原字段和备注。
验证受影响的行为，把结果和下一步更新到原来的项目记录。
```

还在讨论新项目时，可以直接说：

```text
使用 $dev_co 帮我讨论一个自用工具。我还没决定第一版做什么。
先帮我找出最值得解决的具体问题，暂时不要改代码。
```

先观察它有没有正确区分讨论和实施、有没有沿用已有记录、有没有把测试范围解释清楚。发现具体反例后再调整规则，比一次塞进很多要求更容易判断效果。

## 什么时候自动用

按当前任务的意图判断，而不是看到仓库、代码或 `CURRENT.md` 就启动。

| 当前任务 | 默认选择 |
| --- | --- |
| 规划准备构建的软件/系统、持续功能开发、复杂修复、恢复开发和交接 | 使用 dev_co |
| 开发或改造评测系统，验证当前开发增量 | 使用 dev_co |
| 独立跑评测、benchmark、模型对比、结果分析、调研报告 | 直接处理任务 |
| 一次性脚本、孤立小修改、普通代码问答、单次审查 | 直接处理任务 |

你可以明确调用、退出，或选择其他主流程。历史上用过这个技能，不意味着以后每一轮都必须使用。

技能允许宿主自动匹配。希望更稳定地选用时，可以加下面的全局入口；这是给 Agent 的加载指令，不是执行保证，也不需要你每轮重复念技能名。

<details>
<summary>可选：把路由约定合并到全局 AGENTS.md / CLAUDE.md</summary>

Codex 通常使用 `~/.codex/AGENTS.md`，Claude Code 使用 `~/.claude/CLAUDE.md`；自定义 `CODEX_HOME` 时使用对应位置。保留已有约定，不用这段替换整份文件。

```markdown
### Development Skill Routing

- Choose `dev_co` by the current task's intent: load it for scoping a software/system product to build, sustained feature development, complex or multi-step repairs, and development recovery or handoff. Building or refactoring an evaluation system qualifies; verification of the current development increment stays within that workflow.
- Do not auto-load `dev_co` for standalone evaluations, benchmarks or model comparisons, results analysis, reports or research, code questions or one-off reviews, throwaway scripts, or small isolated text/configuration/bug fixes. A software repository, code execution, a current-state file, or previous `dev_co` use is not sufficient. Follow applicable project requirements without starting this workflow. Honor explicit invocation, opt-out, and a user-selected primary workflow.
- When applicable, load it before substantive development using the host's native skill-invocation tool, or read its installed `SKILL.md`. Resolve the catalog path, falling back to `~/.codex/skills/dev_co/SKILL.md` or `~/.claude/skills/dev_co/SKILL.md`; do not rely solely on implicit matching. Reuse loaded content, reloading only after changes or context loss; read references only as needed.
```

权限和指令优先级仍由宿主决定。本技能内的 `lfg`、`review`、`qa` 只在用户明确选用时加载；安装 dev_co 不会修改其他技能自身的自动调用设置。已有技能存在冲突时，需要分别检查其入口和配置。

</details>

## 项目记忆放哪里

优先沿用项目已有的记录或任务系统。持续开发、交接确实需要，而项目又没有当前记录时，才补 `docs/CURRENT.md`。

```text
AGENTS.md / CLAUDE.md   项目命令、约束，以及当前记录的入口
README.md              产品怎样使用、启动和验证
docs/CURRENT.md         当前目标、决定、代码导航、证据和下一步
docs/decisions/         需要长期保留的少量重要取舍，可选
docs/archive/           已完成阶段的长记录，可选
```

当前记录里，要能分清“已经决定”“还在考虑”“已被替代”。改变方向时，更新受影响的目标和决定，保留其他仍然有效的要求；不要只在旧计划末尾再加一句话。

把摘要放在这份记录开头，历史通过链接追溯。换 Agent 后，先读摘要和本轮相关代码；源码仍要核实，记录负责提供意图和导航。详见[当前记忆与交接](references/memory-and-handoff.md)。

## 测试和开发方法怎么选

局部逻辑修复从复现和相关测试开始；接口、持久化或跨模块行为变化，再补契约与集成检查；发布候选按项目要求检查核心路径。小改不默认全量 E2E，也不能以“节省时间”为由跳过项目必需检查。

TDD 适合行为已经清楚、可以先复现失败的改动。需求和接口还含糊时，先写清行为、边界和验收，采用 SDD 中先明确规格的做法；小任务几行就能说清，不必额外生成一套文档。这里没有强制的 TDD / SDD 流水线。

“本地测试通过”“真实服务可用”“已经部署”“用户认可效果”分别报告。按影响选择检查的具体说明见[验证范围与失控恢复](references/verification-and-recovery.md)。

## 想加一些可执行的检查

日常使用可以只靠技能和现有项目记录。需要核对验证证据时，再接入辅助脚本：

| 命令 | 作用 |
| --- | --- |
| `init` | 在确有需要、且记录不存在时初始化当前记录 |
| `brief` | 输出有长度上限的项目摘要 |
| `verify` | 执行事先声明的本地检查，记录结果与相关输入 |
| `gate` | 检查声明范围内的证据是否缺失、失败或已经过期 |

从仓库根目录查看用法：

```sh
python3 scripts/project_workflow.py --help
python3 scripts/workflow_hooks.py --help
```

已有记录的接入格式和可选 Hook 配置见[辅助脚本说明](references/helpers-and-hooks.md)。Hook 默认不启用；配置生成、宿主加载和实际触发需要分别确认。

`gate` 通过，只说明声明范围内的证据仍匹配。它不会自动判断测试是否充分，也不授予发布权限。脚本不隔离网络、不硬控预算、不自动脱敏日志。

## 仓库结构与验证

```text
SKILL.md                    日常加载的精简核心与按需入口
agents/openai.yaml          Codex 展示信息和隐式调用策略
references/                 当前环节需要时才读的详细指南
scripts/project_workflow.py 项目摘要、检查执行和证据核对
scripts/workflow_hooks.py   可选 Hook 配置生成与事件适配
tests/test_workflow.py      标准库行为测试
assets/                     封面及生成说明
```

辅助脚本仅依赖 Python 3.10+ 标准库，进程管理面向 macOS/Linux。

```sh
python3 -m unittest discover -s tests -v
```

当前 43 项脚本行为测试通过，覆盖记录兼容、证据失效、失败与中断、进程清理、路径边界和 Hook 事件适配。也在 Codex CLI 0.154.0、Claude Code 2.1.280 中做过有限场景试用，检查加载、接手和任务范围选择；这些结果不能证明所有模型、项目或长期协作都同样有效。Hook 的协议测试也不能代替宿主里的实际验证。

`dev_co` 的下划线是有意保留的命名。一些仅允许连字符的通用模板校验器会拒绝它，上述两个宿主已验证可以加载。

欢迎带着具体反例提 issue：当时要求做什么、实际发生了什么、哪个宿主，以及你认为应该怎样处理。分享前删掉凭据和私有项目内容。涉及触发范围的修改，需要同时检查该使用和不该使用的场景。

## 许可证

采用 [MIT License](LICENSE)。允许使用、修改和再分发，包括商业使用；分发时保留版权和许可声明。完整条款以 LICENSE 为准。
