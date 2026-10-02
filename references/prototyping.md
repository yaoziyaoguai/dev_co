# Prototypes and Focused Trials

**按需读取：** 交互、产品形态或技术可行性的未知会影响当前决定时，才单独做原型；采用行为按需选择观察或小试验。产出回答当前问题的证据和决定，已有合适证据先复用。

章节导航：产品形态或交互未知 → `Product-shape evidence`；选载体 → `Select by uncertainty`；所有试验 → `Prototype contract`、`Exit`；具体执行只读选中的 `Figma and FigJam`、`Disposable interactive prototype`、`Technical spike` 或 `Observation`。

适用边界：讨论不授权创建外部设计或启动实施。mock 不证明真实集成，静态界面不证明交互；系统/CLI 按所需证据选技术试验。只可直接删除本任务在隔离临时目录创建的可抛弃产物，其余保留/归档或按授权处理；复用原型代码须按生产代码重新审视。

## Product-shape evidence

Create a separate prototype only when an unresolved interaction, product-form, or feasibility question could change the current decision. For a simple, settled workflow, the first real implementation slice may supply the evidence; no disposable copy is required.

Use the cheapest representative surface that answers the question. Walk the smallest coherent core journey, covering only the empty, loading, partial, error, recovery, and success states that could change the decision. A complete design system or every screen is not required.

A static screen or diagram cannot prove interaction; use a runnable task when behavior is the unknown. Mock data must expose realistic labels, content density, relationships, and awkward cases. Inspect and reuse an existing suitable design or demo instead of recreating it.

## Select by uncertainty

| Uncertainty | Best first artifact | What it cannot prove |
|---|---|---|
| Service blueprint, ownership, or sequence | FigJam or flow diagram | Visual usability or technical feasibility |
| Information hierarchy, layout, and product form | Figma screens at the lowest sufficient fidelity | Real behavior, performance, or integration |
| Interaction, state transitions, and task completion | Disposable interactive prototype on a representative surface | Production architecture |
| Native APIs, media, model quality, synchronization, or performance | Focused technical spike | Whether users value the workflow |
| Adoption or demand | Concierge/manual test; include a paid offer only for a commercial hypothesis | Product scalability |

Split trials only when one artifact cannot answer the distinct questions. A polished mockup can conceal an impossible technical core; a successful technical demo can conceal an unwanted product.

## Prototype contract

For a quick design exploration, record only the question, hypothesis, realistic scenario, and decision. For a formal user or technical validation, also record:

- question being tested;
- current hypothesis;
- target participant or environment;
- realistic scenario and representative mock data;
- behavior or measurement to observe;
- pass, fail, and inconclusive thresholds;
- maximum time or scope;
- what will be retained, archived, reused, or proposed for deletion afterward.

Keep this proportional. If the core question cannot be stated, the prototype is probably premature.

## Figma and FigJam

When visual hierarchy or product form is materially uncertain and editable screens are the cheapest useful test, use the lowest sufficient fidelity in Figma:

1. FigJam is useful primarily for flows, systems, or collaborative mapping.
2. Start with flows, wireframes, or simple components. Increase fidelity only when visual trust, content density, brand expression, or platform conventions are part of the decision.
3. Inspect an existing design system before creating new primitives.
4. Cover the core journey and only the states needed to resolve the named uncertainty.
5. Validate the screens and navigation. A visually attractive static screen without a testable task does not prove interaction; use a runnable demo when behavior or state is at issue.
6. Use design-to-code or Code Connect when the relevant design decisions are settled and implementation is within current authorization.

Do not claim that Figma proves runtime behavior, complex gestures or shortcuts, accessibility behavior, integration reliability, model latency, or native performance.

When Figma is selected and the capability is available, create or update an actual editable Figma artifact; a prose-only screen description does not satisfy that visual test.

## Disposable interactive prototype

Use a disposable interactive prototype when a material interaction question needs runnable evidence before implementation. Choose a representative surface, often a browser; native interaction may require a native shell or focused spike. Keep it intentionally disposable:

- mock data and in-memory state by default;
- no production authentication, database, billing, or generalized architecture;
- one command or URL to run;
- only the core journey and states needed for the question;
- representative mock records, realistic labels, and realistic content density rather than lorem ipsum;
- visible prototype marker;
- after the decision, record what is retained, archived, or intentionally reused without letting it silently become production architecture.

Run the demo and verify the core journey. Source code or screenshots without a successful representative task do not prove interaction.

The agent may delete without further authorization only disposable artifacts it created inside an isolated temporary directory. Mark or archive every other prototype by default; deleting a user-provided, pre-existing, or project-stored prototype requires explicit authorization.

Reusing prototype code is a production-code decision, not a shortcut. Review every retained part against the accepted architecture, remove mock-only assumptions and dependencies, and add the relevant production tests. Otherwise carry forward only the validated product decisions, fixtures, and visual assets.

## Technical spike

Isolate one feasibility risk. Examples include model-output quality, runtime performance, synchronization, platform permissions, API rate limits, and offline operation.

Use representative data and measure the result. Avoid wrapping the spike in a full application. Record environment, input, output, failure cases, and whether the result generalizes.

## Observation

Prefer watching a participant attempt a realistic task without coaching. Record:

- where they hesitate;
- what they misunderstand;
- what they ignore;
- what they try that the prototype does not support;
- what result they expect;
- whether they would take a consequential next step.

Compliments do not validate a hypothesis. Task completion, changed behavior, data access, sustained adoption, a concrete commitment, or payment when commercial intent is being tested is stronger evidence.

## Exit

End with one of:

- hypothesis supported; carry the decision into the product record;
- hypothesis rejected; change or stop;
- inconclusive; name the missing evidence and design a smaller follow-up;
- technical feasibility proven but demand unproven;
- product workflow validated but technical feasibility unproven.

Record whether the prototype will be retained, archived, reused, or proposed for deletion. Preserve the answer, not the accidental scaffolding, and follow the deletion boundary above.
