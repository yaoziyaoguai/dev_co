# Product Form, Architecture, and Risk

**按需读取：** 当前需要选择产品形态、数据边界或关键架构时使用；成熟模块的局部修改不重新选型。输出有依据的推荐、影响与重议条件，写回已有决定记录。

章节导航：产品形态 → `Product form before feature list`；领域与数据 → `Domain and data model`；结构/选型 → `Architecture decisions`；失败情形 → `Red-team questions`；留依据 → `Decision record`。只展开本轮取舍相关章节。

适用边界：按实际约束比较，原型证据改变前提时复核，避免假想规模。用用户可判断的效果、成本和维护代价解释选择；不把陌生技术菜单交还用户，不重复已接受的取舍。

## Product form before feature list

Define:

- the user who performs the workflow;
- the buyer and budget owner for commercial work, sponsor for internal work, or adopter and maintainer for open source when relevant;
- the trigger that starts the workflow;
- the result they receive;
- time to first value;
- the minimum trust evidence they require;
- whether delivery is a library, CLI, application, service, API, report, managed workflow, marketplace, or a hybrid;
- why the work repeats often enough when the intended model depends on recurring use or revenue.

Treat acquisition, distribution, and business model as project decisions. Test whether the proposed channel reaches the intended user and supports the intended outcome.

Map the relevant user journey, including entry, setup, first value, recurring use, failure recovery, export, and data deletion where applicable. Add upgrade and cancellation only when the product model includes them. Do not design only the happy path.

For multi-role B2B workflows, when applicable, map each actor's authority, data ownership, and handoff to the next actor. Do not introduce enterprise role machinery when the workflow does not require it.

## Domain and data model

Identify the few domain objects whose meaning must remain stable. For each, define ownership, lifecycle, identity, source of truth, sensitive fields, and relationships.

Trace data from origin to user-visible result:

- acquisition and authorization;
- normalization and validation;
- storage and retention;
- model or business-rule processing;
- provenance and confidence;
- correction and deletion;
- export and downstream synchronization.

When model-generated, probabilistic, or changing external-source outputs influence business decisions, expose provenance, uncertainty, and last-updated time rather than hiding them behind a single score.

## Architecture decisions

Derive candidate architecture from the current product workflow and actual constraints, then finalize it after reviewing the applicable prototype or spike evidence. Compare only constraints that could change the decision:

- target platform;
- credible data volume and concurrency;
- latency, reliability, and offline requirements;
- privacy and data-residency boundaries;
- acceptable fixed and per-operation cost;
- the team's operational capacity.

Use ranges where exact values are unavailable. Mark consequential unknowns explicitly and resolve them with the smallest useful spike instead of inventing scale or expanding into a generic non-functional-requirements checklist.

Evaluate the applicable structural choices, including build versus buy, information-hiding boundaries, local versus cloud execution, synchronous versus asynchronous work, batch versus real-time processing, single versus multi-tenant operation, external-service volatility and rate limits, critical vendor exit, retries, idempotency, partial failure, recovery, observability, migration, updates, and rollback.

Then choose, as applicable, the runtime, framework, storage, authentication and authorization approach, model or provider, and deployment shape that fit those constraints. Prefer mature, well-understood technology that shortens the path to a reliable release unless a real requirement disqualifies it. Record why the chosen stack wins, its important lock-in or replacement cost, and what evidence would reopen the decision.

Do not hand an unfamiliar technology menu to the user. Explain choices through user-visible behavior, delivery time, cost, operational burden, risk, and reversibility; recommend one option and ask the user only about priorities or constraints they uniquely control.

When multiple architecture shapes are meaningfully distinct, compare:

1. **Smallest coherent release** — fewest moving parts that proves the value.
2. **Recommended architecture** — protects the real boundaries of the agreed first-release scope.
3. **Alternative** — buy, integrate, managed service, local-first, batch instead of real-time, or another materially different model.

Walk the critical path from the user's trigger to the promised result. At each hop, identify the responsible component, input and output, source of truth, trust boundary, credible failure, recovery behavior, and material cost. Use this walkthrough to expose missing boundaries and operational work before implementation.

Do not build for imagined scale. Do avoid irreversible coupling to an unstable platform when a narrow adapter or stored source data protects the project.

## Red-team questions

Apply only questions that fit the project's intent.

Common questions:

- Can an upstream platform block access or invalidate the workflow?
- Does data heterogeneity turn software into manual operations?
- Does the product require data that cannot be obtained or that users will not provide?
- Can users verify the output, correct it, and recover from errors?
- What fails when the model, API, or upstream schema changes?
- Which assumption, if false, kills the architecture rather than one feature?

For commercial projects, also ask:

- Is the problem frequent and costly enough to fund the solution?
- Does the named buyer control a budget?
- Does the proposed metric connect to a business outcome or only vanity?
- Does pricing and distribution fit how the buyer purchases?

For subscription models, test recurring value and retention. For paid acquisition, test acquisition cost against lifetime value. For service-to-software projects, test whether the human work can actually be standardized. For platform-dependent projects, test access rights and platform control.

For internal or open-source projects, replace commercial questions with sponsor durability, adoption friction, maintainership, governance, contribution cost, and ecosystem compatibility as relevant.

Turn each credible failure into a mitigation, test, explicit acceptance, or scope reduction. Do not hide unresolved risk in “future work.”

## Decision record

For each load-bearing architecture choice, record:

- context and constraint;
- options considered;
- decision and rationale;
- consequences and tradeoffs;
- evidence that would trigger reconsideration.

Use a small ADR or the project decision record. Avoid architecture documents that only describe boxes without explaining why the boundaries exist.
