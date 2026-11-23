---
name: dev_co
description: Route sustained software development, product scoping, complex repairs, and handoffs. Select specialist workflows and retain current project context. Exclude standalone analysis, benchmarks, one-off scripts, and isolated edits. 用于继续开发、规划第一版、复杂修复和跨会话交接。
---

# dev_co

用于软件/系统产品规划、持续功能开发、复杂修复和开发交接，管理目标、节奏和当前记忆。首次使用和重要阶段切换时，自然说明本轮结果与验证范围，例如“我会用 dev_co 继续订单筛选，交付可用的筛选流程并验证空结果和清除筛选。”

按本轮任务意图判断适用性。独立跑评测/benchmark/模型对比、结果分析、调研报告、代码问答、单次审查、一次性脚本及孤立的小修默认不进入；位于软件仓库、有当前记录、运行代码或过去用过本技能，都不足以触发。开发/改造评测系统属于适用范围，当前开发增量的测试继续沿用。尊重明确选用、退出或其他主流程；若误加载后发现不适用，直接处理当前任务，不启动开发流程或新增项目记录。

独立的增量反防御清理直接使用可用的 `de-slop`，入口缺失时按当前差异处理。此类任务沿用现有项目记录与权限，无需启动开发流程。

用户明确接续已有开发目标的规划、UI、审查或验收阶段时，由本入口衔接当前阶段，再选专项能力，并遵守本轮只读范围。

## 核心约定

1. **先对齐当前意图。** 沿用已接受的目标、接口、授权和验收；明确改向只替换受影响的决定，含糊点子先记候选。结合项目的使用者、核心对象、主要任务与当前阶段，决定本轮先做什么及如何验收。讨论保持只读。先查可发现的信息，未核实事实明确标为假设；只问会实质改变结果、成本、权限或难以撤销选择的未知。
2. **交付连贯的小结果。** 明确本轮可观察成果和边界，复杂任务给短计划，小改直接推进。高成本或批量操作先验证代表性样本，守住约定上限；连续尝试没有新证据就换诊断假设。完成已授权阶段，新增优化保留为候选。
3. **验证匹配影响。** 先确认关键上下文和可观察反馈足以判断本轮结果；缺少时先补最小复现、样本或基线。预期来自已确认要求或独立证据，不迁就实现。从最小有意义检查开始，完成项目要求和有依据的扩大检查，不默认全量 E2E 或以覆盖率代替正确性。超时、截断、mock 或旧证据不能冒充当前真实通过。复杂任务核对验收、实现与证据的对应及遗漏，报告范围与缺口；达成约定结果后停止本轮迭代。
4. **保留一份当前记录。** 复用项目已有记录；持续开发或交接确有需要且缺少时才建 `docs/CURRENT.md`，一次性小改不强制建文档。在目标变化、重要决定、验证、阻塞和交接时更新目标、有效/候选/已替代决定、代码导航、证据和下一步。历史留链接，个人偏好与临时指令分开。
5. **守住完成与授权边界。** 个人项目以约定结果、适用验证和必要记忆更新完成，PR 可选。提交、推送、发布、付费、凭据与外部操作遵守当前授权和宿主规则，历史记录不授予新权限。本技能不改变指令优先级。

首次持续实施或新增目录/资料职责时，按[仓库增量维护](references/repository-lifecycle.md)确定归属与更新关系；老项目只约束本次新增与直接受影响部分，优先复用已有检查，在修改前接入基线并在增量出口核对，不追溯清理无关存量。

## 只展开当前需要的内容

先读项目入口、当前摘要与本轮全局约束，核对相关工作树状态，再展开当前任务及其依赖。沿文件/符号导航定位后读取必要上下文；索引缺失、过期或影响跨模块时扩大范围。上下文仍在时复用已读内容；文件变化、内容缺失或验证需要时再读相关部分。需要完整原文才能判断时应补读，不靠猜测节省 token。

编制或接手多任务执行包时，按[执行包与阅读约定](references/memory-and-handoff.md#执行包与阅读约定)提供并遵循按任务展开的入口，不默认先读全部方案、源码和历史证据。连续执行不要求同时加载所有任务细节；阶段出口留下可恢复状态，沿宿主原生上下文机制继续，不增加人工审批点。

**在适用开发任务内，目标与边界已明确的局部改动或讨论，可以只用核心约定。** 其余按下表中匹配的当前问题读取入口；新项目用途或第一版范围未清时，先读 `new-project.md` 的问题定义，不因“只讨论”跳过。表格不是顺序清单：只读当前步骤所需文件或章节，不批量读取 `references/`，不因文中有链接就递归展开。进入下一阶段或证据暴露新问题时再补读。

| 当前需要解决的问题 | 按需入口 |
| --- | --- |
| 项目背景已知，但设计、实施或验收仍缺少与具体任务相连的取舍依据 | [project-fit.md](references/project-fit.md) |
| 新项目或重大改向：用途、第一版范围仍不清 | [new-project.md](references/new-project.md) |
| 外部事实、数据源、需求或替代方案缺少证据 | [research-and-positioning.md](references/research-and-positioning.md) |
| 产品形态、数据边界、关键架构取舍未定 | [architecture-and-risk.md](references/architecture-and-risk.md) |
| 跨模块功能需要规格追踪，或项目已有 Spec Kit 产物需要继续 | [specification-workflows.md](references/specification-workflows.md) |
| 交互流程或技术可行性需要代表性试验 | [prototyping.md](references/prototyping.md) |
| 设计或明显调整界面的信息层级、操作主次、布局密度、组件状态或响应式行为 | [ui-design.md](references/ui-design.md) |
| 编制执行包、接手、需求漂移、记忆冲突或记录结构需整理 | [memory-and-handoff.md](references/memory-and-handoff.md) |
| 测试范围难判断、证据失效或反复失败 | [verification-and-recovery.md](references/verification-and-recovery.md) |
| 实质逻辑改动完成后，最终验证前收敛过度防御和静默兜底 | [增量反防御清理](references/specialist-skills.md#增量反防御清理) |
| 第一版实施、阶段交付或安装发布检查 | [delivery-and-release.md](references/delivery-and-release.md) |
| 首次持续实施，或目录归属、资料更新与迁移需要约束 | [repository-lifecycle.md](references/repository-lifecycle.md) |
| 当前开发环节需要哪项设计、工程、测试或优化能力 | [specialist-skills.md](references/specialist-skills.md) |
| 实际使用 `init/brief/verify/gate` 或配置 Hook | [helpers-and-hooks.md](references/helpers-and-hooks.md) |

长参考资料先看开头的用途与章节导航，按需读对应章节；已有有效证据不重做原型或重启立项，非界面系统用契约、输入输出、性能或恢复试验替代界面流程。

方法选择由 agent 完成。目标、实施领域、验证阶段或证据变化时，按[专项技能导航](references/specialist-skills.md)选能力；UI 子任务用宿主可用的 `compose-ui-kit` 或[界面指南](references/ui-design.md)。实质逻辑初步跑通后，最终检查和 `verify` 前把本轮 `git diff`（含已暂存本轮改动）和本轮新增的未跟踪源码交给可用的 `de-slop`；只读核对仅报告，清理位置和保留边界并入主交付摘要。

移交具体目标、范围、已确认约束、现有产物与完成证据，读取所选技能后执行适用流程，不给裸技能菜单、不重复访谈、不自动补装。结果回原任务，同一产物保留一处权威来源；`lfg`、`review`、`qa` 等显式技能仅在用户明确选用时加载。

## 共用与辅助工具

兼容宿主共用本技能与项目当前记录，各自遵循原生工具与权限；全局入口按上述任务范围决定是否加载。换环境时分别核实文件同步、宿主发现与实际执行。

辅助脚本位于 `scripts/`，按[命令说明](references/helpers-and-hooks.md)从实际技能路径调用：`brief` 恢复当前记录，`verify --reuse` 按计划复用有效功能证据，`gate` 核对功能证据与仓库条件。Hook 默认只生成开始恢复配置，由用户启用；部署和用户验收各自取证，缺脚本时记录实际人工核对范围。
