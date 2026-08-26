# Hướng dẫn sử dụng toàn bộ Skill và Agent của MOStudio Kit

Tài liệu này dành cho người dùng Codex App/CLI hoặc Hermes Agent muốn áp dụng
MOStudio Kit vào một dự án game đang phát triển hoặc đang vận hành. Mục tiêu là
giúp bạn biết nên yêu cầu gì, skill nào sẽ xử lý, khi nào cần agent chuyên môn,
và bằng chứng nào phải có trước khi tin một kết quả `PASS`.

Phiên bản tiếng Anh sẵn sàng để đăng lên GitHub Wiki nằm tại
[`docs/wiki-skill-agent-user-guide.md`](wiki-skill-agent-user-guide.md).

Catalog hiện tại gồm **50 canonical skill**, **24 canonical agent role** và
**7 pack**. Skill là quy trình có thể tái sử dụng. Agent là vai trò nhận một
phạm vi công việc cụ thể và sử dụng một hoặc nhiều skill để hoàn thành phạm vi
đó. Agent không thay thế skill và không tự mở rộng quyền mutation.

## 1. Bắt đầu nhanh

Bạn không cần nhớ tên tất cả skill. Hãy mô tả kết quả mong muốn, phạm vi repo,
điều không được chạm tới và mức bằng chứng cần có.

Ví dụ tối thiểu:

```text
Audit project Unity này, xác định subsystem và route sang đúng skill.
Chỉ đọc, không sửa file. Báo Verified/Snapshot/Unverified/BLOCKED rõ ràng.
```

Ví dụ đủ ngữ cảnh hơn:

```text
Repo: D:/Games/MyMMO
Mục tiêu: tìm nguyên nhân client không vào được offline gameplay.
Phạm vi được đọc: Assets/, ProjectSettings/, Logs/.
Không được chạm: .env, database, generated localization, production services.
Yêu cầu: tái hiện lỗi, xếp hạng giả thuyết, chỉ sửa sau khi đã có root cause,
chạy focused tests và trả command + exit code + artifact path.
```

Router thường bắt đầu từ `using-game-studio-skills`, sau đó chọn skill hẹp nhất.
Nếu muốn chỉ định rõ, hãy viết tên skill trong yêu cầu:

```text
Dùng unity-ui-rendering-debugging để chẩn đoán HUD bị mất.
Chỉ đọc cho đến khi root cause được chứng minh.
```

Trong Codex có thể gọi plugin bằng `@game-studio-codex-kit` nếu muốn route tường
minh. Trên bề mặt có skill picker, bạn cũng có thể chọn trực tiếp skill tương
ứng; nếu không, nhắc tên skill bằng văn bản là đủ để router hiểu ý định.

## 2. Mẫu prompt nên dùng

Mẫu tổng quát:

```text
Mục tiêu:
Repo/project:
Snapshot/branch/build:
Phạm vi được đọc:
Phạm vi được sửa:
Không được chạm:
Skill mong muốn (nếu biết):
Agent mong muốn (nếu cần):
Reviewer:
Lệnh kiểm chứng dự kiến:
Artifact cần nhận:
Điều kiện dừng/BLOCKED:
```

Mẫu yêu cầu sửa lỗi:

```text
Dùng evidence-first-debugging để xử lý <lỗi>.
Tái hiện trước, đưa ra giả thuyết có thứ tự, xác định root cause, viết regression
test rồi mới sửa tối thiểu. Không thay đổi <do-not-touch>. Kết thúc bằng
build-and-runtime-verification với command, exit code và limitation.
```

Mẫu yêu cầu review:

```text
Dùng review-swarm review diff <commit/branch/working tree> theo ba lane độc lập:
correctness, security/mutation, tests/release. Tất cả lane read-only. Mỗi finding
phải có severity, file:line, bằng chứng và counterevidence. Main thread tích hợp
verdict cuối.
```

Mẫu yêu cầu thay đổi an toàn:

```text
Lập report-only plan cho thay đổi <mục tiêu>. Liệt kê exact paths, before/after
hashes, collision, backup và restore. Không apply cho tới khi reviewer duyệt đúng
plan digest. Nếu target thay đổi sau report thì dừng và tạo plan mới.
```

## 3. Cách đọc verdict và mức rủi ro

### Nhãn bằng chứng

| Nhãn          | Ý nghĩa                                                                            | Ví dụ                                       |
| -------------- | ------------------------------------------------------------------------------------ | --------------------------------------------- |
| `Verified`   | Đã trực tiếp quan sát bằng command, test, build, primary source hoặc artifact | `dotnet test`, exit `0`, log được lưu |
| `Snapshot`   | Đúng với một commit, build, config hoặc môi trường cụ thể                  | Unity`6000.0.45f1` tại commit `abc123`   |
| `Unverified` | Giả thuyết hoặc dự báo chưa đủ bằng chứng                                  | “Có thể prefab mất reference”            |
| `BLOCKED`    | Thiếu runner, quyền, project, dependency hoặc evidence cần thiết                | Không có Unity Editor để chạy PlayMode   |

`BLOCKED` là kết quả hợp lệ. Không được đổi `BLOCKED` thành `PASS` chỉ vì code
trông đúng hoặc compile thành công.

### Mức rủi ro mutation

| Risk          | Điều kiện tối thiểu                                                      |
| ------------- | ----------------------------------------------------------------------------- |
| `read-only` | Có thể tự chạy các kiểm tra không đổi trạng thái                   |
| `low`       | Diff rõ ràng và verification command                                       |
| `medium`    | Exact scope, reviewer, backup/manifest, restore path và plan được review  |
| `high`      | Human approval rõ ràng, report/dry-run, backup/rollback và stop conditions |

Việc chọn agent chuyên gia không hạ risk. `game-data-engineer` vẫn không được tự
chạy destructive SQL; `build-release-engineer` vẫn không được tự publish; agent
read-only không được sửa source.

## 4. Toàn bộ 50 skill

### 4.1 Studio Core — định tuyến, an toàn và bằng chứng

| Skill                              | Dùng khi                                                                 | Ví dụ yêu cầu                                                                       |
| ---------------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `using-game-studio-skills`       | Bắt đầu bất kỳ task nào, cần xác định route/risk/evidence       | “Audit repo này và chọn đúng workflow; chưa được sửa.”                      |
| `studio-project-intake`          | Tiếp nhận repo lạ, gom goal, engine, scope, owner, constraint          | “Tạo task packet cho Unity client + C++ server này.”                                |
| `code-intelligence-contract`     | Thu thập evidence dependency, call-chain, blast-radius theo contract trung lập provider | “Kiểm tra blast radius, không cài hoặc refresh provider.” |
| `studio-workspace-routing`       | Workspace có nested Git roots hoặc nhiều repo liên quan               | “Route client/server/workbench theo project-profile và validation slice.”            |
| `studio-agent-orchestration`     | Có từ hai workstream độc lập và cần chia agent                     | “Lập agent-plan với một investigator, hai writer không trùng file và verifier.” |
| `safe-project-mutation`          | Sắp đổi file/generated state và cần report, digest, backup, restore  | “Dry-run thay ba config này; chưa apply trước review.”                            |
| `build-and-runtime-verification` | Cần chứng minh build/test/runtime thực sự chạy                       | “Chạy build, ghi command, exit code, log và limitation.”                            |
| `evidence-first-debugging`       | Có lỗi/crash/test fail nhưng chưa rõ nguyên nhân                   | “Repro lỗi login, xếp hạng giả thuyết, fix tối thiểu và regression test.”     |
| `studio-handoff`                 | Tạm dừng, chuyển người hoặc chuyển session                         | “Cập nhật HANDOFF với branch, files, commands, failures và next action.”          |
| `review-swarm`                   | Review một change set đã biết qua các lane độc lập                | “Review working tree theo correctness, architecture, safety và tests.”               |
| `bug-hunt-swarm`                 | Crash ngắt quãng hoặc bug xuyên subsystem cần nhiều lane điều tra | “Chia lane client, server, protocol; chỉ điều tra read-only và rank suspects.”    |
| `game-feature-brainstorming`     | Chưa chốt hướng thiết kế, cần 2–3 phương án có trade-off      | “Đề xuất ba cách làm party finder cho MMORPG.”                                   |
| `game-feature-to-spec`           | Hướng feature đã chốt, cần spec testable                            | “Biến phương án party finder B thành state machine và acceptance criteria.”     |
| `feature-to-work-packets`        | Spec đã duyệt, cần chia gói việc theo owner/path/dependency         | “Chia spec thành client/server/QA work packets không trùng writer.”                |
| `skill-authoring-and-audit`      | Tạo/sửa skill, xử lý trigger collision hoặc provenance/maturity      | “Audit overlap rồi update skill hiện có trước khi tạo skill mới.”              |
| `studio-project-scaffold`        | Adopt repo, tạo governance, profile, local skills/agents                 | “Report-only gamestudio init; liệt kê file sẽ tạo và collision.”                 |

Chuỗi thường dùng cho một feature:

```text
game-feature-brainstorming
  → game-feature-to-spec
  → feature-to-work-packets
  → studio-agent-orchestration
  → safe-project-mutation
  → build-and-runtime-verification
  → studio-handoff
```

### 4.2 Unity Client

| Skill                                  | Dùng khi                                                                            | Ví dụ yêu cầu                                                              |
| -------------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------ |
| `unity-client-offline-debugging`     | Client không vào offline vì login/bootstrap/mock/network fallback/scene startup   | “Trace offline flag từ bootstrap đến scene; không tạo mock tùy tiện.” |
| `unity-ui-rendering-debugging`       | HUD/widget mất, clipped, sai sorting/depth/anchor/atlas/prefab                      | “Chẩn đoán NGUI widget tồn tại nhưng không render.”                   |
| `localization-authority-audit`       | Source/copy localization lệch, thiếu key, mojibake, encoding hoặc generated drift | “Xác định authority của key UI_LOGIN và các copy client/server.”       |
| `unity-asset-guid-meta-audit`        | Missing`.meta`, duplicate GUID, stale reference, prefab/import lỗi                | “Audit GUID/meta của Assets/UI mà không reimport.”                        |
| `unity-batchmode-build-verification` | Có Unity batchmode, BuildPipeline, Editor.log hoặc Unity CI                        | “Chạy batchmode build Windows và trích lỗi thật từ Editor.log.”        |

Chuỗi gợi ý cho HUD bị mất:

```text
unity-ui-rendering-debugging
  → localization-authority-audit (nếu text/key liên quan)
  → unity-asset-guid-meta-audit (nếu prefab/atlas reference liên quan)
  → unity-batchmode-build-verification
  → build-and-runtime-verification
```

### 4.3 C++ / Lua / MMORPG

| Skill                                      | Dùng khi                                                                            | Ví dụ yêu cầu                                                      |
| ------------------------------------------ | ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| `multi-service-local-environment-doctor` | Local services lỗi port, listener, dependency startup hoặc cross-project isolation | “Map service→configured port→listener; không stop process.”       |
| `game-database-migration-safety`         | Lập kế hoạch MySQL migration cần dry-run, backup và restore                     | “Plan migration 3307 sandbox; không đọc/in log credentials.”      |
| `lua-client-server-contract-audit`       | Lua RPC/opcode/field/type/order giữa client và server bị lệch                    | “So client table với canonical protocol và báo source authority.” |
| `cpp-server-crash-triage`                | C++ dump/AV/segfault/stack/symbol/build identity                                     | “Chuẩn hóa crash signature và rank root causes từ dump.”         |
| `mmorpg-packet-protocol-review`          | Review opcode, byte layout, direction, version negotiation                           | “So packet LOGIN_REQ/RES giữa C++ và Unity.”                       |
| `network-authority-and-exploit-review`   | Kiểm tra server authority, replay, abuse, rate limit                                | “Review claim reward; client nào đang được tin quá mức?”      |
| `save-data-schema-migration`             | Đổi version save/profile/checkpoint/persistence payload                            | “Plan v3→v4 bằng fixtures, backward compatibility và rollback.”   |

Chuỗi gợi ý cho lỗi packet:

```text
lua-client-server-contract-audit
  → mmorpg-packet-protocol-review
  → network-authority-and-exploit-review
  → focused client/server tests
  → build-and-runtime-verification
```

### 4.4 Design, Release và LiveOps

| Skill                               | Dùng khi                                                                      | Ví dụ yêu cầu                                                                    |
| ----------------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| `playtest-evidence`               | Lập/review playtest với scenario, observation và reproduction evidence      | “Thiết kế playtest onboarding cho 8 người chơi mới.”                         |
| `game-performance-budget`         | Định nghĩa/review frame time, memory, loading, network hoặc thermal budget | “Đặt budget mobile tier B và so với capture hiện tại.”                       |
| `economy-source-sink-model`       | Mô hình currency, faucet, sink, exchange và inflation                       | “Model gold economy cho 3 segment trong 90 ngày.”                                 |
| `balance-data-change-review`      | Review diff damage/price/cooldown/drop rate theo bounds                        | “Kiểm tra patch balance có vượt min/max đã duyệt không.”                   |
| `release-candidate-preflight`     | Cần quyết định go/no-go cho RC                                             | “Preflight RC 1.8.0 theo build hash, tests, known issues và rollback.”            |
| `store-submission-checklist`      | Chuẩn bị Steam/console/mobile submission                                     | “Lập checklist Steam metadata, privacy, package và entitlement; không upload.”  |
| `liveops-incident-response`       | Production outage cần incident commander, containment, timeline, recovery     | “Mở incident cho login outage; chỉ quan sát cho tới khi IC duyệt mitigation.” |
| `telemetry-event-contract-review` | Review event name/id/properties/version/privacy/producers/consumers            | “Review event purchase_completed v2 và backward compatibility.”                   |

Chuỗi gợi ý cho release:

```text
build-and-runtime-verification
  → platform-device-compatibility-matrix
  → release-candidate-preflight
  → store-submission-checklist
  → human-controlled publish (ngoài phạm vi skill)
```

### 4.5 Content Production

| Skill                                            | Dùng khi                                                                        | Ví dụ yêu cầu                                                                    |
| ------------------------------------------------ | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `level-and-content-design-review`              | Review flow/pacing/readability/density/progression của level/mission            | “Review dungeon 20 phút theo flow và encounter pacing.”                          |
| `narrative-quest-content-contract`             | Quest/dialogue/objective/reward/localization/cinematic cần một contract        | “Chuẩn hóa quest cứu làng thành state/reward/localization contract.”          |
| `art-asset-pipeline-preflight`                 | Preflight source art, DCC export, scale, pivot, LOD, collision, texture/import   | “Audit batch environment art trước khi import Unity.”                            |
| `animation-rigging-import-audit`               | Audit skeleton, skin, retarget, clips, root motion, compression                  | “Review humanoid rig và root-motion clips cho boss.”                              |
| `unity-ui-art-and-motion-production`           | Tạo UI art/motion từ Figma hoặc phân rã flattened UI screenshot             | “Tách HUD thành raster/native UI/background, review bbox rồi plan uGUI import.” |
| `game-screenshot-showcase-and-store-packaging` | Capture PlayMode, immutable evidence, showcase deck, report-only store packaging | “Lập capture plan cho 6 Steam screenshots; không upload.”                        |
| `audio-content-pipeline-review`                | Review music/voice/SFX/loudness/codec/streaming/loop/middleware/memory           | “Audit boss music loop, loudness và streaming budget.”                            |

Hai skill có maturity `experimental` là
`unity-ui-art-and-motion-production` và
`game-screenshot-showcase-and-store-packaging`. Chúng cần evidence thật từ Figma,
Unity hoặc capture pipeline trước khi có thể đưa ra runtime `PASS`.

### 4.6 Production Management

| Skill                                     | Dùng khi                                                              | Ví dụ yêu cầu                                            |
| ----------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------ |
| `studio-production-planning`            | Lập milestone, staffing, workstream, dependency và forecast          | “Lập kế hoạch vertical slice 12 tuần với acceptance.” |
| `production-risk-and-dependency-review` | Review critical path, owner gap, blocked handoff và schedule exposure | “Review kế hoạch alpha, không thay baseline schedule.”  |
| `qa-test-strategy-and-coverage`         | Xây test strategy/matrix theo risk, platform và test level           | “Tạo coverage matrix cho cross-platform login.”           |
| `platform-device-compatibility-matrix`  | Lập compatibility matrix theo OS/GPU/RAM/input/network/store          | “Định nghĩa support tiers cho Windows và Android.”     |
| `load-soak-capacity-verification`       | Load/soak/concurrency/saturation/leak/failover/recovery                | “Plan soak 8 giờ cho 5.000 CCU với stop conditions.”     |

### 4.7 Product Analytics

| Skill                                    | Dùng khi                                                                      | Ví dụ yêu cầu                                              |
| ---------------------------------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------- |
| `product-analytics-experiment-review`  | Review A/B hypothesis, assignment, metrics, guardrails, sample size và ethics | “Review experiment giảm giá starter pack.”                 |
| `liveops-content-rollout-and-rollback` | Lập canary/cohort rollout, monitoring, trigger và rollback cho live content  | “Plan rollout event Halloween 5%→25%→100%, chưa publish.” |

## 5. Toàn bộ 24 agent role

Ba role nền tảng:

| Agent            | Vai trò                                                  | Khi nên dùng                                               | Ví dụ giao việc                                                      |
| ---------------- | --------------------------------------------------------- | ------------------------------------------------------------ | ----------------------------------------------------------------------- |
| `investigator` | Điều tra read-only về ownership, dependency, call path | Cần biết ai/đâu là source authority trước khi sửa    | “Trace authority của localization key; trả file:line, không sửa.” |
| `implementer`  | Writer bị giới hạn vào một write scope rõ ràng     | Root cause/spec đã ổn định và chỉ còn một gói code | “Chỉ sửa`server/auth/**`; không chạm protocol registry.”        |
| `verifier`     | Kiểm chứng độc lập, không sửa production source    | Sau implementation hoặc trước handoff/release             | “Chạy focused + regression tests, kiểm tra artifact/hash.”          |

Hai mươi mốt specialist:

| Agent                              | Chuyên môn                                                     | Skill thường dùng                                    | Ví dụ giao việc                                                                  |
| ---------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `unity-csharp-client`            | Unity C#, scene, prefab, UI, performance                         | UI rendering, GUID/meta, batch build                    | “Sửa bootstrap offline trong`client/Assets/**`; PlayMode evidence bắt buộc.” |
| `csharp-backend`                 | .NET services, APIs, jobs, tooling                               | Debugging, build verification, environment doctor       | “Điều tra auth API timeout; chỉ sở hữu`services/Auth/**`.”                 |
| `cpp-game-server`                | C++ authoritative server, crash, protocol, memory                | Crash triage, packet review, build                      | “Fix crash signature X trong`server/Game/**`; không đổi opcode.”             |
| `golang-services`                | Go gateway/services, concurrency, observability                  | Debugging, build verification, environment doctor       | “Review goroutine leak và chạy`go test ./...`.”                               |
| `lua-gameplay`                   | Lua gameplay và client-server contracts                         | Lua contract, packet review, debugging                  | “Sửa consumer Lua theo canonical packet; không sửa generated table.”           |
| `game-data-engineer`             | Schema, migration, config pipeline, telemetry                    | DB migration, save migration, telemetry contract        | “Lập migration dry-run; không import DB hay lộ credentials.”                   |
| `technical-artist`               | Shader, VFX, material, rendering, import pipeline                | GUID/meta, performance budget, build verify             | “Audit shader variants và render budget; không overwrite source art.”           |
| `ui-motion-artist`               | Figma UI, raster decomposition, uGUI/NGUI/UI Toolkit motion      | UI art/motion, asset preflight, GUID/meta               | “Tách HUD screenshot, tạo report-only import plan và reduced-motion states.”   |
| `game-showcase-capture-producer` | PlayMode capture, evidence, showcase/store package               | Screenshot packaging, playtest, release/store checks    | “Capture approved checkpoints; không upload/sign/submit.”                        |
| `ui-localization-specialist`     | UI prefab, localization authority, font, overflow, accessibility | Localization audit, UI rendering, playtest              | “Audit German overflow và key authority; không thay generated overlay.”         |
| `systems-game-designer`          | Economy, progression, balance, content systems                   | Feature spec, economy model, balance review             | “Model progression curve và review tuning delta.”                                |
| `qa-automation`                  | Unit/integration/PlayMode/browser/regression evidence            | Playtest evidence, build verify, review swarm           | “Sở hữu`tests/**`; không sửa source để ép test xanh.”                    |
| `build-release-engineer`         | Build, CI, package, rollback, release gate                       | RC preflight, Unity batch build, store checklist        | “Sửa CI cache và verify package; không publish/sign.”                          |
| `liveops-sre`                    | Health, incident, monitoring, recovery, capacity                 | Incident response, environment doctor, authority review | “Quan sát login outage và lập timeline; không restart production.”            |
| `game-security-engineer`         | Trust boundary, exploit path, secrets, authority                 | Authority review, debugging, review swarm               | “Review reward claim replay; không chạy attack traffic.”                        |
| `producer`                       | Milestone, scope, staffing, dependency, risk                     | Production planning, risk review, handoff               | “Lập milestone beta và owner map; không tự approve gate.”                     |
| `level-content-designer`         | Level layout, encounter pacing, mission flow                     | Level review, feature spec, playtest                    | “Review dungeon flow và đề xuất acceptance/playtest cases.”                   |
| `narrative-designer`             | Narrative, quest, dialogue, cinematic, localization contract     | Quest contract, localization, telemetry                 | “Viết quest contract và event telemetry; không sửa gameplay code.”            |
| `asset-pipeline-specialist`      | DCC export, engine import, LOD, collision, compression           | Asset preflight, rig audit, GUID/meta                   | “Preflight character batch và report blockers trước import.”                   |
| `audio-engineer`                 | Music, VO, SFX, middleware, loudness, streaming, memory          | Audio review, performance budget, localization          | “Audit localized VO loudness và memory/concurrency limits.”                      |
| `product-analyst`                | Metrics, experiment, segmentation, live content decisions        | Experiment review, telemetry, governed rollout          | “Review A/B assignment và guardrails; không tự rollout.”                       |

## 6. Cách phối hợp nhiều agent

Chỉ dùng nhiều agent khi workstream thật sự độc lập. Tối đa ba sidecar đồng thời;
main thread giữ critical path và integration ownership.

Một `agent-plan.yaml` tốt cần có:

```yaml
critical_path: xác nhận canonical packet schema
integration_owner: main-thread
concurrency: 3
lanes:
  - role: investigator
    read_scope: [client/protocol/**, server/protocol/**]
    write_scope: []
    expected_output: authority-map.md
  - role: cpp-game-server
    write_scope: [server/network/**]
    do_not_touch: [client/**, registry/opcodes.yaml]
    validation: [focused C++ tests]
  - role: unity-csharp-client
    write_scope: [client/Assets/Scripts/Network/**]
    do_not_touch: [server/**, generated/**]
    validation: [Unity EditMode tests]
verifier:
  role: verifier
  starts_after: [cpp-game-server, unity-csharp-client]
  source_write: false
```

Không nên parallelize khi:

- hai agent cùng sửa một file, scene, prefab hoặc registry;
- interface chung còn chưa chốt;
- writer phải liên tục đợi output của writer khác;
- task chỉ là một fix nhỏ trong một file;
- verifier phải sửa source nếu test fail.

## 7. Tám ví dụ end-to-end

### 7.1 Adopt một repo Unity/MMORPG mới

```text
1. using-game-studio-skills
2. studio-project-intake
3. studio-workspace-routing
4. studio-project-scaffold report-only
5. Human review plan digest, collision và backup
6. Apply scaffold được duyệt
7. studio-agent-orchestration nếu có nhiều repo
8. studio-handoff
```

Prompt:

```text
Adopt repo D:/Games/MyMMO vào MOStudio Kit. Đầu tiên chỉ intake và report-only
scaffold. Giữ nguyên AGENTS.md, .env, config credentials và mọi local skill.
Không apply trước khi tôi duyệt plan digest và backup path.
```

### 7.2 Unity client không vào offline

```text
unity-client-offline-debugging
  → evidence-first-debugging
  → unity-csharp-client hoặc lua-gameplay implementer
  → unity-batchmode-build-verification
  → verifier
```

Prompt:

```text
Trace flag offline, login bypass, mock data và scene bootstrap. Chứng minh root
cause trước khi sửa. Nếu thiếu Unity Editor thì static findings là Verified nhưng
PlayMode verdict phải BLOCKED.
```

### 7.3 C++ server crash

```text
cpp-server-crash-triage
  → investigator xác nhận build/symbol identity
  → cpp-game-server implementer
  → verifier chạy focused tests và compile
```

Prompt:

```text
Triage dump này thành stable signature. Không suy đoán stack khi symbol mismatch.
Sau khi xác nhận root cause, sửa tối thiểu trong server/Game và thêm regression.
```

### 7.4 MySQL migration

```text
game-database-migration-safety
  → game-data-engineer
  → dry-run trên 3307
  → backup/restore verification
  → explicit human approval
```

Prompt:

```text
Plan migration thêm index cho player_items. Chỉ dùng sandbox 3307, không in
credentials, không chạm production. Trả dry-run, estimated lock, backup, restore,
stop conditions và phần cần DBA approve.
```

### 7.5 Tạo UI từ screenshot phẳng

```text
unity-ui-art-and-motion-production
  → ui-motion-artist
  → human bbox/classification review
  → Figma authority + export hashes
  → art-asset-pipeline-preflight
  → safe-project-mutation
  → Unity runtime evidence
```

Prompt:

```text
Phân rã combat-hud.png theo original pixel coordinates thành raster assets,
native UI và background. Giữ original, raw-full và local-composite restoration.
Không import Unity cho tới khi Art Lead duyệt bbox, Figma revision và plan digest.
```

### 7.6 Live incident

```text
liveops-incident-response
  → liveops-sre read-only observation
  → IC xác nhận containment
  → authorized operator thực hiện mitigation
  → recovery verification
  → postmortem handoff
```

Prompt:

```text
Login success rate giảm còn 42%. Mở incident record, ghi timeline và blast radius.
Chưa restart service hoặc đổi DB/config. Đề xuất containment options để IC duyệt.
```

### 7.7 Release candidate

```text
build-and-runtime-verification
  → qa-automation
  → platform-device-compatibility-matrix
  → build-release-engineer
  → release-candidate-preflight
  → store-submission-checklist
```

Prompt:

```text
Preflight RC 1.8.0 tại commit abc123. Bind mọi test/log/package vào đúng build
hash. Liệt kê blockers, waivers, monitoring, rollback và go/no-go. Không publish.
```

### 7.8 A/B test và live content rollout

```text
telemetry-event-contract-review
  → product-analytics-experiment-review
  → product-analyst
  → liveops-content-rollout-and-rollback
  → human approval
```

Prompt:

```text
Review experiment starter pack: hypothesis, assignment, primary metric, guardrails,
sample size và novelty. Nếu đạt gate, lập canary rollout 5/25/100% với trigger
rollback. Không tự bật experiment.
```

## 8. Cài đặt và kích hoạt

### Codex App/CLI

```bash
codex plugin marketplace add hoatv2211/GameStudio-CodexKIT
codex
```

Mở `/plugins`, chọn marketplace **MOStudio Kit**, cài plugin và bắt đầu session
mới. Trong Codex App, mở Plugins từ Codex và làm tương tự.

### Hermes Agent

```bash
npx skills add hoatv2211/GameStudio-CodexKIT -a hermes-agent -g -y
```

Liệt kê skill trước khi cài:

```bash
npx skills add hoatv2211/GameStudio-CodexKIT -a hermes-agent -l
```

### Scaffold skill và agent vào game project

Các command sau dành cho maintainer có full repository clone. Report trước:

```powershell
$report = python -B scripts/generate_adapters.py . --target per-project --output D:/Games/MyMMO | ConvertFrom-Json
$report | ConvertTo-Json -Depth 10
```

Sau khi review exact plan:

```powershell
python -B scripts/generate_adapters.py . --target per-project --output D:/Games/MyMMO --apply --reviewer "Tech Lead" --backup-root D:/Games/MyMMO/.adapter-backup --plan-digest $report.plan_digest
```

Adapter tạo project-local skills dưới `.agents/skills/`, role templates dưới
`.codex/agents/` và activation snippet `.codex/agents.generated.toml`. Snippet
này **không tự active**. Phải review rồi merge thủ công phần cần thiết vào
`.codex/config.toml`; adapter không được tự sửa active config.

## 9. Checklist trước khi tin kết quả

- Skill được chọn có khớp đúng trigger hay chỉ khớp từ khóa chung?
- Repo, branch/build và do-not-touch scope đã được ghi chưa?
- Mọi mutation có reviewer, exact scope, backup và restore chưa?
- Writer có sở hữu file rõ ràng và không trùng writer khác chưa?
- `PASS` có command, exit code và artifact path không?
- Compile success có bị dùng thay cho regression/runtime proof không?
- Unity/Figma/database/service runner vắng mặt có được ghi `BLOCKED` không?
- Generated file có được sửa ở canonical source rồi regenerate không?
- Secrets có bị đưa vào command, log, fixture hoặc prompt không?
- Handoff có ghi failures, limitations và next owner không?

## 10. Những yêu cầu nên tránh

Không nên viết:

```text
Fix tất cả đi, tự quyết định, test thấy ổn thì deploy luôn.
```

Nên viết:

```text
Chẩn đoán trước, giới hạn scope, báo plan và risk. Chỉ apply thay đổi low-risk
đã nêu; mọi database/service/publish action phải dừng chờ approval. Verify bằng
command cụ thể và trả BLOCKED nếu thiếu runner.
```

Không yêu cầu verifier “sửa luôn nếu test fail”; hãy trả finding về cho writer.
Không giao cùng prefab/scene/registry cho hai agent. Không dùng `review-swarm`
thay cho debugging khi chưa có change set ổn định. Không dùng specialist như một
lý do để bỏ qua approval.

## 11. Nguồn tra cứu canonical

- [Skill catalog](CATALOG.md): trigger, type, risk và artifact của 50 skill.
- [Agent role registry](../registry/agent-roles.yaml): ownership, forbidden
  actions, required skills và validation commands của 24 role.
- [Architecture](architecture/overview.md): source of truth, layers, role/skill
  boundary và distribution model.
- [Adoption evidence](adoption.md): phần đã Verified/Snapshot và phần còn
  `BLOCKED`.
- [Repository operating contract](../AGENTS.md): evidence, mutation, ownership,
  generated files, archive và handoff.

Khi tài liệu này khác canonical `SKILL.md` hoặc registry, canonical source luôn
được ưu tiên. Tài liệu hướng dẫn không cấp thêm quyền mutation, publish, database
hoặc service control.
