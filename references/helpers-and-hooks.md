# 辅助脚本与可选 Hook

**按需读取：** 确实使用辅助命令或配置 Hook 时打开；常规开发和人工维护记忆无需接入脚本。

章节导航：首次接入/配置字段 → `先接入已有记录`；接手摘要、检查与证据 → `四个命令`；用户选择 Hook 后 → `Hook：先生成可审阅配置`。执行时读取所选章节的完整限制，不只复制命令。

适用边界：运行脚本并读取必要输出，只有修改或排错才读实现。`brief` 有长度上限，缺失内容按需回查；`verify/gate` 只涉及声明范围，不证明验收充分或赋予发布权限。脚本不隔离网络、不硬控预算、不自动脱敏。Hook 不随技能安装启用，须保留宿主设置并按要求信任、验证。

Python 3.10+ 标准库，支持 macOS/Linux 的本地进程管理。命令中的 `$SKILL_ROOT` 表示当前 `SKILL.md` 所在的**实际绝对目录**，使用前将其设为已发现路径；`$PROJECT_ROOT` 同样指实际项目根目录。不需要安装依赖或读取凭据。

原名 `start-software-project` 的项目记录仍可读取；新建记录使用 `workflow: dev_co`。不需要为了技能改名重建项目文档。此次意图解析修复会使旧算法生成的证据失效一次，按原有相关检查重新验证；无需因此扩大检查范围。

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

## 四个命令

```sh
python3 "$SKILL_ROOT/scripts/project_workflow.py" brief --root "$PROJECT_ROOT"
python3 "$SKILL_ROOT/scripts/project_workflow.py" verify --root "$PROJECT_ROOT"
python3 "$SKILL_ROOT/scripts/project_workflow.py" gate --root "$PROJECT_ROOT"
```

`brief` 输出有界摘要、代码导航及当前 Git 状态；不是源码事实认证。`verify` 按 checks 顺序实际执行 argv，不启用 shell 字符串；写出退出码、超时、日志和输入指纹。`gate` 仅核对证据，不运行测试。退出码：0 表示所选自动检查的当前证据满足；1 表示缺失、失败或过期；2 表示配置、运行或读取错误。init/brief 的 0 仅表示该命令成功。

证据位于 `.project-workflow/evidence/<run-id>/` 和 `latest.json`，保存项目路径、执行时的分支/HEAD、声明文件内容、当前意图、检查计划、环境标签与日志。`verification.freshness` 决定 Git 信息是否影响证据复用：

- `content`：适用于只依赖声明文件和环境的检查。空提交或仅换分支不使证据失效，报告仍保留实际验证时的 Git 来源，不冒充在新提交上重新执行。
- `git`：检查读取版本号、提交历史或分支行为时使用；HEAD 或分支变化也会使证据失效。

`init` 新记录显式使用 `content`；配置检查时确认相关依赖均已声明，涉及 Git 就改为 `git`。已有记录省略该字段仍按 `git` 处理；切换模式改变计划，需重新验证，不能直接沿用旧结果。两个模式都绑定项目根、声明输入、意图、计划、环境和日志。

未提交的输入变化同样会被检测；运行中上述依赖变化使结果失效。每次新执行先让旧通过记录失效，防止异常时回退成“已通过”。`verify.lock/owner.json` 记录运行进程；遇到遗留锁先核对进程，再清理确认已结束的本任务锁，不能自动删锁并行重跑。

正文中独立的二级段落 `## 最近验证`、`## 下一步`、`## 接手记录`、`## 候选想法` 不参与意图指纹，范围到下一个 `#` 或 `##` 标题；顶层反引号/波浪号围栏中的标题不切换段落。缩进、列表或引用中的开围栏，以及未闭合围栏，会保守地将整篇正文纳入指纹，不尝试完整 Markdown 容器解析。**目标、验收与有效决定必须写在各自段落，不能只塞进被排除的段落**。候选被采纳时移入目标、决定或验收，必要时递增 goal_revision。写在其他段落里的“候选”字样不会被自动排除，其余正文变化仍使证据保守失效。phase/status 是流程标签，不能用改成 done 代替验证。

脚本忽略常见缓存、生成证据和敏感文件名，并拒绝越界路径；这不是通用秘密检测器。`cost: local` 是配置声明，**不是网络沙箱**：argv 中的任意程序仍可能访问网络或写文件。执行前检查命令，只有符合当前授权的本地检查才用 verify。日志不自动脱敏；不要把敏感输出送入它。

指纹不覆盖未声明的依赖、系统库、时钟、外部服务和环境变量，也不证明检查足够全面。更换真实运行环境应更新 environment/计划并重新验证。脚本和证据可被编辑，不构成对抗性防篡改机制。

## Hook：先生成可审阅配置

```sh
python3 "$SKILL_ROOT/scripts/workflow_hooks.py" --host codex --root "$PROJECT_ROOT" --print-config
python3 "$SKILL_ROOT/scripts/workflow_hooks.py" --host claude --root "$PROJECT_ROOT" --print-config
```

按需加 `--state docs/PROJECT.md`。输出只是配置片段，**不会安装或启用**。保留宿主原有 hooks，仅合并用户选择的部分，推荐先在单一试用项目启用：

`--root` 与验证 CLI 选择同一个项目根：状态路径、inputs 和证据都相对它解释。生成时将根固化为绝对路径，相对路径按命令进程当前目录解析。子项目必须显式指定自己的根，否则兼容旧配置，按事件 cwd 寻找 Git 顶层。显式根不存在或不是目录时报错；根存在但缺少记录时不回退到父项目。固定根的配置只用于对应项目，不作为全局通用配置。

启用前先用 `brief` 确认当前记录已经接入且内容正确。只有普通 Markdown、尚无上述 frontmatter 的记录仍能人工接手，但默认 SessionStart/Stop 不会识别它；应就地接入并保留原文，或明确继续采用人工记录。不能只放入配置就告诉用户“自动记忆已经生效”。

- Codex：使用当前版本支持的项目 `.codex/hooks.json`/活动配置层；按 `/hooks` 审阅并信任确切定义，改变定义后重新信任。禁止用绕过信任的选项。
- Claude Code：合并到项目 `.claude/settings.json` 的 hooks；通过 `/hooks` 检查，按该版本要求重新载入会话。
- 配置使用生成时 Python、脚本及显式项目根的绝对路径，换机器、移动技能或项目后需要重新生成。

行为：

- **SessionStart**：发现接入的当前记录时注入简短上下文。仍需读取本技能和本轮相关代码；没有接入的项目不创建文件。
- **Stop**：explore/shape/recover 或 needs-user/blocked/paused 不要求续跑。实施阶段且已配置检查时，缺少/失败/过期证据最多要求续跑一次；`stop_hook_active` 后仅报告缺口。无自动检查时提示如实报告人工检查。不会自动运行测试或阻止用户主动中断。
- **可选 PreToolUse**：仅为明确选定的精确工具名，用重复的 `--protect-tool TOOL_NAME` 生成 matcher。对这些调用，未接入记录、读取失败或证据不满足时返回 deny；通过时返回空对象，让宿主继续正常权限流程。不要泛配所有 shell 调用，否则可能把修复/验证本身锁死。

未指定保护工具时不生成 PreToolUse。它只覆盖匹配的宿主工具入口，不能保证其他工具、脚本内部调用、发布/付费请求都被拦住。项目配置和数据都可被 agent 修改；真正权限、预算与不可绕过约束由宿主或外部受控系统承担。

跨宿主只共享记录与检查逻辑，实际载入、信任、超时/错误处理仍由各宿主决定。协议模拟测试不等于真实会话集成成功；启用后应单独验证一次开始注入、结束提醒与不循环，再声称已生效。

官方协议参考（使用新版本宿主时先核实变化）：[Codex hooks](https://learn.chatgpt.com/docs/hooks)、[Claude Code hooks](https://code.claude.com/docs/en/hooks)。
