---
name: dev_co
description: Coordinate sustained software/system development, product scoping, complex repairs, and handoffs with current memory and proportionate verification. Use for building evaluation systems; exclude standalone evaluations, benchmarks, analysis, one-off scripts, and small isolated edits unless explicitly requested.
---

# dev_co

用于软件/系统产品规划、持续功能开发、复杂修复和开发交接，管理目标、节奏和当前记忆。首次使用和重要阶段切换时，用一句自然的话说明正在使用 dev_co、本轮结果和验证范围；普通回复不重复标签。

按本轮任务意图判断适用性。独立跑评测/benchmark/模型对比、结果分析、调研报告、代码问答、单次审查、一次性脚本及孤立的小修默认不进入；位于软件仓库、有当前记录、运行代码或过去用过本技能，都不足以触发。开发/改造评测系统属于适用范围，当前开发增量的测试继续沿用。尊重明确选用、退出或其他主流程；若误加载后发现不适用，直接处理当前任务，不启动开发流程或新增项目记录。

## 核心约定

1. **先对齐当前意图。** 沿用已接受的目标、接口、授权和验收；明确改向只替换受影响的决定，含糊点子先记候选。讨论保持只读。先查可发现的信息，未核实事实明确标为假设；只问会实质改变结果、成本、权限或难以撤销选择的未知。
2. **交付连贯的小结果。** 明确本轮可观察成果和边界，复杂任务给短计划，小改直接推进。高成本或批量操作先验证代表性样本，守住约定上限；连续尝试没有新证据就换诊断假设。完成已授权阶段，新增优化保留为候选。
3. **验证匹配影响。** 从最小有意义检查开始，完成项目要求和有依据的扩大检查；不默认全量 E2E、不造假测试、不用覆盖率代替正确性。超时、截断、mock 或旧证据不能冒充当前真实通过；报告版本、环境、覆盖范围与缺口。
4. **保留一份当前记录。** 复用项目已有记录；持续开发或交接确有需要且缺少时才建 `docs/CURRENT.md`，一次性小改不强制建文档。在目标变化、重要决定、验证、阻塞和交接时更新目标、有效/候选/已替代决定、代码导航、证据和下一步。历史留链接，个人偏好与临时指令分开。
5. **守住完成与授权边界。** 个人项目以约定结果、适用验证和必要记忆更新完成，PR 可选。提交、推送、发布、付费、凭据与外部操作遵守当前授权和宿主规则，历史记录不授予新权限。本技能不改变指令优先级。

## 只展开当前需要的内容

先读项目入口和已有当前记录，核对相关工作树状态，沿导航查看本轮代码与证据；索引缺失或过期才扩大搜索。上下文仍在时复用已读内容；仅在文件变化、内容缺失或上下文丢失时重读。

**在适用开发任务内，目标与边界已明确的局部改动或讨论，可以只用核心约定。** 其余按下表中匹配的当前问题读取入口；新项目用途或第一版范围未清时，先读 `new-project.md` 的问题定义，不因“只讨论”跳过。表格不是顺序清单：只读当前步骤所需文件或章节，不批量读取 `references/`，不因文中有链接就递归展开。进入下一阶段或证据暴露新问题时再补读。

| 当前需要解决的问题 | 按需入口 |
| --- | --- |
| 新项目或重大改向：用途、第一版范围仍不清 | [new-project.md](references/new-project.md) |
| 外部事实、数据源、需求或替代方案缺少证据 | [research-and-positioning.md](references/research-and-positioning.md) |
| 产品形态、数据边界、关键架构取舍未定 | [architecture-and-risk.md](references/architecture-and-risk.md) |
| 交互流程或技术可行性需要代表性试验 | [prototyping.md](references/prototyping.md) |
| 接手、需求漂移、记忆冲突或记录结构需整理 | [memory-and-handoff.md](references/memory-and-handoff.md) |
| 测试范围难判断、证据失效或反复失败 | [verification-and-recovery.md](references/verification-and-recovery.md) |
| 第一版实施、阶段交付或安装发布检查 | [delivery-and-release.md](references/delivery-and-release.md) |
| 实际使用 `init/brief/verify/gate` 或配置 Hook | [helpers-and-hooks.md](references/helpers-and-hooks.md) |

较长参考资料先看开头的用途与章节导航，再读取所需章节及其适用约束；任务确实跨多个问题时可读多份。已有有效证据可以满足相应阶段，不重做原型或重启立项；系统、CLI 和数据管道使用契约、输入输出、性能或恢复试验，不强加界面流程。

专项技能只在当前环节需要时加载，沿用现行要求与证据，不重启一套审批或完整开发流程。TDD 等方法按需使用。`lfg`、`review`、`qa` 仅在用户明确选用时加载；不通过其他技能绕过，也不将普通开发、检查、测试解释为选用它们。

## 共用与辅助工具

Codex 与 Claude Code 共用本技能和项目当前记录，各自使用原生工具与权限；全局入口按上述任务范围选择是否加载，不需要用户每轮点名。换环境时确认技能与入口存在，加载约定不构成绝对执行保证。

辅助脚本按需执行，只读取所需输出；修改或排错时才读源码。`brief` 提供有界摘要，`verify/gate` 只覆盖声明的检查与输入，不证明测试充分、已部署或用户验收。Hook 可选，须经用户选择后按宿主要求配置并验证，不随技能安装自动启用；无工具时如实采用人工记录与核对。
