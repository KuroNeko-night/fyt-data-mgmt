# 先把项目中的几个上千行的超长文件进行拆分和迁移 Update: 先把项目中的几个上千行的超长文件进行拆分和迁移 Update: 先把项目中的几个上千行的超长文件...

## Execution Summary
Governed runtime execution plan for `vibe` in mode interactive_governed.

## Skill Search Guide
- 先拆任务，再拆模块
- 会按模块搜索本地 skills
- 每个模块单独搜索本地 skills
- 会先看候选 skill 名和短描述，再打开并阅读候选 `SKILL.md`
- 每个模块最多保留 3 个候选，避免上下文污染
- 以候选 `SKILL.md` 的真实用途为准，不按词面碰撞判断
- 会给出 `L` / `XL` 两套 skills 组织方案，并说明每个 skill 的职责
- 优先选择真正负责该模块的 owner，不选只沾边的 helper
- 一个 skill 可以覆盖多个模块
- explicit_only skills 只有在用户明确点名时才可入选
- 不得跨越候选 skill 声明的负边界或适用限制
- 没有 owner 时必须报缺口，不得伪装覆盖
- 没有 owner 的模块会明确标出缺口
- requirement 阶段公开搜索办法，并在请用户选择前由 Agent 分别给出 L / XL 的具体工作流和候选 skill 名称；这些名称必须标为尚未正式选定或使用，不得公开程序候选排名或预选结果
- xl_plan 阶段公开模块、候选、最终采用和缺口
- execute 阶段公开本次实际启用的 skills

## Task Modules
- `core-python-split`: 拆分 core/ 下超过千行的 reconcile_core.py、tauri_bridge.py、purchase_core.py，保持公开入口与导入兼容，业务算法仍只在 core/。
- `web-server-migration`: 将 web_server.py 中仍可下沉的依赖装配与协议逻辑迁移到 web_backend/，web_server.py 只保留兼容启动入口。
- `gui-split`: 拆分 web_control_gui.py 中可独立测试的非 Tk 辅助逻辑，保留 Tkinter 入口稳定，不引入第三方 GUI 依赖。
- `frontend-api-split`: 将 web-app/src/api.ts 按业务域拆分为 web-app/src/api/ 下模块，更新全部导入并保持 Web 构建通过。
- `regression-and-docs`: 执行全量回归并同步 docs/项目全景-模块与实现.md 中关于本次拆分和迁移的模块说明。

## Candidate Skills By Module
- `core-python-split`: none found
- `web-server-migration`: none found
- `gui-split`: none found
- `frontend-api-split`: none found
- `regression-and-docs`: none found

## Uncovered Modules
- No module is blocked by a Skill gap; `core-python-split`, `web-server-migration`, `gui-split`, `frontend-api-split`, `regression-and-docs` is explicitly assigned to the current Agent without a local Skill.

## L / XL Organization Difference
- L: 先冻结需求和计划，再由一个主流程按模块顺序串行推进：core 拆分 → web_server 迁移 → GUI 拆分 → api.ts 拆分 → 回归与文档收口。
- XL: 如需分波次：core 拆分与 api.ts 拆分可在不同写范围内并行；web_server 与 GUI 拆分需在 core 稳定后串行；最终统一回归与文档收口。
- Selected workflow level: `L`

## Frozen Inputs
- Requirement doc: C:\Users\mai\Desktop\fyt-data-mgs\docs\requirements\2026-08-15-update-update.md
- Source task: 先把项目中的几个上千行的超长文件进行拆分和迁移 Update: 先把项目中的几个上千行的超长文件进行拆分和迁移 Update: 先把项目中的几个上千行的超长文件进行拆分和迁移

## Wave Plan
- Wave 1 (`sequential`): `core-python-split` via current Agent as `owner`
- Wave 2 (`sequential`): `frontend-api-split` via current Agent as `owner`
- Wave 3 (`sequential`): `web-server-migration` via current Agent as `owner`
- Wave 4 (`sequential`): `gui-split` via current Agent as `owner`
- Wave 5 (`sequential`): `regression-and-docs` via current Agent as `owner`

## Delivery Acceptance Plan
- Freeze downstream product acceptance inside the governed requirement doc and reuse it rather than inventing closeout claims later.
- Emit a per-run delivery-acceptance report during `phase_cleanup` so runtime/process success is kept separate from project-delivery success.
- Delivery-acceptance report: C:\Users\mai\Desktop\fyt-data-mgs\outputs\runtime\vibe-sessions\20260815T070049Z-e4912340\delivery-acceptance-report.json
- If manual spot checks are declared in the requirement doc, final completion wording stays blocked until they are cleared or explicitly downgraded to manual review.
- Release truth aggregation remains an outer-layer gate; this run emits the per-run delivery-truth report only.

## Module Work Plan
- `core-python-split`: 拆分 core/ 下超过千行的 reconcile_core.py、tauri_bridge.py、purchase_core.py，保持公开入口与导入兼容，业务算法仍只在 core/。
  Required: `True`; dependencies: none; Execution mode: `agent_direct`
  Work: current Agent as `owner` - 拆分 core/ 下超过千行的 reconcile_core.py、tauri_bridge.py、purchase_core.py，保持公开入口与导入兼容，业务算法仍只在 core/。
  Acceptance: `core-split-compiles` (automated) - 拆分后的 core 模块通过 py_compile，且原有导入入口可正常 import。
  Acceptance: `core-tests-pass` (automated) - 全量 Python 回归通过，没有因拆分引入的新失败。
- `web-server-migration`: 将 web_server.py 中仍可下沉的依赖装配与协议逻辑迁移到 web_backend/，web_server.py 只保留兼容启动入口。
  Required: `True`; dependencies: `core-python-split`; Execution mode: `agent_direct`
  Work: current Agent as `owner` - 将 web_server.py 中仍可下沉的依赖装配与协议逻辑迁移到 web_backend/，web_server.py 只保留兼容启动入口。
  Acceptance: `web-server-compiles` (automated) - web_server.py 与 web_backend 通过 py_compile。
  Acceptance: `web-tests-pass` (automated) - 全量 Python 回归通过，Web API 行为不因迁移改变。
- `gui-split`: 拆分 web_control_gui.py 中可独立测试的非 Tk 辅助逻辑，保留 Tkinter 入口稳定，不引入第三方 GUI 依赖。
  Required: `True`; dependencies: `web-server-migration`; Execution mode: `agent_direct`
  Work: current Agent as `owner` - 拆分 web_control_gui.py 中可独立测试的非 Tk 辅助逻辑，保留 Tkinter 入口稳定，不引入第三方 GUI 依赖。
  Acceptance: `gui-compiles` (automated) - web_control_gui.py 及其新辅助模块通过 py_compile。
  Acceptance: `gui-tests-pass` (automated) - tests.test_web_control_gui 全部通过。
- `frontend-api-split`: 将 web-app/src/api.ts 按业务域拆分为 web-app/src/api/ 下模块，更新全部导入并保持 Web 构建通过。
  Required: `True`; dependencies: none; Execution mode: `agent_direct`
  Work: current Agent as `owner` - 将 web-app/src/api.ts 按业务域拆分为 web-app/src/api/ 下模块，更新全部导入并保持 Web 构建通过。
  Acceptance: `api-build-pass` (automated) - npm --prefix web-app run build 通过，前端行为不退化。
- `regression-and-docs`: 执行全量回归并同步 docs/项目全景-模块与实现.md 中关于本次拆分和迁移的模块说明。
  Required: `True`; dependencies: `core-python-split`, `web-server-migration`, `gui-split`, `frontend-api-split`; Execution mode: `agent_direct`
  Work: current Agent as `owner` - 执行全量回归并同步 docs/项目全景-模块与实现.md 中关于本次拆分和迁移的模块说明。
  Acceptance: `full-regression-pass` (automated) - 仓库卫生检查、全量 Python 回归、双端前端构建和 Rust 测试全部通过。
  Acceptance: `docs-synced` (automated) - docs/项目全景-模块与实现.md 已同步本次拆分和迁移后的模块事实。

## Verification Commands
- Run every verification command frozen for the module work units and retain its real result.
- Reconcile every module acceptance criterion against the returned execution evidence.
- Review the delivery-acceptance report emitted during `phase_cleanup` before using full completion language.

## Rollback Plan
- If verification fails, revert only changes inside the approved module write scopes.
- Do not roll back unrelated user changes.

## Phase Cleanup Contract
- Remove temporary artifacts created by the approved module work only.
- Write cleanup receipt before completion.
