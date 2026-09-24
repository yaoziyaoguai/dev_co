# Delivery and Release

**按需读取：** 第一版决定已明确并进入实施，或需要阶段交付、安装、发布检查时使用。已有可用版本可直接选择交付章节。

章节导航：开始第一版 → `Execute the first-release contract`、`Repository setup`；实现增量 → `Thin vertical slices`；按风险检查 → `Quality and security`；交付候选 → `Release candidate`；外部发布 → `GitHub and launch`；汇报 → `Final report`。实施时不预读不相关的发布细节。

适用边界：第一版范围与验收沿用当前记录；只补缺口。个人项目 PR 可选，提交/推送/部署依据现有授权；本地、真实服务、部署和用户验收的证据分别报告，不能由前者推定后者。

## Execute the first-release contract

Use the accepted first-release contract in the current project record. If it is missing, consult the readiness section of [new-project.md](new-project.md) to resolve the actual gap; do not reopen settled decisions. Make that complete value loop the next release candidate. Keep it proportional: recovery covers credible blocking failures rather than every theoretical edge case, and the intended result is what the user actually needs. Revise the contract when evidence changes the decision, and record the reason.

Finish this releasable loop before expanding the product surface. Do not spread implementation across multiple unfinished workflows, and do not let optional features displace release-candidate completion.

## Repository setup

Before creating or changing a repository, define the outcome, non-goals, expected files, and proof. Reuse an existing repository when it already represents the product; do not create a second repository to avoid understanding the first.

For a new repository, add only what the first release needs. Typical decisions include:

- runtime and dependency manager;
- project structure and module boundaries;
- `.gitignore` and configuration example without secrets;
- test and formatting commands;
- CI for the relevant checks;
- README with install, run, verify, and current limitations;
- license choice when distributing externally, explicitly decided rather than assumed;
- release or deployment path.

Do not publish or push until the user authorizes the exact external action.

## Thin vertical slices

Build the first end-to-end user-visible workflow before broad foundations. The slices should converge on the first-release contract rather than creating several disconnected happy paths. Each slice should cross the necessary UI, domain, and infrastructure boundaries while remaining small enough to verify.

For each slice:

1. define expected user-visible behavior;
2. write or identify the smallest meaningful check;
3. implement using existing conventions;
4. test failures and edge cases credible for that slice;
5. inspect the diff for accidental scope and dead scaffolding;
6. keep the repository in a buildable state.

Add abstraction only for a real boundary, irreversible dependency, or multiple actual callers.

## Quality and security

Apply review proportional to risk. Check:

- correctness and recovery paths;
- accessibility and responsive behavior for user interfaces;
- authentication and authorization where present;
- validation at trust boundaries;
- secret handling and dependency risk;
- privacy, retention, deletion, and logging;
- rate limits, retries, idempotency, and partial failure for external APIs;
- cost and performance for representative workloads;
- migration and rollback for persistent data;
- documentation and operator visibility.

Do not call the project ready while relevant tests fail, output is truncated, or only a demo path was checked.

## Release candidate

Create and pass the release candidate for the first-release contract before polishing or adding optional features. Verify from a clean user perspective:

- acquisition or installation;
- first-run setup;
- core task completion;
- error recovery;
- output quality and export;
- update or rollback path;
- support and feedback route;
- analytics only when justified and disclosed.

For packaged desktop or mobile applications, verify signing, permissions, packaging, and installation on a clean environment as applicable. For web services, verify deployment, environment variables, health, logs, and rollback.

## GitHub and launch

Before public release, show:

- repository visibility;
- files and history that will become public;
- license;
- release artifacts;
- documentation and known limitations;
- any telemetry or network behavior;
- deployment destination.

Check that current authorization covers the intended remote, push, publication, or deployment. Ask only when it is absent or the target or action has materially changed; do not repeat an already answered approval request. After release, verify the public artifact rather than assuming the command succeeded.

## Final report

Report:

- user-visible outcome;
- files and architecture boundaries changed;
- exact checks performed;
- release or deployment status;
- known caveats and unverified behavior;
- next evidence to collect from users.
