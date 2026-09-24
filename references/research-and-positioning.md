# Research and Positioning

**按需读取：** 外部事实、数据可得性、需求或替代方案的未知会改变当前决定时使用。产出能支持下一步的证据与缺口；已有证据足够时停止，不把调研当固定阶段。

章节导航：查事实 → `Start with prior work`、`Source hierarchy`、`Evidence ledger`；辨需求 → `Evidence appropriate to project intent`、`User-need and demand research`；比较外部采用/市场 → `Landscape analysis`；设计验证与收束 → `Online-first validation`、`Research stop condition`。按问题读取相关章节。

适用边界：区分事实、推断与假设，保留来源日期和反例。个人项目不强加市场验证；公开资料能回答时不用登录浏览器。桌面研究不代表真实用户验证。

## Start with prior work

Search for recent research, practitioner reports, standards, public datasets, incumbent documentation, issue discussions, and failed attempts before reasoning from scratch. Prefer sources from the last 24 months in fast-moving areas such as AI, developer tooling, platforms, pricing, and regulation.

Use older work when it is foundational or when comparing how conditions changed. Record publication date and distinguish the date of the underlying data from the date of the article.

## Source hierarchy

Prefer, in order:

1. primary research with disclosed sample and method;
2. official standards, product documentation, pricing, filings, and platform policies;
3. public datasets, repositories, changelogs, and issue trackers;
4. credible analyst or practitioner synthesis;
5. vendor claims and anecdotes, clearly labelled;
6. search snippets only as discovery pointers, never final evidence.

Use direct search or public endpoints by default. Do not open a personal browser merely to run ordinary searches. Browser automation is appropriate for authenticated, highly dynamic, or visual pages that cannot be inspected another way.

## Evidence ledger

For every load-bearing claim, capture:

- claim;
- source and date;
- underlying sample or method when available;
- what it actually supports;
- limitations or incentives;
- confidence: high, medium, or low;
- whether another source conflicts with it.

Do not average away conflicts. Explain whether sources studied different users, stages, regions, channels, or definitions.

## Evidence appropriate to project intent

Do not force startup evidence onto every project:

- For a commercial product, look for consequential behavior, payment, budget, urgency, and switching.
- For an internal tool, look for workflow cost, sponsor commitment, adoption constraints, and organizational consequences.
- For open source, look for repeated use, ecosystem gaps, maintainership, contribution behavior, and integration demand.
- For a personal, learning, or creative project, direct self-use, learning progress, or delight can be sufficient. Research the market only if distribution or commercialization is part of the goal.

## User-need and demand research

Look for behavior rather than interest:

- money already spent when the project is commercial;
- employees or agencies hired;
- spreadsheets, scripts, and workarounds maintained;
- delays, errors, lost revenue, compliance exposure, or career consequences;
- repeated requests, expansion, or urgency;
- what happens when the current solution fails.

For commercial projects, market size does not substitute for a reachable first customer. Identify the user, buyer, budget owner, purchase trigger, sales motion, and current alternative. For other intents, replace those tests with the relevant adopter, sponsor, maintainer, or personal-success evidence above.

## Landscape analysis

Use this analysis when external adoption, distribution, or commercialization matters. Skip it for a personal or learning project whose success does not depend on a market.

Map four different questions instead of treating “competition” as one number:

1. **Feature saturation** — how many products offer similar functions?
2. **Customer penetration** — how many target customers actually use or pay for them?
3. **Control and capture** — who owns the data, discovery channel, workflow, and transaction?
4. **Adjacent substitution** — can a platform, vertical suite, agency, spreadsheet, open-source tool, or internal team solve enough of the problem?

For important alternatives, compare the intended user, outcome, workflow, distribution, evidence of adoption, switching cost, and gaps. Add pricing and purchasing behavior for commercial products. Do not dismiss an idea because somebody built it; do not infer demand merely because alternatives exist.

## Online-first validation

Before building a substantial production system, prefer tests appropriate to the project intent, such as:

- a small workflow or technical spike using representative data;
- realistic query, task, or fixture sets;
- an internal shadow trial for an internal tool;
- an RFC, sample integration, or maintainer test for open source;
- concierge delivery, a concrete landing-page offer, or paid design partners for a commercial product;
- remote observation of real users completing the job;
- holdouts or before/after comparisons;
- repeated tests across channels rather than one favorable output.

Surveys and waitlists are weak unless paired with consequential behavior.

## Research stop condition

Stop desk research when the largest uncertainty requires private data, real workflow observation, consequential adoption, payment for a commercial product, integration access, or longitudinal behavior. Convert it into a field test with a threshold.

The research output should state, when applicable:

- supported facts;
- best current interpretation;
- unresolved hypotheses;
- recommended smallest coherent scope;
- strongest counterargument;
- next test and, when meaningful, its stop or change threshold.
