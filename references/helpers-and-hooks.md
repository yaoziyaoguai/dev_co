# 辅助脚本与可选 Hook

**按需读取：** 确实使用辅助命令或配置 Hook 时打开；常规开发和人工维护记忆无需接入脚本。

章节导航：首次接入/配置字段 → `先接入已有记录`；接手摘要、检查与证据 → `四个命令`；用户选择 Hook 后 → `Hook：先生成可审阅配置`。执行时读取所选章节的完整限制，不只复制命令。

适用边界：运行脚本并读取必要输出，只有修改或排错才读实现。`brief` 有长度上限，缺失内容按需回查；`verify/gate` 只涉及声明范围，不证明验收充分或赋予发布权限。脚本不隔离网络、不硬控预算、不自动脱敏。Hook 不随技能安装启用，须保留宿主设置并按要求信任、验证。

Python 3.10+ 标准库，支持 macOS/Linux 的本地进程管理。命令中的 `$SKILL_ROOT` 表示当前 `SKILL.md` 所在的**实际绝对目录**，使用前将其设为已发现路径；`$PROJECT_ROOT` 同样指实际项目根目录。不需要安装依赖或读取凭据。

原名 `start-software-project` 的项目记录仍可读取；新建记录使用 `workflow: dev_co`。不需要为了技能改名重建项目文档。旧意图/文件指纹的功能证据会失效一次，按原有相关检查重新验证；无需因此扩大检查范围。仓库 schema 1 基线的处理见[基线来源与换增量](repository-lifecycle.md#基线来源与换增量)，不能通过重跑测试自动迁移。

## 先接入已有记录

没有当前记录、且需要持续开发/交接时：

```sh
python3 "$SKILL_ROOT/scripts/project_workflow.py" init --root "$PROJECT_ROOT" --goal "本轮要交付的结果"
```

默认创建 `docs/CURRENT.md`，存在则拒绝覆盖。已有文档先复用；可在不丢失原文的前提下手工加入下面的 JSON frontmatter，并用 `--state docs/PROJECT.md` 指定。若原文格式不适合接入，继续人工维护原记录，无需为脚本另建一套记忆。

```markdown
---
{
  "workflow": "dev_co",
  "schema": 1,
  "phase": "repair",
  "status": "active",
  "goal_revision": 2,
  "environment": "local / Python 3.12 / offline fixture",
  "verification": {
    "level": "targeted",
    "reason": "只改 CSV 导入及其调用方契约。",
    "freshness": "content",
    "inputs": ["src/importer", "tests/test_importer.py", "pyproject.toml"],
    "checks": [
      {
        "id": "importer-regression",
        "argv": ["python3", "-m", "unittest", "tests.test_importer"],
        "cost": "local",
        "timeout_seconds": 60
      }
    ]
  }
}
---

保留现有正文：目标、验收、决定、导航、推进约定、最近验证、下一步。
```

命令和路径只是示例，使用项目真实可运行的检查；缺少文件即失败。`phase` 为 explore/shape/build/repair/recover/deliver，`status` 为 active/needs-user/blocked/paused/ready/done。`verification.level` 为 none/targeted/integration/release。无自动检查时 checks/inputs 留空并记录实际人工验收，不为凑数编造检查。

自动识别 `docs/CURRENT.md`、`docs/PROJECT.md`、`CURRENT.md` 中带该标记的文件。自定义路径要在项目入口和 Hook 配置中保持一致。所有状态、证据和声明输入必须在项目根目录内；状态/证据路径不能经过符号链接。把生成的 `.project-workflow/` 加入适用的忽略规则前先检查现有约定；原始日志可能含项目信息，不自动提交或上传。

可选字段：`brief_sections` 在 frontmatter 顶层指定现有二级章节的实际标题列表；默认选择本轮目标、验收标准、项目约束、当前决定、代码导航、推进约定、最近验证、下一步。它只决定恢复摘要，不决定意图指纹的排除范围。需要自定义进展标题时使用下述 `non_intent_sections`。

`verification.repository_policy` 指定已接入的仓库规则文件（例如 `devco-repository.json`），同时必须提供与当前基线相同的 `verification.repository_scope`（例如 `quote-v2`）。由 gate 即时检查文件归属、引用和更新义务；接入与范围见[仓库增量维护](repository-lifecycle.md)。已有原生状态格式可以单独运行仓库检查，不必迁移为这里的 frontmatter。

### 验证输入的选择

`inputs` 声明检查实际依赖的项目内文件或目录，包括引用的有效规格、契约、测试和相关配置。目录只展开声明范围：

- Git 工作树使用已跟踪文件和未被 Git ignore/exclude 忽略的未跟踪文件；已跟踪生成源码仍参与。Git 枚举失败会报错，不静默退回另一套范围。
- 无 Git 项目排除常见工具缓存。两种模式都可用 `verification.exclude` 额外排除目录展开结果，例如 `["src/build/", "fixtures/output.json"]`；使用规范相对路径，目录以 `/` 结尾，不支持 glob。
- 显式声明的真实文件优先于普通缓存、Git ignore 和 `exclude`。真正依赖的 ignored 文件要逐个明确纳入；敏感路径、项目边界、状态/证据路径限制始终保留。
- 只核对最终选中的符号链接，记录链接身份但不递归跟随。内部目标必须实际进入选中范围；整个目标目录被过滤时，仅把目录名写进 inputs 不够，须补齐真实依赖文件。外部、断裂或无法证明覆盖的链接报错，不自动读取外部内容。覆盖承诺限于声明范围，不推断构建器的全部依赖。

指纹包含普通文件内容、类型和执行位，忽略修改时间。源码增删改、执行位及链接目标变化都会使相关证据失效；上限为 5,000 个选中条目、单文件 8 MB、总内容 64 MB。范围过大时选择本轮相关模块，不默认扩大上限。

## 四个命令

```sh
python3 "$SKILL_ROOT/scripts/project_workflow.py" brief --root "$PROJECT_ROOT"
python3 "$SKILL_ROOT/scripts/project_workflow.py" verify --reuse --root "$PROJECT_ROOT"
python3 "$SKILL_ROOT/scripts/project_workflow.py" gate --root "$PROJECT_ROOT"
```

`brief` 对短记录沿用全文；长记录按恢复章节提取原文、保留正文位置，明确报告截断、缺项和同名段落歧义，并列出其他章节导航。缺口需要按本轮问题补读，不把摘录当作完整语义总结。新会话/上下文丢失时恢复一次；上下文仍有效就不反复调用。

`verify --reuse` 核对功能证据；有效时返回 `reused: true`，不运行测试、不重写日志。证据失效才执行声明的 argv 并记录结果；确有重测需要时省略 `--reuse`。执行前检查配置、输入边界和仓库基线来源，非法时不启动检查；普通资料更新、归属或引用待补不会阻止功能检查。命令不启用 shell 字符串，保留子检查退出码、超时、日志和输入指纹。

`gate` 不运行功能测试，组合功能证据与当前仓库检查：`verification_ready` 表示功能证据有效；配置了仓库规则时，最终 `ready` 要求它与 `repository.ready` 都为真。顶层 `reasons` 汇总两类未满足项。`reused` 只说明功能证据复用，不说明整个增量完成；仅补不影响检查输入的资料，可以复用原功能结果。

退出码：0 表示最终 `ready=true`；1 表示功能证据缺失/失败/过期或仓库条件未满足；2 表示配置、来源或读取错误。功能通过但资料待补仍返回 1，补资料后 `--reuse` 可返回 0 且不增加执行次数。子检查的实际退出码保存在证据中；init/brief 的 0 仅表示该命令成功。验证集中在增量验收、重要变更和交接，不每条回复/每次编辑运行；需要正文或源码才能判断的问题不能靠省略读取解决。

证据位于 `.project-workflow/evidence/<run-id>/` 和 `latest.json`，保存项目路径、执行时的分支/HEAD、声明文件内容、当前意图、检查计划、环境标签与日志。`verification.freshness` 决定 Git 信息是否影响证据复用：

- `content`：适用于只依赖声明文件和环境的检查。空提交或仅换分支不使证据失效，报告仍保留实际验证时的 Git 来源，不冒充在新提交上重新执行。
- `git`：检查读取版本号、提交历史或分支行为时使用；HEAD 或分支变化也会使证据失效。

这是功能证据的依赖选择。仓库基线独立绑定 scope、分支与祖先来源，因此 `content` 功能证据有效而仓库来源不匹配时，最终仍不能通过。

`init` 新记录显式使用 `content`；配置检查时确认相关依赖均已声明，涉及 Git 就改为 `git`。已有记录省略该字段仍按 `git` 处理；切换模式改变计划，需重新验证，不能直接沿用旧结果。两个模式都绑定项目根、声明输入、意图、计划、环境和日志。

未提交的输入变化同样会被检测；运行中上述依赖变化使结果失效。每次新执行先让旧通过记录失效，防止异常时回退成“已通过”。`verify.lock/owner.json` 记录运行进程；遇到遗留锁先核对进程，再清理确认已结束的本任务锁，不能自动删锁并行重跑。

默认不将正文中独立的二级段落 `## 最近验证`、`## 下一步`、`## 接手记录`、`## 候选想法` 纳入意图指纹。可在 frontmatter 顶层设置 `"non_intent_sections": ["Next steps", "Verification notes"]`，按二级标题解析后的标题精确匹配；显式列表替换默认集合，`[]` 表示不排除任何章节。列表元素须为非空标题字符串，字符串等非法配置会报错；改变列表本身也会使意图指纹失效。

排除范围到下一个 `#` 或 `##` 标题；顶层反引号/波浪号围栏中的标题不切换段落。缩进、列表或引用中的开围栏，以及未闭合围栏，会保守地将整篇正文纳入指纹，不尝试完整 Markdown 容器解析。**目标、验收与有效决定必须写在有效段落，不能只塞进被排除的段落**。候选被采纳时移入目标、决定或验收，必要时递增 goal_revision。脚本无法辨别误放进排除段落的真实需求；其他段落中的“候选”字样也不会被自动排除。phase/status 是流程标签，不能用改成 done 代替验证。

文件选择按上述规则排除生成证据和敏感文件名，并拒绝越界路径；这不是通用秘密检测器。`cost: local` 是配置声明，**不是网络沙箱**：argv 中的任意程序仍可能访问网络或写文件。执行前检查命令，只有符合当前授权的本地检查才用 verify。日志不自动脱敏；不要把敏感输出送入它。

指纹不覆盖未声明的依赖、系统库、时钟、外部服务和环境变量，也不证明检查足够全面。更换真实运行环境应更新 environment/计划并重新验证。脚本和证据可被编辑，不构成对抗性防篡改机制。

一个工作树保留一份当前计划和一份 `latest.json`。复用粒度是整个计划：A、B 两项检查在同一计划时，相关输入变化会重新执行两项，没有逐项缓存。已有任务系统/CI 的有效结果可按其原有规则使用，不为保存每项历史通过而反复切换本辅助计划；最终合并版本的验收责任仍在交付者。

## Hook：先生成可审阅配置

```sh
python3 "$SKILL_ROOT/scripts/workflow_hooks.py" --host codex --root "$PROJECT_ROOT" --print-config
python3 "$SKILL_ROOT/scripts/workflow_hooks.py" --host claude --root "$PROJECT_ROOT" --print-config
```

按需加 `--state docs/PROJECT.md`。输出只是配置片段，**不会安装或启用**。保留宿主原有 hooks，仅合并用户选择的部分，推荐先在单一试用项目启用：

`--root` 与验证 CLI 选择同一个项目根：状态路径、inputs 和证据都相对它解释。生成时将根固化为绝对路径，相对路径按命令进程当前目录解析。子项目必须显式指定自己的根，否则兼容旧配置，按事件 cwd 寻找 Git 顶层。显式根不存在或不是目录时报错；根存在但缺少记录时不回退到父项目。事件 cwd 经解析后必须是固定根本身或其子目录；其他项目的 SessionStart 不注入内容，已选 PreToolUse 保护返回 deny。固定根的配置只用于对应项目，不作为全局通用配置。

启用前先用 `brief` 确认当前记录已经接入且内容正确。只有普通 Markdown、尚无上述 frontmatter 的记录仍能人工接手，但这些适配器不会识别它；应就地接入并保留原文，或明确继续采用原生/人工记录。不能只放入配置就告诉用户“自动记忆已经生效”。

- Codex：使用当前版本支持的项目 `.codex/hooks.json`/活动配置层；按 `/hooks` 审阅并信任确切定义，改变定义后重新信任。禁止用绕过信任的选项。
- Claude Code：合并到项目 `.claude/settings.json` 的 hooks；通过 `/hooks` 检查，按该版本要求重新载入会话。
- 配置使用生成时 Python、脚本及显式项目根的绝对路径，换机器、移动技能或项目后需要重新生成。

行为：

- **SessionStart**：发现接入的当前记录时注入简短上下文。仍需读取本技能和本轮相关代码；没有接入的项目不创建文件。
- **Stop（可选）**：默认不生成，也不读取状态或扫描输入。明确选择每回合结束提醒时，加 `--check-on-stop` 生成对应配置；explore/shape/recover 或 needs-user/blocked/paused 跳过，其余只提醒证据缺口，不执行测试、不强制续跑。项目仍处于 build 不能证明当前回合是实施请求。旧配置若指向本次更新脚本，原来的无参数 Stop 也不再驱动续跑；需要提醒时重新审阅、生成并按宿主要求加载。
- **可选 PreToolUse**：仅为明确选定的精确工具名，用重复的 `--protect-tool TOOL_NAME` 生成 matcher。对这些调用，未接入记录、读取失败或证据不满足时返回 deny；通过时返回空对象，让宿主继续正常权限流程。不要泛配所有 shell 调用，否则可能把修复/验证本身锁死。

未指定保护工具时不生成 PreToolUse。它只覆盖匹配的宿主工具入口，不能保证其他工具、脚本内部调用、发布/付费请求都被拦住。项目配置和数据都可被 agent 修改；真正权限、预算与不可绕过约束由宿主或外部受控系统承担。

跨宿主只共享记录与检查逻辑，实际载入、信任、超时/错误处理仍由各宿主决定。协议模拟测试不等于真实会话集成成功；启用后验证开始注入和明确选用的事件，不把未配置的事件列作已生效。

官方协议参考（使用新版本宿主时先核实变化）：[Codex hooks](https://learn.chatgpt.com/docs/hooks)、[Claude Code hooks](https://code.claude.com/docs/en/hooks)。
