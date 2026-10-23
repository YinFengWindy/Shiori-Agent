# External Plugin Runtime Contract v1

This contract is the external package boundary for #210 / #261. A package is
validated before its backend is imported. It is **not a sandbox or a trust grant**:
trusted plugin code ultimately runs with the host's privileges.

`package_contract: 1` opts into the package contract. `api: 2` remains the backend
setup protocol. `version` identifies plugin releases; `runtime_api` independently
constrains the host API. Bundled source plugins without `package_contract` retain
the existing v2 build/loading path. An external installer or discovery provider
must call this validator even when the discriminator is absent; omission is not
a way to accept a legacy external package. Source classification/manual trust
(#211/#216), external renderer loading (#213), and cross-host activation rollback
(#262) were delivered separately and are described in the later sections.

## Package layout and schema

A zip contains `manifest.yaml` at its root, without an enclosing directory. The
same root can be placed in a manual package directory. Example:

```text
manifest.yaml
backend/plugin.py
renderer/ui.mjs
renderer/background.mjs
renderer/surface.mjs
style.css
assets/label.txt
```

UTF-8 YAML is required. The executable schema is `validate_package()` in
`apps/backend/agent/plugin_host/package_contract.py`, with shared strict field
readers and renderer validation in the adjacent owning modules. Unknown top-level
and renderer declaration keys are rejected. This table defines the v1 fields:

| Field | Required | Value |
| --- | --- | --- |
| `package_contract` | yes | integer `1` |
| `api` | yes | integer `2` |
| `id` | yes | `[a-z][a-z0-9_-]{0,63}` |
| `version` | yes | full SemVer 2.0 string, including optional prerelease/build |
| `runtime_api` | yes | compatibility range; host currently advertises `3.1.2` |
| `entry` | yes | explicit package-relative `.py` backend entry |
| `capabilities` | yes | existing v2 capability-name list, including `[]` |
| `channels` | no | static channel declarations (Runtime API 2.2); requires the `channels` capability |
| `renderer` | no | object with optional `ui`, `background`, `surface` keys |
| `renderer.<kind>.entry` | per declared kind | package-relative precompiled `.mjs` |
| `renderer.<kind>.css` | per declared kind | list of `.css` files; `[]` explicitly means no styles |
| `assets` | no | list of required package-relative regular files; default `[]` |
| `host_dependencies.python` | no | required host Python distribution names; default `[]` |
| `peer_dependencies` | for any renderer | `react` and `react-dom` compatibility ranges |
| `dependencies`, `optional_dependencies` | no | existing strong/optional plugin ID lists |
| `supports_hot_unload` | no | existing boolean, default `true` |
| `desc`, `author`, `config_model` | no | existing v2 descriptive/configuration metadata |
| `display_name`, `category`, `default_enabled` | no | same meaning and validation as for bundled plugins (see the plugin tutorial): title, `feature` / `channel` / `system` group, strict boolean default enablement; accepted since Runtime API 3.1.1 (#678), older hosts reject the unknown keys |
| `distribution` | no | `builtin` (default) or `external`; see [External source packages in the repository](#external-source-packages-in-the-repository-675) |

There is one backend entry in v1. Each renderer kind may declare one entry. Every
declaration is required; there is no `optional` entry flag. A missing stylesheet,
background module or surface entry blocks the whole package before backend import.
A backend entry must be parseable Python with a top-level `async def setup` that
accepts one positional context and has no additional required arguments. The
existing injected context/capability protocol is unchanged. The external fixture
uses that context without importing host internals; public backend import
portability is completed by #212.

Ranges use whitespace-separated comparators with AND semantics: `=`, `>`, `>=`,
`<`, `<=`; a bare SemVer means equality. Example: `>=3.0.0 <4.0.0`. Caret, tilde,
wildcard, comma, OR and hyphen ranges are deliberately unsupported and rejected.
Build metadata does not affect precedence. Prerelease hosts require a comparator
mentioning a prerelease of that same major/minor/patch tuple.

## Runtime API version history

Ordinary SDK / runtime contract PRs accumulate in [Unreleased](#unreleased),
with a description, **breaking** markers where applicable and PR references.
They do not increment the version individually. Before publishing the SDK or a
desktop release containing new contracts, the maintainer compares the whole batch
with the last published contract and assigns its version once. A contract already
shipped inside a desktop release is published even if the registries still lag;
its version must not be reused for subsequent contract changes.

The single version source remains
`packages/sdk/python/shiori_sdk/_version.py`
(`RUNTIME_API_VERSION = __version__`), synchronized by
`node scripts/sync_sdk_version.mjs`. The source batch is **3.1.2**,
published to both npm and PyPI on 2026-10-16.
Packages using the new 3.1.2 APIs or
channel migration declare `runtime_api: ">=3.1.2 <4.0.0"` and the matching
Python SDK minimum; audited packages using only unchanged APIs retain their
existing minimum. **The selected patch number does not imply backward compatibility.**

Desktop v0.5.5 already distributed #820/#821/#822/#827 while still advertising
3.1.1, which differs from the published registry 3.1.1. That historical mistake
must not be fixed by moving tags or replacing 3.1.1 artifacts. Version 3.1.2
consolidates these additions and the subsequent #847 breaking migration.

| Version | Adds | Introduced by |
| --- | --- | --- |
| `2.0.0` | package contract v1 and the v2 `setup(ctx)` protocol | #265 |
| `2.1.0` | renderer communication (`client.events`, `client.dependency`, `client.background`) | #218; first released in v0.3.0 |
| `2.2.0` | static manifest `channels` declarations and `channels.list` | #363 T1 |
| `2.3.0` | optional channel hooks, including `uses_bot_commands`, and `register_channel(..., description=)` | #363 T2 (hooks) and T4 (`uses_bot_commands`) |
| `2.4.0` | renderer host services as an injected `host` prop, with `host.feedback` (host toasts), `host.ui.InlineError` (host inline error block) and `host.ui.ConfirmDialog` (host confirmation), all with an opt-in 看板娘 `persona` (generic or by scene key) | #362 follow-up (看板娘扩展) |
| `2.5.0` | required `chat_types` session-type declarations on manifest `channels` entries (replacing the channel-level `chat_id_label` / `chat_id_hint`) | #397 |
| `2.6.0` | the `accounts` capability: `ctx.accounts.register(...)` / `report(...)` for host-owned communication account registration and ownership, released with the plugin scope | #419 |
| `2.7.0` | `ctx.tools.register(..., external_allowed=)` to declare a tool usable in external-context turns; from this host on, undeclared plugin tools are unavailable in restricted external-context turns, including tools of existing packages that require an older `runtime_api` (host policy, not an API break) | #489 |
| `2.8.0` | the `@shiori/plugin-sdk` renderer peer (renamed `@yinfengwindy/shiori-sdk` in 3.0.0), resolved to the host's own instance through the renderer import map (see [Runtime API 2.8 plugin SDK peer](#runtime-api-28-plugin-sdk-peer)) | #503 (#440 T1) |
| `2.9.0` | `@shiori/plugin-sdk` shared renderer primitives: components, class names, icons, pure helpers and hooks, plus the UI module, host service, account and role contract types (see [Runtime API 2.9 plugin SDK primitives](#runtime-api-29-plugin-sdk-primitives)) | #504 (#440 T2) |
| `2.10.0` | the host services context (`PluginHostServicesProvider` / `usePluginHostServices`) exported by `@shiori/plugin-sdk`, plus `host.config` (the plugin's own config: read, save a patch, subscribe) and `host.assets` (local path to displayable URL) (see [Runtime API 2.10 host services context, config and assets](#runtime-api-210-host-services-context-config-and-assets)) | #505 (#440 T3) |
| `2.11.0` | `ctx.reportFailure(operation, error)` on the background `setup(ctx)`: a handled background failure recorded in the host's desktop diagnostic log; `@shiori/plugin-sdk` also becomes the source of the `desktop.surface` and `app.background` contract types (see [Runtime API 2.11 background failure reporting and surface/background types](#runtime-api-211-background-failure-reporting-and-surfacebackground-types)) | #508 (#440) |
| `2.12.0` | the `avatars` capability: `ctx.avatars.refresh(kind, channel, id, fetch)` hands channel senders' and chats' platform avatars to a host-owned cache, released with the plugin scope (see [Runtime API 2.12 channel avatars](#runtime-api-212-channel-avatars)) | #514 |
| `2.13.0` | optional `group_listening: true` on manifest `channels` entries: the channel hands every group message to the host, so its groups offer 群聊旁听 (see [Runtime API 2.2 channel declarations](#runtime-api-22-channel-declarations)) | #538 (#527) |
| `2.14.0` | optional `on_heard=` keyword on `ctx.channel_hub.route_account_inbound`: called with the projected message only when an unaddressed group message is stored in the listening records, so a channel can refresh the avatars it shows (see channel-plugins handbook) | #553 |
| `2.15.0` | quoted messages (#555): `infra.channels.reply_context.with_reply_quote` (public as `shiori_sdk.channels.reply_context.with_reply_quote` since 3.0.0) wraps a routed message with the message it quotes (text never truncated, quoted pictures ahead of its own) and records `reply_to_content` / `reply_to_sender_name` / `reply_to_media`; the hub sets `reply_to_sender_is_user` on a routed message whose quoted sender is bound to the user (plugins cannot set it) | #555 |
| `2.16.0` | SDK `CrossfadeLayers` and `SidebarResizeHandle`; packages importing either require `runtime_api: ">=2.16.0 <3.0.0"`. The host no longer provides NcatBot; external `host_dependencies` declarations requiring it are rejected by the existing missing-dependency check. QQ uses per-account OneBot sockets; `psutil` remains a production dependency. | #576 |
| `3.0.0` | **breaking**: the unified Shiori SDK. `@shiori/plugin-sdk` becomes `@yinfengwindy/shiori-sdk` (no alias) and shares version and source tree `packages/sdk/` with the Python `shiori-sdk`, which owns plugin-facing Python contracts, lifecycle values and independent test fakes; every 2.x range is rejected with `incompatible_runtime` (see [Runtime API 3.0](#runtime-api-30-unified-shiori-sdk)) | #551 (#585–#591) |
| `3.1.0` | `shiori_sdk.lifecycle` gains `AfterTurnCtx`, `PHASE_SLOTS` / `require_phase_slot` and `requires` / `produces` on the `LifecycleModule` protocol; packages importing or implementing any of them require `runtime_api: ">=3.1.0 <4.0.0"`. `shiori_sdk.runtime` owns the host's `KNOWN_CAPABILITIES` and manifest `capabilities` validation. `shiori-sdk[testing]`'s `sdk_context` grants only the plugin manifest's (validated) `capabilities` with an isolated temporary `plugin_dir`, and `FakeLifecycle` rejects unknown phase slots like the host. `shiori_sdk.runtime.HostServiceUnavailable` is raised before `setup` when a declared capability's host service is missing, so `workspace` / `session_manager` on the typed contexts are no longer optional. `shiori_sdk.redaction.summarize_llm_output_for_log` moves back to the host (`core.common.llm_output_log`); `redact_secrets` stays in the SDK. Those corrections preceded the first 3.1.0 publication on 2026-10-03 | #620, #622, #624 (#619) |
| `3.1.1` | **breaking** relative to published 3.1.0: removes `SurfaceHandle.voice` and its voice types, and replaces relationship `closeness` with affection. The batch also adds plugin services/native resources, local and managed environments, private settings autosave, role capability dialogs, external turns, terminal chat events and scoped attachment tools. See the complete batch below. | #674/#677, #678, #679, #683/#688, #699/#703, #700/#704, #701/#705, #710/#717, #715/#728, #721/#726, #719/#735, #740/#743, #734/#738, #720/#744, #749/#751, #748/#754, #750/#752, #756/#757; consolidated by #762 |
| `3.1.2` | **breaking** relative to published 3.1.1: removes channel push-sender registration and makes `message_push` raise on failure. Adds background results, process resources, external links and secondary sidebar styling. Published to npm and PyPI on 2026-10-16. | #820, #821, #822, #827, #847; finalized for #851 |

### Unreleased

<!-- Record the next contract batch here, with PR references and breaking markers. -->

- **Plugin kernel `shiori_sdk.kernel` (issue #900, refactor P1).** New SDK
  package holding the kernel the host now runs on: `Key[T]`, `PluginSpec`,
  `Kernel` (`start` / `reload` / `stop`, host steps `plan` / `activate` /
  `deactivate` / `drain`) and the plugin `Context` (`provide` / `require` /
  `get`, `on` / `watch` / `emit`, `effect` / `spawn` / `on_drain`), `Veto`,
  `fail_open` / `fail_closed` via `on_error`, post-chain core checks, and the
  `PluginStarted` / `PluginFailed` / `PluginStopped` events. `PluginDiagnostic`,
  `PackageContractError` and `RendererActivationError` move here from the host.
  `shiori_sdk.testing.kernel.KernelHarness` runs specs on the real kernel and
  offers `await harness.idle()` for watchers. Existing v2 plugin contexts are
  unchanged; plugins do not receive the kernel `Context` yet (P4).
  Kernel semantics fixed during P1 (the first two confirmed by the maintainer):
  the default reload drain
  waits only for `on` / `watch` handlers in flight, while spawned tasks are
  cancelled on dispose; two plugins providing one key without `replaces` /
  `conflicts` are both BLOCKED (a plugin duplicating a core key fails startup);
  only `requires` can form a dependency cycle.
  **Behavior visible to existing plugins:** an in-generation reload now also
  reloads the running plugins that list the target in `optional_dependencies`
  (disable/unload still takes only hard dependents), and active plugins (their
  tool hooks, phase modules, channels and bot commands) are aggregated in
  kernel order — dependency depth, then plugin id — instead of discovery and
  load order, so the order stays the same after a reload.
- **Core service `CRASH_REPORTING` (issue #901, refactor P2, D13b).** New
  `shiori_sdk.core` package for core socket contracts; its first module
  `shiori_sdk.core.crash_reporting` defines the `CrashReporting` protocol
  (`install(owner, handler, system, thread, loop, loop_handler)` returning the
  original hooks, `uninstall(owner)`) and `CRASH_REPORTING = Key("crash_reporting")`.
  The host provides it as a core service that arbitrates `sys.excepthook`,
  `threading.excepthook` and the loop exception handler; the v2 `diagnostics`
  capability now installs through it, with unchanged behavior. Plugins cannot
  inject it yet: observe switches to `inject: [crash_reporting]` in P3.

- **breaking: capabilities `role_store`, `role_runtime_registry` and
  `relationship_runtime` removed (PR #921, issue #901, refactor P2).** None of the three
  had a user; `roles` and `models` cover what plugins read from roles. They
  leave `shiori_sdk.runtime.KNOWN_CAPABILITIES` and the `capabilities` enum of
  `manifest.schema.json`, and the host no longer exposes `ctx.role_store`,
  `ctx.role_runtime_registry` or `ctx.relationship_runtime`. A third-party
  manifest that still declares one of them is rejected at discovery and
  package validation as an unknown capability, so the plugin does not load;
  remove the name from `capabilities` (using `roles` / `models` instead) to
  load it again.

- **breaking: capability `proactive_gates` removed (PR #<待定>, issue #902,
  refactor P3-1, D19).** No plugin contributed a gate. It leaves
  `shiori_sdk.runtime.KNOWN_CAPABILITIES` and the `capabilities` enum of
  `manifest.schema.json`, and the host no longer exposes `ctx.proactive_gates`.
  A third-party manifest that still declares it is rejected at discovery and
  package validation as an unknown capability, so the plugin does not load;
  remove the name from `capabilities` to load it again. Proactive admission now
  runs only the core motives (scene follow-up, relationship fallback), in the
  same order and with the same rule that a motive may claim a tick but never
  block it.

- **Natural proactive replies and background reports (PR #894, issue #868).** The current
  role's built-in natural-chat capability also applies to proactive draft
  `message_push` output, Drift dialogue and captured background-result reports.
  Natural internal drafts use the shared `messages` schema/validator and at most
  one completion-only `finish_reply` correction; target/evidence/finish controls
  stay on the existing proactive draft. Ordinary `message_push` string payloads
  are unchanged. Generation-owned delivery uses the same reply-sequence owner.
  Native account transports retain ownership of request deadlines; the host adds
  no fixed segment timeout. A started send and its bookkeeping finish together;
  failed or uncertain sends stop the batch without retry, and only confirmed dialogue
  enters subsequent context. Completed tool facts survive invalidation and enter
  model history before pacing releases the role gate. Generation, sends and
  protected accounting remain serial; older batches cannot replace newer mood
  state. Drift reauthorizes its late-selected target before sending.
  Proactive success/failure, presence, relationship and committed-turn observers
  run once for the logical reply; a partial reply publishes only its delivered
  prefix. A cancelled final send that still confirms every segment settles as
  success once, including ACK/dedupe effects. Explicit-send tool payloads and
  system notifications are unchanged.
- **Validated reply bubbles (PR #894, issue #868).** `AfterReasoningCtx.reply_messages`
  carries the validated natural-chat bubbles. Decorators rewrite each item;
  `reply` stays their plain join for whole-turn observers. Additive relative to
  published SDK 3.1.2. The host no longer splits a reply on code fences or
  indentation, and no longer round-trips a delimiter through the prompt.
- **Read-only account target routes for natural batches (PR #894, issue #868).** Channel
  plugins may register `account.resolve`, receiving `account_id` plus the existing
  `AccountTarget.to_payload()` fields and returning `AccountRoute.to_payload()`:
  canonical `channel`, `chat_id`, `chat_type` (`private` or `group`) and optional
  positive integer `message_thread_id`. The channel owns platform parsing,
  account-instance lookup and supported-target validation;   resolution sends
  nothing and does not grant tools or participation. A confirmed private send
  and a full-tool grant use the same `AccountRoute`; `for_private` rejects
  groups and topics. `AccountConversation` was never part of published SDK
  3.1.2. Natural proactive
  retargeting requires this capability and explicitly fails if it is absent;
  the host never guesses a platform address. Already selected bound private
  chats and captured background origins reuse their authoritative address.
  Ordinary `account.send` / model `account_send` do not call or require the new
  resolver. The host checks account ownership before and after resolution and
  pins the same ownership/connection fence for the batch's sends. Bundled
  Telegram, QQ, QQBot, Feishu and Grok account plugins supply the resolver.
- **Background origin and ordering (PR #894, issue #868).** Host-originated spawn results
  retain their original role, account, chat, topic and real sender; typed legacy
  completions without an origin retain their existing internal path. Typed
  completions and captured SDK reports with an account retain the existing
  AccountAccess connection fence;
  the host rechecks it inside the role gate and immediately before each queued
  transport callback, including error/retry output. Revoked destinations receive
  neither the report nor an error notification, with natural chat on or off. This
  fence is private queue state and introduces no SDK sending interface.
  Internal results are never reclassified as external user admission. A group proactive
  reply with no addressee yields to the first admitted, deduplicated request;
  addressed output yields only to that real sender, while other senders wait in
  chat order. Channel admission/mention/reply/blacklist policy stays in the
  channel owner. Desktop input can supersede its natural proactive/report tail.
  Persisted message and batch IDs survive reload. Proactive messages and internal
  background reports do not become independently undoable user turns; reports
  and their tool facts are excluded from passive-turn selection. Existing
  passive batches still undo as a whole, and an unresolved passive anchor still
  prevents deletion of an earlier unrelated turn. No SDK version is assigned
  until this contract batch is released.

- **Fixed-peer account settings (PR #892, issue #891).**
  Account reports may include `fixed_peer` to declare that connection activation
  controls admission to one fixed peer. The host hides private/group enable
  switches and sender blacklist controls for this capability; `full_tools` still
  controls the separate explicit tool grant. Other accounts keep their existing
  settings. Providers must normalize legacy admission rules before registration
  and reject unsupported rule mutations; the capability alone does not bypass
  the host's admission or authorization checks. Grok is the initial consumer.

- **Reply-chain ownership stays in the channel journal (issue #895).**
  Grok does not keep a write-only connection error or journal status string.
  Its receipt table never expires a chain that still has queued, sending or
  uncertain work. A `reply_to` whose parent was already expired starts a new
  chain instead of failing or inheriting the old budget. The host no longer
  reserves outbound identity before enqueue: `PreparesOutbound`,
  `MessageBus.prepare_outbound` and `TurnCommitted.will_dispatch` are removed.
  `AfterTurnCtx.will_dispatch` remains the observer-facing dispatch gate.
  `ReplyInterruption` is the only cancellation owner; `ChannelSequenceOwner`
  registers the current generation's plans and invalidates them on replacement.
  One `NaturalReplyRequest` carries the optional finish_reply protocol through
  a reasoning run.

- **Account media supplements (PR #889, issue #886).** Host/plugin calls to `account_send.execute`
  may supply protected `push_proactive=False` and `push_chat_id` with
  `target_kind="user"`. Here `channel` is the original transport channel; the host
  resolves its exact canonical private chat against current user bindings and the
  role's owned accounts before using the account plugin's sender. It never guesses
  a target from a chat ID or redirects to another bound chat. Both arguments are
  absent from model schemas and protected by execution-context precedence.
  `ExternalTextPushed.proactive` defaults to true; false persists the supplement
  without proactive classification while retaining the existing commit broadcast.
  NovelAI records generation cooldown/dedup before invoking delivery, so a failed
  or cancelled send cannot cause the next observation to regenerate the image.

- **Desktop and natural-channel supplements (PR #880, issue #867).** Every desktop chat accepts
  supplements, including ordinary streaming replies. On external channels this
  requires the built-in natural-chat capability: admitted and deduplicated input
  invalidates only the same role, receiving
  account, channel, chat type, chat, topic and real sender's reply plan. Other
  group senders retain chat order; unaddressed or blocked messages do not enter
  this boundary. The dispatcher invalidates before waiting for the previous
  chat task. Generation stops at its next model/tool completion boundary,
  persists accepted input and completed tool facts, and starts no further tool
  calls or summary requests for the invalidated plan. A started delivery and
  its bookkeeping finish; confirmed prefixes remain and unstarted tails are
  discarded. Desktop `chat.send` acknowledges supplements without waiting for
  old generation, while each queued runner waits for predecessor cleanup.
  Ordinary desktop replies freeze their already published stream prefix and
  thinking, stop publishing further deltas immediately, and persist that prefix
  with completed tool facts before the next runner starts. Ordinary runtime
  reload behavior remains unchanged until a supplement invalidates its owner.
  Turn-owned `session.updated` events also carry `turn_id`; old persisted
  messages are still reconciled by ID without changing the current turn or
  reverting its session summary. Internal/proactive entrypoints remain outside
  this behavior. `InterruptController.request_interrupt` accepts the receiving
  `account_id`, `chat_type` and opaque `message_thread_id` alongside channel/chat.
  Channel `/stop` uses that exact origin; partial legacy addresses never select
  a scoped account/topic by a unique-match fallback. Partially supplied external
  origins return idle; missing transport or chat type never implies desktop or
  private-chat ownership. Across runtime generations, supplements chain to the
  latest actually owned turn; borrowed predecessor references cannot receive
  turn-ID cancellation or impersonate a generation's accepted work. Desktop session-only and
  unscoped legacy task calls remain compatible. **breaking** for external
  integrations targeting account-scoped turns: session-only or partially
  addressed `request_interrupt` calls no longer infer that target; callers must
  pass its receiving channel, chat, account, chat type and topic. Bundled channel
  callers are migrated. SDK/runtime versions are unchanged.

- **External plugin trust before execution (PR #884, issue #878).** The desktop prompts
  for enabled, valid, untrusted startup candidates using its shared persona
  confirmation dialog. `plugins.trust` accepts an optional explicit `enable`
  intent and `operation_id`, revalidates the displayed directory and content,
  and admits only that startup candidate. First approval can activate within
  the current application through the normal plugin lifecycle; channels retain
  the existing generation-swap boundary. `plugins.list.trusted` describes an
  actual exact-content grant separately from `can_trust` and runtime state.
  Cancelled candidates remain inactive and are not prompted again in the same
  desktop session; manual retry remains available. A session execution ledger
  prevents bridge reconnects from replacing already executed backend contents;
  the existing renderer code-identity boundary remains unchanged.

- **Explicit account tool permission (PR #873, issue #870).** `AccountResponseRules.allow_full_tools`
  defaults to false, including when absent in saved JSON. Only accounts declaring
  the `full_tools` capability expose the per-account switch. The channel hub drops
  plugin-supplied `account_full_tools` metadata before asserting its own admission
  flag; tool consumers also check the current live account, role and thread.
  `accounts.report(tool_conversation=AccountRoute(...))` names the current
  canonical private route eligible for this grant. The host validates it against
  the reporting account. Missing routes grant nothing; changed routes reject old
  queued messages and background targets even if the account's plugin token is
  unchanged and the new peer later receives full tool permission.
  This grants the role's enabled tools without changing `MessageSource`, user
  identity, automatic history or memory scope. Queued turns recheck saved policy,
  and background result targets revalidate original account ownership, runtime
  access and current authorization both before queueing and inside the role gate.
  `allowFullTools` is optional in TypeScript snapshots; absent means false. Rule
  serializers omit the disabled field for compatibility with older payloads.

- **Explicit account-send acceptance and canonical private conversations (PR #872, issue #869).**
  `account.send` may return `accepted: true` when the transport accepts a task but
  provides no platform message ID. Only the boolean `true` permits an empty ID;
  absent/ambiguous receipts remain uncertain. Existing `message_id` receipts keep
  their behavior. A run/task ID must not be presented as a platform message ID.
  A confirmed private send may also include `conversation: {channel, chat_id,
  chat_type: "private"}` using `shiori_sdk.accounts.routing.AccountRoute`.
  This must be the canonical inbound address resolved by the sending plugin,
  not a guessed chat ID derived from its target ID. The host validates the
  channel against the account platform and records `account_send` in this network
  thread even when the peer is not the desktop user. Invalid optional addresses
  are logged and omitted without retrying an already accepted side effect.
  `TurnCommitted.external_message_id` now carries the original inbound ID (default
  empty for non-transport turns), so channels can finish durable input even when
  the role intentionally sends no reply.

- **Acknowledged channel reply sequences (#866 / #876).** Ordinary channel turns may
  select the host-owned `ReplySequencePolicy` when the live transport registers with
  `subscribe_outbound(..., supports_reply_sequence=True)`. Telegram, QQ, QQBot
  and Feishu opt in. `OutboundMessage.delivery_outcome` carries a transient
  `DeliveryOutcome(status, external_message_id)` after a channel operation;
  queue acceptance is never a sent receipt. Each current segment has its own
  persisted ID and platform receipt; unstarted suffixes remain private. Failed
  or unknown outcomes stop the batch without bus retries. Pending, failed and
  uncertain sequence rows are excluded from shared model and memory history;
  executed tool traces remain separate facts. Channel callbacks bound one
  logical segment (length chunks, attachments and bookkeeping) to 90 seconds;
  a deadline records uncertainty. Pacing holds neither the transport lock nor
  the role generation gate, so unrelated chats can proceed while same-chat
  requests retain admission order. Runtime replacement cancels old suffixes
  and retains already started sends through their final bookkeeping. Explicit
  `InterruptController.request_interrupt` accepts optional `channel` / `chat_id`
  keywords so `/stop` targets its chat; default single-session callers remain
  compatible. Automatic new-input interruption and internal/proactive replies
  are not enabled by this change. SDK/runtime version remains unchanged until
  the release batch is assigned.

- **Complete reply sequences (#865 / #871, built-in capability #874 / #875).** The
  default-off role setting `runtime_config.natural_chat_enabled` selects a
  host-owned presentation policy on interactive desktop turns and admitted
  ordinary turns on opted-in channels (Telegram, QQ, QQBot and Feishu).
  Model text is buffered, existing reply hooks run, and the host parses boundaries
  outside fenced code and publishes complete messages serially. Each stored
  message has its own ID and shares `reply_sequence_id` (the desktop `turn_id`
  or channel `request_id`), with a zero-based `reply_sequence_index`.
  Desktop attempts also carry `trigger_user_message_id`, the stable persisted
  user row shared by initial sends and retries. Sequence undo resolves that exact
  row within the same thread; an unresolved anchor never selects an earlier turn.
  The desktop receives intermediate `chat.message` events with the same session
  update payload shape as `session.updated`; they do not finish the turn.
  `chat.done`, `chat.error` and `chat.cancelled` remain the terminal events.
  Cancellation retains the published prefix and abandons the pending suffix;
  without a policy, existing single-message streaming is retained. The built-in
  capability contributes only the instant-chat setting and separator instructions.
  Role manifest v10 atomically migrates the former plugin preference, preserving
  an explicit built-in value and unrelated plugin namespaces.
  **breaking** relative to the unreleased #871 API: removes
  `shiori_sdk.reply_sequence.ReplySequencePolicy` and the plugin-only
  `PromptRenderCtx.reply_sequence` / `supports_reply_sequence` fields. They had no
  other plugin consumers; the policy and eligibility input now live in the host.
  Published SDK 3.1.2 did not contain those additions. The SDK version stays unchanged
  until the next contract batch is finalized; delivery events and metadata above
  remain available.

- **In-generation plugin reload (host groundwork, #856 / #860).** The plugin kernel can
  reload one plugin and its hard dependents without replacing the runtime generation;
  the bridge starts using it with #857. Plugin-observable semantics:
  - `ctx.runtime.on_drain` callbacks must only wait for accepted work and must not tear
    anything down. They may run more than once, and may run while the instance stays
    active (a reload abandoned after its drain timeout reopens the instance).
  - A reloaded instance sees `ctx.runtime.was_active` as `True`, so start-up recovery
    does not repeat.
  - Once an instance is being reloaded, unloaded or terminated, calls into its tools,
    RPC handlers and services — including through references held from earlier — are
    rejected with `PluginRpcError("plugin_unavailable")` instead of reaching the old
    instance. Unload and disable still cancel in-flight work rather than waiting for it.
  - Process resources acquired with `ctx.process_resources` survive an in-generation
    reload, and the new instance re-acquires the same object.
  - The SDK managed runtime helper (`shiori_sdk.managed.rpc.register_runtime_rpc`) no
    longer stops the managed service from `on_drain`; it stops on disposal (#860).
- **Saving plugin config reloads within the generation (#857).** `plugin.config.set`
  reloads the target and the ACTIVE plugins that hard-depend on it in the current
  runtime generation instead of publishing a new one; other plugins are not set up
  again and keep their effects (managed services, channel connections), and the
  `generation` stays the same. Plugin-observable semantics:
  - Each phase-module `run` and tool-hook `run` contributed through `ctx.lifecycle` /
    `ctx.tool_hooks` counts as an in-flight call of its plugin: a reload waits for the
    run in progress (not for the whole turn). While the plugin is sealed or after it
    was disposed, its phase module passes the frame through unchanged and its
    `post_tool_use` / `post_tool_error` hooks leave the result unchanged, while its
    `pre_tool_use` hooks fail closed: the tool call is denied with "插件 X 正在重载，本次
    工具调用未执行，请稍后重试" instead of running unguarded. This also applies to tools
    that a closure plugin's own in-flight call runs through the executor (for example a
    subagent): those inner calls are denied, so that outer call fails instead of
    finishing. A turn that started before the reload never reaches the old instance.
    **breaking** (narrow): the host gates `run` in place on the contributed
    object, as it already does for tools, so phase modules and tool hook objects must
    accept attribute assignment (no `__slots__`); otherwise `setup` fails.
  - The reload waits up to 60 s for the closure's in-flight calls. If they do not
    finish, nothing changes and the save fails with `plugin_reload_busy`
    (`details.plugin_ids` = still busy). If the new config fails `setup`, the old
    config is restored and the save fails with `plugin_reload_failed`
    (`details.plugin_ids`, `details.restore_failed`). If writing the config file fails
    after the new instances started, they are rolled back the same way and the save
    fails with `runtime_commit_failed` carrying the same details. In all cases the
    config is not written and the settings page keeps the draft.
  - New bridge event `plugins.reloaded` with payload `{generation, plugin_ids}` (target
    first, then dependents). It replaces `runtime.applied` for this save: renderer
    communication contexts, `usePluginRpcClient` clients, background scopes and native
    sessions of exactly these plugins are closed and recreated; the reloaded plugins'
    renderer entries report activation again for the new `activation_token`. Other
    plugins' contexts and the role list are not refreshed. The event is emitted once
    per applied reload, also when the saving request was cancelled after the reload
    committed; an idempotent retry of the same `operation_id` returns the remembered
    result without emitting it again.
  - Unchanged: a closure that contributes or declares channels, or contains a plugin
    with `supports_hot_unload: false`, and a target that is not ACTIVE still swap the
    generation (`runtime.applied` with `changed: true`, or `plugin_restart_required`).
    A disabled plugin's table is stored without any reload. Install, update and
    uninstall still swap the generation.
  - `plugin.config.set` no longer has the bridge's default 30 s request deadline, like
    `runtime.apply`: the drain is bounded, but waiting for the settings lock, setup,
    restore and the generation-swap fallback are not.

- **Enabling and disabling a plugin happens within the generation (#858).**
  `plugins.setEnabled` loads or unloads the target and the plugins that hard-depend
  on it in the current runtime generation; other plugins are not set up again and
  keep their effects, and the `generation` stays the same. Plugin-observable
  semantics:
  - Disabling disposes the target and its ACTIVE hard dependents without draining:
    `on_drain` does not run, scoped and `spawn_runtime` background tasks are
    cancelled (as on a generation swap), calls into them are rejected with
    `plugin_unavailable`, and their process resources are closed. The target
    becomes `DISABLED` and the dependents `BLOCKED`.
  - Enabling sets up a disabled target and the plugins that were `BLOCKED` only
    because of it, with `ctx.runtime.was_active` `False`. A plugin whose setup fails
    stays `FAILED` with the flag persisted, as before.
  - The bridge emits `plugins.reloaded` `{generation, plugin_ids}` (target first,
    then dependents) instead of `runtime.applied`, with the same once-per-operation
    guarantees as for a config save; the result carries the same ids in
    `reloaded_plugins`. Renderers refresh the plugin roster and replace exactly
    these plugins' communication contexts, background scopes and native sessions;
    surfaces of a disabled plugin close when the roster drops it. If writing the
    config file fails, the previous states are restored and the toggle fails with
    `runtime_commit_failed`.
  - Unchanged: a closure that contributes or declares channels (qq, qqbot, telegram,
    feishu), contains a plugin with `supports_hot_unload: false`, or (when enabling)
    depends on a plugin in a state only a fresh load can retry (for example
    `FAILED`) still swaps the generation (`runtime.applied` with `changed: true`, or
    `plugin_restart_required`).

### 3.1.2 release batch

Published to both npm and PyPI on 2026-10-16 by the
[SDK release run](https://github.com/YinFengWindy/Shiori-Agent/actions/runs/38855118971).

- #847 (issues #842 / #843): **breaking** — `ChannelContext.push_tool`, the
  `shiori_sdk.channels.services.PushSenders` protocol and the testing
  `FakePushSenders` / `fake_channel_context(push_tool=)` are removed. Since
  #829 / #839 a role's `message_push` may only reach its own desktop session, so
  channel senders registered there were unreachable; role sends to channels use
  `account_send` (`account.send`). Channel packages that still call
  `ctx.push_tool` fail at `start` and must drop the registration. `message_push`
  (reached by plugins through `ctx.tools.get_tool`) now raises on an unknown
  channel, an unsupported payload or a sender failure instead of returning error
  text; returning at all means the payload was sent or queued with the current
  turn, so callers no longer inspect the result wording.

- #827 (issue #825): `@yinfengwindy/shiori-sdk` exports
  `secondarySidebarShellClass({ animating, collapsed, inset: "list" | "nav" })`,
  the outer box of a secondary sidebar in the host's resizable track (surface,
  content motion, collapsed slide-out, horizontal inset; `"list"` also sets the
  chat-list vertical padding). The host's chat, role-workspace and settings
  sidebars use it, as do the novelai and herdr page sidebars. Additive.

- #822 (issue #819): renderer `PluginHostServices.openExternal(url): Promise<void>` exposes
  the existing validated desktop external-link operation. It accepts the host's
  HTTP(S)/mailto protocols and rejects refused links or shell failures; plugins
  receive no raw IPC access. The independent host-services fake records calls.
  Process-resource attachments become inactive as soon as their effect scope
  begins cleanup, so retired view subscriptions cannot enqueue new emissions.

- #821 (issue #818): `process_resources` exposes plugin-private, versioned in-process resource
  contracts. Candidate generations attach without activating or reconfiguring
  the resource; publication activates the new attachment and closes removed
  resources. Rollback closes only otherwise unowned provisional resources.
  Unload and shutdown await cleanup and surface failures. Factories must construct
  idle objects without retaining generation contexts, providers, RPCs or tasks.
  `FakeProcessResources` supplies independent SDK testing support.
  Background result targets now use the current runtime dispatcher for each
  report rather than retaining the originating runtime; stored origins remain
  unchanged and their user binding is checked at admission. No restart recovery.

- #820 (issues #817 / #816): `background_results` grants `capture()` during an
  authenticated role tool turn. The returned `BackgroundResultTarget` retains the original
  role, thread, actual transport and bound sender; `report(result_id, text)`
  rechecks them inside the role turn gate and reports through the role's normal
  outbound path. Repeated attempted IDs do not produce another report, including
  after an ambiguous failure. This is in-process only, without restart recovery.
  SDK testing adds explicit `FakeBackgroundResults` / `FakeBackgroundResultTarget`.

### 3.1.1 release batch

All APIs in the following themes share the same 3.1.1 minimum. The intermediate
development increments were never individually published.

#### Published API migrations

**Breaking — surface voice (#674/#677).** The published 3.1.0
`SurfaceHandle.voice`, `SurfaceVoice`, `SurfaceVoiceGesture`, `VoiceStatePayload`
and `VoiceInputSource` are removed. The host no longer owns speech orchestration.
Plugins use their own surface/background messages and scoped native resources;
desktop pet owns preferences and orchestration. The range checker alone still
accepts an old `>=3.1.0 <4.0.0` package, so an affected external package must
migrate, rebuild and require 3.1.1; this is not automatic compatibility.

**Breaking — relationship state (#715/#728).** Relationship snapshots no longer
carry `closeness`; it is dropped when reading stored snapshots.
`RelationshipSnapshot.internal_profile.relation_state` uses the explicit
`RelationState` fields (`dependence`, `security`, `initiative_desire`,
`neglect_sensitivity`, each 0–1), replacing `Record<string, number>`. Consumers of
closeness must use the role's `AffectionSummary`. Loneliness growth and the
relationship proactive motive require initialized affection of at least 60
(the start of 「亲密」).

#### Services, native resources and local utilities

Generic `services` publication/discovery/calls, pure ASR/TTS wire values, scoped
native capture/playback/key capabilities and background chat replace host speech
business (#674/#677); see [plugin services](#runtime-api-311-plugin-services-native-resources-and-background-chat).
Local utilities are `shiori_sdk.files.audio.pcm_wav_duration`,
`shiori_sdk.files.staging.staged_import_file` and
`shiori_sdk.local_http.loopback_http_url` (#678/#675).

External Package Contract v1 accepts `display_name`, `category`,
`default_enabled` and `distribution: external` (#678): the latter identifies
repository sources delivered by normal ZIP installation. Older hosts reject the
new metadata keys.

#### Private managed environments and native pickers

`shiori_sdk.managed` provides fixed artifact acquisition, atomic installation,
owned processes, background operations and `register_runtime_rpc`;
`shiori_sdk.files.lease`, `ManagedRuntimePanel` and `useManagedRuntime` complete
the opt-in backend/renderer boundary (#679/#676). Providers retain model,
installation and orchestration policy. `host.pickFilePaths` returns the user's
original file paths without copying; `host.pickDirectory` returns a chosen native
directory and may create one. `NativeFilePathPickerOptions` and both helpers are
available in the SDK/fakes (#699/#703).

Environment hygiene (#700/#704) adds `ManagedRuntime.remove()` / `runtime.remove`
and the `removing` phase. Removal requires no active task or service in any
generation; it also works without an installed version. Status reports
`reclaimable` cached download bytes and `staging` leftovers. Successful preparation
cleans downloads and other versions; failed/cancelled preparation retains its
cache. Cleanup failures appear in status `error` without undoing publication.
Removal/cleanup are joined on cancellation. `Installation(..., installed_size=)`
checks free space before copying: missing artifact bytes + installed bytes +
max(1 GiB, 5%). `run_owned` / `OwnedChild` incrementally decode UTF-8, otherwise
Windows ANSI, into UTF-8 logs, split CR/LF/CRLF, and include the last meaningful
line in preparation/early service failures. `Processes.spawn` accepts asyncio
subprocess constants for stdout/stderr.

The finalized install-location contract (#701/#705) separates a persistent state
root (`current.json`, `location.json`, locks, logs, provider files) from
`install_root` (downloads, `s/`, `v/`, child tmp/cache and provider-declared
`scratch` directories). `Installation.relocate(root | None)` /
`ManagedRuntime.relocate()` / `runtime.relocate {directory?}` select a dedicated
namespace directory inside an existing local drive directory, only while nothing
is installed/kept and no task runs. UNC/device namespace paths and nonempty target
installations are rejected; Windows namespace matching is case-insensitive.
Omitting the directory restores the default. Location survives generations while
`OwnedService.root` remains the state root. A custom pointer records its absolute
install root; a default follows moved plugin data. An unreadable location is
reported in `error`, repairable by relocation without a pointer or by removal.
Removal unlinks links/junctions without following them, removes only installation
entries and an empty custom root, and retains every state-root file.

`runtime.prepare {source}` verifies a regular original absolute file without
links/junctions, its suffix, exact size for a single artifact, and SHA-256 before
building. It never copies, moves or deletes that original; resource ZIP members
are extracted to staging. Free space is measured on the install volume; an
in-place single-file import needs no download-copy bytes. The build callback is
`build(staging, resources)`, with a name-to-verified-path mapping also returned by
`acquire_resources`. `verify_file` verifies original single files;
`acquire_artifact` has no `source` argument. `ManagedRuntime(..., import_asset=)`
owns import selection; neither `register_runtime_rpc` nor `submit` takes it,
and `register_runtime_rpc` has no `max_bytes` parameter.

Status includes `location`, `customized`, `required`, `required_import`, `free`,
`removable` and `relocatable`. `ManagedRuntimePanel` has no `namespace` prop; it
shows installation location and space, imports with `host.pickFilePaths`, offers
location/reset controls and confirms destructive removal through the host.
`useManagedRuntime` exposes `ManagedRuntimeAction` and `relocate(directory?)`.
These final signatures supersede earlier workspace-only experiments; those
intermediate managed APIs were never published.

#### Private settings and role capability cards

`usePrivateAutosave`, `SettingsField`, `SettingsToggleField`, `SettingsGroup`,
`SettingsSectionCard`, `settingsInputClass`, `settingsGroupStackClass` and
`host.ui.SettingsSavedStatus` provide plugin document autosave and the host
settings layout (#683/#688).

`RoleCapabilityCard.settings` opens the card's medium-width settings dialog;
Escape, backdrop and close button dismiss it and return focus to the trigger.
Its contents mount on first open and stay mounted while closed, preserving
pending autosave/retry; mounting itself writes nothing. The dialog does not own
a save transaction. `PluginRoleSettingsProps` supplies `roleId` (null for a new
role), scoped `client` and `moodCatalog`; role settings render under
`PluginHostServicesProvider` and remount per role. `storage: "plugin"` with
`read: () => ({})` keeps private settings out of the host role draft.
`RoleCapabilityCard.onSettingsOpenChange` /
`CapabilitySettingsDialog.onOpenChange` let a plugin flush autosave on close.
`compactIconButtonClass` is exported from the main SDK and renderer peer
(#719/#735, #720/#744).

The experimental `roleUi` contribution, `PluginRoleUiProps` /
`PluginRoleUiContribution` and `usePrivateDraft` were removed before publication
(#750/#752). They are not available in this release batch. A UI declaring
`roleUi` fails export validation; a precompiled import of `usePrivateDraft` fails
to link. Migrate workspace builds to `roleSettings` and `usePrivateAutosave`.
The role editor's unsaved-change guard covers only the host role draft.

#### Affection values

`AffectionSummary` is available on `RoleRecord.affection`, session metadata and
`roles.affection.history`. It is absent before the first conversation initializes
affection. `value` is -100–100; `AffectionStageName` has seven stages: 「厌恶」
(-100 to -50), 「冷淡」 (-49 to -1), 「陌生」 (0–19), 「熟悉」 (20–39),
「朋友」 (40–59), 「亲密」 (60–79), 「挚爱」 (80–100). `progress` is 0–1
within the current stage. `floor` is the highest reached stage's start from
「熟悉」 up (20/40/60/80), or null before any such stage; a 「陌生」 role may
fall negative, while decay never makes affection negative. Consumers must handle
all seven stages (#710/#717, #749/#751, #748/#754).

#### External turns, message supplements and terminal chat events

`external_turns` adds `ctx.external_turns.submit(ExternalTurnMessage(...))` and
`ExternalTurnResult` (`replied` with text, `busy`, `duplicate`) plus
`FakeExternalTurns`. It runs a non-channel source message as the role's external
context group turn in that conversation's thread, never queues or sends to a
channel, and disallows desktop/running-channel platform identities; role-session
interrupt does not cancel it (#721/#726). See [external turns](#runtime-api-311-external-turns).

`message_push.execute(..., push_proactive=False)` records supplemental text/images
as non-proactive, without desktop presence/awaiting-reply/relationship cooldown
updates. The strict boolean defaults to true and comes only from host execution
context, never model arguments/schema. False with a nonblank `file` is rejected
before sending; old callers/senders retain behavior (#740/#743).

`chat.cancelled` (`{session_key, turn_id}`) ends desktop turns cancelled by
`chat.cancel` or bridge shutdown. While connected, each accepted turn has exactly
one terminal event: `chat.done`, `chat.error` or `chat.cancelled`. A turn-id cancel
persists partial output and emits `session.updated` first. The SDK exports
`chatTerminalEventMethods`, `isChatTerminalEvent` and `ChatTerminalEventMethod`
(#734/#738).

#### Channel attachment tools and bounded HTTP

`ChannelPluginContext.tools` allows channels declaring `tools` to register scoped
tools. `ToolAttachmentScope(channel, paths)` and `TOOL_ATTACHMENT_SCOPE_KEY`
carry the host-created immutable snapshot of the current turn's received and
explicitly quoted attachments. Consumers must protect the key using
`Tool.context_precedence`, reject missing scope, and enforce channel/file policy.
`TEXT_ATTACHMENT_TOOL_KEY` selects a plugin-owned inbound reader hint without
granting access (default: `read_file`). `with_reply_quote` distinguishes quoted
files from images and preserves mixed attachment order (#756/#757).

`HttpGet.get` / `ChannelHttp.request` accept `max_response_bytes`: a nonnegative
cap checks Content-Length and streamed decoded bytes, including redirects,
closes oversized responses without retry and raises `ResponseTooLarge` with
`max_response_bytes`. Omitting the cap preserves behavior; HTTP fakes implement
the same contract (#756/#757).

2.2 and 2.3 first ship together in the release that turns every external
channel into a plugin (#363): no released host advertises 2.2 alone, and
`uses_bot_commands` joined 2.3 before any host advertising 2.3 was released.

## Runtime API 2.1 communication

API 2.1 adds injected renderer `client.events.on(localName, handler)`,
`client.dependency(pluginId)` and `client.background.call(localName, payload)`
alongside the existing `client.call`. Dependency IDs use the manifest's existing
strong/optional lists. Missing or inactive optional peers return `null`; retained
peers and calls from retired contexts fail with `plugin_unavailable`. The same
local names are used for self and declared peers. Background setup registers
awaitable methods with `ctx.rpc.handle`; `ctx.events` is plugin-local and
`ctx.hostEvents` explicitly subscribes to host events.

Components must renew subscription effects when their injected `client` changes.
The host replaces contexts on a real runtime publication or bridge restart, and
only the named plugins' contexts on `plugins.reloaded` (in-generation reload),
reclaims methods/listeners/pending requests on teardown, renderer failure, and
main-frame document reload/navigation. Document ownership tokens prevent delayed
cleanup from touching successor registrations; in-page/subframe navigation leaves
contexts intact. `runtime.applied.changed` means a new runtime generation was
published, independently of the idempotent RPC response's historical `changed`
value. Same-generation retries, no-op saves, and role-only writes emit refresh
events with `changed: false`; retries from retired generations emit no event.
These refreshes leave communication contexts intact. Renderer activation reports
emit `plugins.changed` with `generation`, `plugin_id`, and `kind` when readiness or
failure changes the roster. All windows refresh availability, but unchanged ACTIVE
plugins keep their communication contexts and background scopes. Failed plugins
still lose their UI, background, and surface resources. Background hosts subscribe
before their initial asynchronous reconcile, preserving publications during setup.
Background request waits are
bounded and do not occupy backend RPC scheduling capacity. Method policies on
backend calls are unchanged. See [the plugin tutorial](plugins-tutorial.md#桌面-rpc事件与-ui)
for examples and delivery/error semantics. Packages using these additions must
require `runtime_api: ">=3.0.0 <4.0.0"`; the existing `client.call` signature and
Python exported dependency API remain compatible. This is cooperation under the
existing trust model, not a sandbox; the CSP and resource grants are unchanged.

## Runtime API 2.2 channel declarations

API 2.2 adds the optional top-level `channels` list. Each entry declares one
external chat channel the plugin may contribute through `ctx.channels.add`:

```yaml
capabilities: [config, channels]
channels:
  - name: qq                         # required, [a-z][a-z0-9_-]{0,63}
    label: QQ（NapCat）               # required, display name
    contact_label: QQ 号              # optional, names member IDs in a group binding's blacklist
    group_listening: true            # optional since 2.13, boolean: groups can be listened to
    chat_types:                      # required since 2.5, nonempty
      - type: private                # required, private | group, unique per channel
        label: 私聊                   # required, type picker label
        chat_id_label: QQ 号          # required, number field label
        chat_id_hint: 对方的 QQ 号     # optional, number field placeholder
      - type: group
        label: 群聊
        chat_id_label: 群号
        chat_id_hint: QQ 群号
        prefix: 'gqq:'               # optional, prepended to the number
```

Values must be nonempty strings (`group_listening` is a boolean); unknown keys,
duplicate names, the host-owned `desktop` name and declarations without the
`channels` capability are rejected.

Since API 2.13 an entry may declare `group_listening: true`: the plugin passes
every group message to `route_account_inbound`, not only those that @ or reply
to the account, with the text already cleaned of platform codes (the host keeps
it as is). The host then offers listening for that channel's groups: a group the
user (or the role) turns listening on for keeps its unaddressed messages in
separate listening records, which start no turn (#538). Channels without the
declaration show no listening switch. `channels.list` rows carry
`group_listening: true` only when declared.

Since API 2.5 every entry must declare `chat_types`; an entry without it is
rejected, and the 2.2 channel-level `chat_id_label` / `chat_id_hint` keys are no
longer accepted (the number copy comes from each type). The role binding form
offers a type picker and a number field and composes the stored `chat_id` as
`prefix + number`. Prefixes carry no surrounding whitespace, and no prefix may
start another of the same channel. Saving a binding is rejected when its type is
not declared, when the type declares a prefix the `chat_id` does not carry
(followed by a number), or when the `chat_id` carries another type's prefix.
Every role binding stores its `chat_type`. A saved binding on a channel no
installed plugin declares (its plugin was uninstalled) is shown read-only and
kept as is, but cannot be added or changed. Packages declaring `channels` must
require `runtime_api: ">=3.0.0 <4.0.0"`.

The declaration is static, so the desktop can list a channel while its plugin is
disabled, untrusted or still missing credentials. The channel name is a data key
of role bindings and conversation threads and must stay stable across releases.

An entry may also declare an optional `instance_prefix` (a nonempty string that
starts with `<name>_`, e.g. Telegram's `telegram_`): per-account connections may
then use generated transport names `<instance_prefix><suffix>`, which share the
entry's `chat_types` and `group_listening`. `channels.list` adds one row per such
contributed instance of an enabled, `ACTIVE` plugin.

At runtime `ctx.channels.add(channel)` only accepts a `channel.name` declared by
the same manifest, a name under a declared `instance_prefix`, or an account
instance named `<declared name>:<suffix>` whose channel carries a nonempty
`account_id`. Any other name raises during setup, so the plugin rolls back
to `FAILED` with diagnostic code `undeclared_channel` (stage `setup`, field
`channels`). When two plugins declare the same channel name, or one plugin's
`instance_prefix` overlaps another plugin's channel name or prefix, discovery
marks every claimant `CONFLICT` (code `duplicate_channel`, field `channels`) and
none of them activates; candidates that already conflict by plugin ID keep
`duplicate_id`.
Packages using `channels` must require `runtime_api: ">=3.0.0 <4.0.0"`; older
hosts reject the unknown top-level key.

`plugins.list` rows carry the manifest's `capabilities` and `channels`. The
read-only bridge method `channels.list` returns `{channels: [...]}`: the
host-owned `desktop` first, then every declared plugin channel (every external
channel is a plugin). Each row has the declaration fields plus `plugin_id` (`null`
only for `desktop`), `plugin_enabled`, `state`, `error` and `status`. `state` is `active`,
`not_configured` (enabled but nothing contributed, usually missing credentials),
`failed` (construction, start or `status()` failed, or the plugin itself did not
activate; `error` keeps the cause) or `plugin_disabled`. A channel may implement
an optional `status()` returning `{connected, account?, detail?}`; `status` is
that value for an active channel and `null` otherwise. Changes follow the existing
`runtime.applied` broadcast for configuration publication and `plugins.changed`
for renderer activation outcomes; there is no separate channel event.

## Runtime API 2.3 channel hooks

API 2.3 replaces the host's channel-name checks with optional hooks on the
channel object. The core resolves a hook by channel name against the published
connections (a draining, retired connection still answers for its own replies);
an absent hook yields the neutral default. Protocols live in
`shiori_sdk.channels`:

| Hook | Effect | Default |
| --- | --- | --- |
| `supports_stream_events(chat_id) -> bool` | turns for this chat publish `StreamDeltaReady` | no stream events |
| `system_prompt_hint(chat_id) -> str` | Markdown appended after a blank line at the end of the system prompt | nothing appended |
| `default_chat_type: str` | `chat_type` the hub assigns when inbound metadata has none | `"unknown"` |
| `uses_bot_commands: bool` | the channel reads `ctx.bot_commands` at start; the host folds the command list into its `configuration_key` reuse check, so a command change rebuilds it | `False`: command changes keep the connection |

`desktop` stays host-owned: role-owned `role:<id>` desktop sessions always
stream. Packages using the hooks must require `runtime_api: ">=3.0.0 <4.0.0"`:
older hosts ignore them. (`ChannelContext.push_tool` and its
`register_channel(..., description=...)`, also introduced in 2.3, were removed
by #847; see the [3.1.2 release batch](#312-release-batch).)

## Runtime API 2.4 host feedback and inline errors

API 2.4 opens two host presentation pieces to plugin UIs, so a plugin's
failures read like the host's and can be fronted by the host mascot 吟风:

- Every bound component (`navPage.component` and `sidebar`, a custom
  `settingsSection.component`, `roleAssets.component`) now receives the host
  services as a `host` prop next to `client` (`PluginInjectedProps`, exported
  by `@yinfengwindy/shiori-sdk` since 2.9). Bundled source plugins may keep using the
  `usePluginHostServices()` context; a precompiled external package, which
  cannot import the host's React context, uses the prop.
- `host.feedback.{success,info,warning,error}(message, options?)` queues a
  toast in the host's single toaster. `options` is `{ detail?, action?,
  persona?, personaQuiet? }`: `detail` folds behind 「详情」, `action` is
  `{ label, onSelect }`, and `personaQuiet: true` shows only her face (with the
  persona's expression) when the plugin already shows the same line on screen —
  NovelAI sets it while its failure card is visible.
- `host.ui.ConfirmDialog` is the host's confirmation dialog: the same props as
  the host's own (`open`, `title`, `description`, `confirmLabel`, `children?`,
  `busy?`, `busyLabel?`, `cancelLabel?`, `error?`, `destructive?`,
  `finalFocus?`, `onClose`, `onConfirm`) plus `persona?`.
- `host.ui.InlineError` is the host's in-page error block. Props:
  `message` (required), `title?`, `detail?`, `actions?` (React nodes),
  `layout?: "row" | "strip" | "card"`, `glyph?` / `glyphTone?: "danger" |
  "accent"` (the plain glyph), `role?: "alert" | "status"`, `onDismiss?`,
  `persona?`, `className?`, `testId?`.
- `host.ui.SettingsSavedStatus` (runtime API 3.1.1) publishes the host's
  「正在保存…」/「已保存」 mark in the settings page corner, exactly as the schema
  plugin config page does. Props: `phase` (`DraftSavePhase`, usually
  `usePrivateAutosave().savePhase`). It renders nothing outside a settings page.
- For `account.detail` contributions `host.ui` also offers
  `AccountStatusCard` (one account's status with its single connect/disconnect
  button and plugin rows below), `AccountDetailActions` (secondary actions in
  the account danger zone next to 删除账号) and `Reveal` (fade + height
  show/hide for rows such as a QR code). The other members of `host` are
  `onEvent` (every desktop bridge event), `listRoles`, `pickImages`,
  `pickFiles` (native selection copied into private staging under a
  `namespace`), the 3.1.1 path pickers, `config` and `assets` (2.10). The SDK's
  `PluginHostServices` / `PluginHostUi` types are the complete list.

`persona` is `boolean | "generic" | PersonaSceneKey` and defaults to `false`: a
plugin opts in per call. `true` / `"generic"` select the surface's own generic
line and face (toast: error / warning a line, success / info only her face;
inline error: the generic inline-error line; confirmation: the generic line for
a destructive or an ordinary confirmation). A scene key selects the host's line
for that scene: `not_configured`, `unauthorized`, `quota`, `network`,
`upstream` (failures), `destructive`, `discard`, `confirm` (confirmations);
the table is `personaSceneLines` in `shared/mascot/mascotLines.ts`, and an
unknown key is a type error. The lines are always host-written: a plugin picks
a scene, never a sentence. The user's 设置 › 外观 › 看板娘 switch always
wins — with it off, opted-in toasts and blocks render plain, exactly like
`persona: false`. Nothing else about toasts changes: the queue, durations,
deduplication and the bridge-offline filter are shared with the host.

```tsx
function Page({ client, host }: PluginNavPageComponentProps) {
  const [error, setError] = useState("");
  const load = () => client.call("list").catch((cause: unknown) => {
    host.feedback.error("加载失败", { detail: String(cause), persona: true });
    setError(String(cause));
  });
  return error ? <host.ui.InlineError persona message={error} actions={<button onClick={load}>重试</button>} /> : null;
}
```

Packages that use `host` must require `runtime_api: ">=3.0.0 <4.0.0"`; older
hosts do not inject it. The bundled NovelAI studio uses all three: its
generation failure card and error toasts pick the scene from the backend's
stable error codes (`novelai_not_configured` → `not_configured`, …), and its
prompt-library delete confirmation is `host.ui.ConfirmDialog` with
`persona="destructive"`.

## Tools in external contexts (#489)

A turn in an external context (group chats, private chats with someone who is
not a bound user) whose sender is not the bound user may only use tools that
were registered as allowed there. `ctx.tools.register(tool, ...,
external_allowed=True)` is that declaration; the default is `False`, so a plugin
tool that does not declare it is unavailable in such turns. Messages from the
bound user themselves are never restricted, even in a group.

Restricted tools are left out of the tool schemas sent to the model and out of
`tool_search` results, `tool_search` cannot unlock them, and a call that still
reaches one is rejected with a tool result telling the model only its user can
ask for it. The declaration is read from the registry on every check, so a tool
registered mid-turn without the declaration is excluded as well. MCP tools are
dynamic and can never be declared: registering one with `external_allowed=True`
raises. Declare it only for tools that are safe for strangers to trigger; the
bundled NovelAI `generate_image` does, while commands, files, desktop, browser,
outbound messages, schedule changes and memory stay undeclared.

Packages that pass `external_allowed` must require
`runtime_api: ">=3.0.0 <4.0.0"`; older hosts reject the keyword.

This is a behavior change of 2.7.0 hosts: every plugin tool that does not
declare `external_allowed` is unavailable in restricted external-context turns,
including tools of existing packages that require an older `runtime_api` and
therefore cannot declare it. The registration API itself is unchanged for them;
this is host policy, not an API break. Such packages keep working everywhere
else, and their tools become available in those turns once they declare
`external_allowed=True` and require `runtime_api: ">=3.0.0 <4.0.0"`.

## Runtime API 3.1.1 external turns

A plugin that receives messages from a source that is not a channel account
(the desktop pet's live-stream chat, #292) declares `external_turns` and submits
each message it wants answered through `ctx.external_turns.submit(...)`. The host
routes it through the same thread creation, projection and role execution context
as channel account intake (`core/channels/role_routing.py`), with group-chat
semantics: the conversation is the role's external thread
`thread:<role>:<platform>:<conversation_id>`, named by `conversation_title` in the
phone's conversation list, and the sender (keyed by `platform` + `sender_id` for
member profiles) is never the bound user, so the turn sees only that thread's
history and external memory and is limited to the external tool whitelist. The
message and the reply are stored in that thread and take part in external memory
consolidation; they never appear in the desktop conversation.

User turns come first at gate entry. The turn takes the role's turn gate only when
no other role work holds or awaits it; otherwise `busy` returns at once, and since
the message is routed only after the gate is taken, no thread, contact name or
message is created or changed. Once an external turn holds the gate it runs to the
end: desktop or channel turns arriving meanwhile wait for it like for any other
role work (external turns are meant to be short, such as a live-chat reply).
It does not pass through the channel inbound queue and never dispatches outbound:
the plugin owns presenting the returned reply. The turn is not the role session's
interruptible turn, so desktop or channel interrupts never reach it and it never
writes into their interrupt state; cancelling the `submit` call cancels it. The
host checks only that the role exists and that `platform` is neither `desktop` nor
a running channel; the plugin is trusted to submit for the roles it serves.

## Runtime API 2.8 plugin SDK peer

API 2.8 adds `@yinfengwindy/shiori-sdk` as a renderer peer next to React. It is the
public renderer contract between plugins and the host (#440): contract types
and, from 2.9 on, the shared components, style class names and pure
helpers plugins may use. A precompiled package externalizes `@yinfengwindy/shiori-sdk`
exactly like `react`; the renderer import map resolves it to a host-served
wrapper around the **host's own instance**, so `instanceof` checks and shared
state behave exactly as they do for built-in plugins. The SDK is not a
`peer_dependencies` entry: it is versioned by the runtime API, so a package using
it declares `runtime_api: ">=3.0.0 <4.0.0"` (the unified SDK major).

The runtime exports are exactly those listed for `@yinfengwindy/shiori-sdk` in the
renderer peer ABI (`pluginUiPeerExports` in
`apps/desktop/src/plugins/uiContract.ts`); at 2.8.0 they are `BridgeError` and
`PluginBridgeError` (2.9.0 adds the primitives below). Type-only exports (such as `PluginRpcClient`, the type of
the injected `client`) have no runtime presence. Adding an export is a contract
change recorded under Unreleased and assigned a version with its release batch
(see the version history above).

The `@yinfengwindy/shiori-sdk/testing` subpath is development-only test support. It is
**not** part of the runtime API or the import map; production renderer code must
not import it. The `@yinfengwindy/shiori-sdk/contract` subpath is a type-only,
React- and DOM-free view of contract types for host code compiled outside the
renderer (main process, preload); it has no runtime presence, is not in the
import map, and plugins import the same types from the main entry. The
`@yinfengwindy/shiori-sdk/host-internal` subpath is host-only and **not** part of the
plugin contract: it is not in the peer ABI or the import map, and plugin
renderer code is barred from importing it.

## Runtime API 2.9 plugin SDK primitives

API 2.9 moves the shared renderer primitives that plugins use into
`@yinfengwindy/shiori-sdk`, which now owns their only implementation (the host
imports them from the SDK too, so host and plugins render the same components
and class names). A precompiled package that imports any of the exports below
declares `runtime_api: ">=3.0.0 <4.0.0"`; on a 2.8 host those names are missing
from the served peer wrapper and the package fails to load.

Runtime exports added in 2.9.0 (all are listed in `pluginUiPeerExports`):

| Group | Exports |
| --- | --- |
| Helpers and hooks | `errorMessage`, `useLatestRef`, `roleToggleStatus`, `accountOnline`, `useAccountAction` |
| Class names | `cx`, `cardClass`, `badgeClass`, `inputClass`, `textareaClass`, `pressableClass`, `compactPressableClass`, `primaryButtonSurfaceClass`, `ghostButtonSurfaceClass`, `ghostButtonClass`, `compactButtonSizeClass`, `compactGhostButtonClass`, `iconButtonClass`, `secondarySidebarSurfaceClass`, `secondarySidebarShellClass` (3.1.2), `sidebarNavItemClass`, `sidebarContentMotionClass`, `menuPanelClass`, `menuSeparatorClass` |
| Components | `Select`, `ActionMenu`, `AutosizeTextarea`, `SettingsToggleCard`, `RoleCapabilityCard` |
| Icons | `UploadIcon`, `SparkleIcon`, `PetalIcon`, `withMotif`, `navMotifs` |

The class names are Tailwind utility strings resolved against the host's
stylesheet; an external package's own CSS does not need to repeat them.

Type-only exports added in 2.9.0: the UI module contract (`PluginUiModule`,
each contribution and its component props, `PluginInjectedProps`), the slot
props, `PluginRoleSettingsContribution` and `PluginChatImageActionProps`, the
host services (`PluginHostServices`, `PluginHostUi` and the props of each
`host.ui` component, `PluginHostFeedback`, `PluginPersona`,
`PersonaSceneKey`, `NativeFilePickerOptions`), the account snapshot and status
vocabulary (`AccountSnapshot`, `AccountResponseRules`, `AccountStatusView`, …),
and the role and session domain types (`RoleRecord`,
`SessionMessageUpdatePayload`, …). They describe the 2.4–2.8 behaviour
unchanged; only their source of truth moved.

## Runtime API 2.10 host services context, config and assets

API 2.10 gives plugins the stateful host capabilities they used to reach through
host source, as services instead of host stores. A precompiled package that uses
any of them declares `runtime_api: ">=3.0.0 <4.0.0"`.

Runtime exports added in 2.10.0 (listed in `pluginUiPeerExports`):

| Export | Meaning |
| --- | --- |
| `PluginHostServicesProvider` | the React context provider the host mounts every bound contribution (`settings.section` component, `nav.page` and its sidebar, `role.assets`, `account.detail`) under, with the same services object it injects as the `host` prop |
| `usePluginHostServices()` | reads those services from any component below the contribution, so deep components need not pass `host` down; throws outside a mounted contribution |

The SDK owns the context's only instance and the host imports it from the SDK,
so a precompiled plugin, whose `@yinfengwindy/shiori-sdk` import resolves to the host's
instance through the import map, reads exactly the services the host provided.
A plugin's own tests may wrap components in `PluginHostServicesProvider` with
fake services.

`PluginHostServices` gains two members (types `PluginHostConfig`,
`PluginHostAssets` and `PluginConfigValues`):

- **`host.config`** is the plugin's own config, bound when the host mounts the
  plugin: there is no plugin id to pass and no way to reach another plugin's
  config. `get()` resolves to the current values of the plugin's
  `[plugins.<id>]` table (schema defaults filled in; a `${NAME}` reference
  arrives as written, never resolved). `save(patch)` merges `patch` over the
  current top-level values, stores the result through the same validation and
  hot-apply path as the plugin's page in 设置 › 插件, and resolves to the values
  as stored; saves of one plugin run one at a time, each over what the previous
  one stored, and a value the config schema rejects fails that save with a
  `PluginBridgeError` (code `plugin_config_invalid`) and stores nothing.
  `subscribe(listener)` calls `listener` with the stored values after every
  successful save of the plugin's config, through `save` or through 设置 › 插件,
  and returns the unsubscribe function. A save through `host.config` refreshes
  an open 设置 › 插件 page of that plugin.
- **`host.assets.url(path)`** turns a local path the host handed to the plugin
  (in a bridge or RPC response) into a URL for `<img src>` or CSS, exactly as
  the host renders its own images. A path the host granted no access to yields
  the host's placeholder URL rather than throwing. `url` does not depend on
  `this` and keeps one identity while the plugin is loaded, so it can be passed
  on as a bare function (a hook argument or effect dependency). The background
  `ctx.assets.url` resolves through the same host bridge
  but answers `null` for such a path, because background code decides whether
  to show something at all.

The host store behind any of this (plugin enablement, feedback queue, registries,
appearance preferences) stays private; accounts still arrive through the
`account.detail` props and `host.ui`.

## Runtime API 3.1.1 plugin services, native resources and background chat

These are the additions of the 3.1.1 row; packages using any of them declare
`runtime_api: ">=3.1.1 <4.0.0"`. The SDK README ("Discoverable services and
speech contracts") holds the details.

- **Services.** A backend that declares the `services` capability publishes
  `ctx.services.register(service_id, contract=, label=, methods={...},
  metadata=)` (`shiori_sdk.services.ServiceProviderContext`): explicit async JSON
  methods for exactly that plugin instance's lifetime. Renderer code discovers
  them through the injected `client.services.list(contract)` (descriptors
  `{plugin_id, service_id, contract, label, metadata}`) and calls one with
  `client.services.call({plugin_id, service_id}, method, payload)`. Discovery
  needs no static dependency and grants no access to the provider's private
  RPCs; a retired provider or caller fails with `plugin_service_unavailable`,
  an unpublished method with `plugin_service_method_unavailable`, and no other
  provider is silently substituted. `shiori_sdk.voice` defines only the speech
  wire values (`shiori.asr.v1` `transcribe`, `shiori.tts.v1` `synthesize`),
  published by the bundled `sensevoice_asr` and `gpt_sovits_tts` plugins.
- **Native resources.** The background `ctx.native` offers `audio` (`devices`,
  `startCapture`, `stopCapture` → 16 kHz mono WAV, `cancelCapture`, `play`,
  `stop`; no host playback queue) and `keys` (`validate`, `register(id,
  accelerator, listener)`, `unregister`). They are bound to the background
  activation and revoked when it or its window ends.
- **Background chat.** `ctx.chat.send({role_id, content, turn_id, media})` and
  `ctx.chat.cancel({session_key, turn_id})` start and cancel a turn for a role.
  Since 3.1.1, while the bridge connection is open, every accepted turn ends
  with exactly one host event (`chatTerminalEventMethods`): `chat.done`,
  `chat.error`, or `chat.cancelled` (`{session_key, turn_id}`) when it was
  cancelled by turn id or by bridge shutdown. A turn-id cancel persists the
  partial reply and sends its `session.updated` before `chat.cancelled`. A
  bridge that dies without closing its connection delivers none of them; the
  renderer then sees `bridge.exit`.
- **Private role settings.** Use `roleSettings` capability cards and their
  settings dialog. The experimental `roleUi` contribution was removed before
  publication and is not part of the 3.1.1 contract.

## Runtime API 3.1.1 native path pickers

Besides the copying `host.pickFiles`, which is unchanged, the injected host
services offer two native dialogs that hand back what the user chose:

- **`host.pickFilePaths({ filters, multiple?, maxFileBytes })`** resolves to the
  selected files' original absolute paths. It applies `pickFiles`' selection
  policy (the same option validation and host ceilings, at most 16 files with
  `multiple`, extensions from `filters`, regular files only, each at most
  `maxFileBytes` by size on disk) but takes no `namespace`: nothing is read,
  copied into `private_runtime/imports` or granted as a media URL. The file is
  only checked at pick time and may change or disappear afterwards, so the
  plugin verifies it (size, hash, format) when it uses it. Cancel resolves to `[]`.
- **`host.pickDirectory()`** opens a directory dialog in which the user may also
  create a directory, and resolves to its absolute path, or `null` on cancel.

Neither widens the security boundary: plugins already run with the host's
privileges (see the top of this contract), and a returned path grants no host
resource — the plugin reaches it through its own backend code exactly as it
could any path. Their channels (`desktop:pick-file-paths`,
`desktop:pick-directory`) accept no path from the renderer.

## Runtime API 2.11 background failure reporting and surface/background types

API 2.11 adds one member to the `ctx` a background module's `setup(ctx)`
receives; a package that calls it declares `runtime_api: ">=3.0.0 <4.0.0"`.

- **`ctx.reportFailure(operation, error)`** records a failure the plugin
  handled but a human should still see — a fire-and-forget operation with no
  caller to throw at (a tray click, a surface command), or a step `setup`
  deliberately survives — in the host's desktop diagnostic log, the same place
  a failed `setup` itself is recorded. The background window is hidden and its
  console is out of reach, so this is the only way such a failure is found
  later. The host prefixes the entry with the plugin's id; `operation` names
  what failed (`"restore"`, `"show"`). It returns nothing; the host does not swallow a failure of the diagnostic channel itself.

It is an injected capability rather than an SDK function because it writes to
host state (the diagnostic log behind the preload bridge), and the SDK holds no
host state; like `ctx.store` and `ctx.tray` it is bound to the plugin.

There are no new runtime exports, so `pluginUiPeerExports` is unchanged. The
contract types of the other renderer contribution points move into
`@yinfengwindy/shiori-sdk` as type-only exports, describing the existing behaviour
unchanged (the host uses the same SDK types):

- `desktop.surface`: `PluginSurfaceModule` (the entry's default export),
  `PluginSurfaceContribution`, `PluginSurfaceComponentProps`, the
  self-directed `SurfaceHandle` and what it reports and accepts
  (`SurfacePlacement`, `SurfaceWorkArea`, `SurfaceExtension`,
  `SurfaceMenuItem`).
- `app.background`: `PluginBackgroundContribution` (the entry's default
  export), `BackgroundCtx` and its capabilities (`PluginBackgroundSurfaces`,
  `PluginBackgroundStore`, `PluginBackgroundTray`, `PluginBackgroundAssets`,
  `PluginBackgroundEvents`, `BackgroundEffectDispose`; since 3.1.1 also
  `PluginNativeApi` and `PluginBackgroundChat`, see
  [Runtime API 3.1.1](#runtime-api-311-plugin-services-native-resources-and-background-chat)),
  plus the surface vocabulary they use (`SurfaceSpec`, `SurfaceCreateResult`,
  `PluginBackgroundSettled`, `SurfaceSettleReason`).

The React-free ones the host's main process and preload use are also available
from `@yinfengwindy/shiori-sdk/contract`.

### Runtime API 3.0 surface interaction

`BackgroundCtx.surfaces.setInteraction(surfaceId, { roleId, available })` declares
an interaction target; `null` revokes it. The declaration is independent of opaque
retained state and plugin KV. The host combines it with its authoritative window
visibility/readiness/lifetime, so hiding, closing, reloading or crashing a surface
revokes that interaction target. Runtime API 3.1.1 removes the published 3.1.0
`SurfaceHandle.voice` gesture/state API. Speech gestures, input ownership,
provider selection and playback queues belong to the desktop-pet plugin.
The host forwards owned surface messages and manages scoped native resources.

`SurfaceHandle.onRoleActivity(listener)` exposes `SurfaceRoleActivity` with
`roleId`, `sessionKey`, `phase` (`running/review/failed/waiting`) and `notify`.
Only matching available targets receive it. A changed target receives `null` so
plugins clear prior activity and timers. Raw backend event subscription and
`window.miraDesktop`/`Window["miraDesktop"]` are not plugin surface APIs. Shape
translation is host-owned; animation state, priority and notification timing stay
with each plugin. All these types are defined once in the SDK's `surfaceInteraction`
contract and are available from the main and `/contract` entries.

### Test entry

`@yinfengwindy/shiori-sdk/testing` remains development-only: it is not in the peer ABI
or the import map, and production renderer code must not import it. It provides:

| Export | Use |
| --- | --- |
| `mountTestComponent(node, { windowGlobals })`, `changeInputValue`, `mockableWindowTimers` | a happy-dom DOM harness: each mount installs a fresh window as the global DOM and `cleanup()` restores the previous globals |
| `chooseSelectOption(label, optionLabel, index?)` | picks an option of the SDK `Select` through its visible trigger and a real pointer event |
| `deferred()` | a promise the test settles on demand |
| `createFakeHostServices(options)` | in-memory `PluginHostServices` whose calls can be asserted: `host` (pass as the prop or to the Provider), `calls` (every service call in order), `feedback` (the toasts), `uiRenders` (the props of each `host.ui` render), `config()` (the stored config), `emit(event)` (delivers a bridge event to `onEvent` listeners) and `accountDetailActionsZone()` (where `host.ui.AccountDetailActions` render). Options answer `listRoles`, `pickImages`, `pickFiles`, `pickFilePaths` (default `[]`), `pickDirectory` (default `null`), the initial `config`, `saveConfig` and `assetUrl` |
| `createFakeSurfaceHandle(overrides)` | complete injected surface fixture, including owned messages and role activity, without a host bridge |
| `createFakePluginClient(overrides)` | an injected `client` with no bridge behind it: pass the parts the component uses (usually `call`, answering by local method name); any other request rejects, `dispose` resolves |

The fake `host.ui` components are plain stand-ins: they render the text, buttons,
disabled/busy state and ARIA roles of their contract, and the account status card
uses the host's status wording, but they have no host styling, motion or 吟风;
assert a `persona` on the recorded props instead. The harness relies on Base UI
settling its DOM detection before the first mount; the desktop unit test loader
(`apps/desktop/scripts/test-unit-loader.mjs`) does this for every test process.

## Runtime API 2.12 channel avatars

API 2.12 adds the `avatars` capability, the host's cache of the platform
avatars of a channel's message senders and chats (#514). A plugin declares
`avatars` in its manifest `capabilities` and, if it is an external package,
`runtime_api: ">=3.0.0 <4.0.0"`.

An avatar is keyed by `kind` and the message's transport `channel`
(`InboundMessage.channel`):

- `"sender"` with the sender ID (`InboundMessage.sender`): the same
  「渠道 + 发送者 ID」 key as member profiles (#498), so one person has one
  avatar across the channel's groups;
- `"chat"` with the chat ID (`InboundMessage.chat_id`): a group's avatar, or
  the other person's for a private chat.

The plugin holds the platform credentials and downloads the picture; the host
decides when it is due, validates, shrinks and stores it. The capability has
one member, `refresh(kind, channel, id, fetch)`:

- It is due when there is no cached avatar or the last attempt is older than
  7 days. When due, the attempt time is recorded at once, so concurrent calls
  and the retry after a failed fetch wait until it is due again; when not due
  it does nothing and returns None.
- When due it starts a background task and returns it: `fetch()` is the
  plugin's async download, answering the picture's bytes, or None when the
  platform has no avatar (the placeholder is shown until it is due again).
  The bytes must be a PNG, JPEG, GIF or WebP of at most 1 MiB; the host
  shrinks it to a small PNG stored as its own file under the workspace, off
  the event loop.
- A failing `fetch` or a refused picture is logged as a warning and never
  reaches the caller; the cached avatar, if any, is kept.
- An unknown `kind` or a blank channel or ID raises `ValueError`.

Call `refresh` for the messages a role receives, after the host admitted them
(`route_account_inbound`), so fetching never delays delivery. Avatars are not
written to message metadata or account data; the desktop reads them through
the phone (`sender_avatar_abs` on messages, `avatar_abs` on conversation rows)
and identity (`avatar_abs`) bridge responses. After the plugin scope is
released `refresh` raises `RuntimeError` and its pending tasks are
cancelled. A bundled channel's own account avatar still goes through
`ctx.accounts.register(..., avatar_url=)`.

## Renderer artifacts and dependencies

The plugin's own build emits browser ESM, with a default export (direct or
`export { name as default }`). CommonJS, `.js` with ambiguous format, TypeScript,
JSX source, empty modules, and missing default-export declarations are rejected.
The static check verifies extension, UTF-8, a lexical default export and absence
of CommonJS loading constructs. It is **not a full JavaScript parser** and does
not prove arbitrary JS syntax, imported module graphs or exported value types.
The renderer loader must parse the complete graph and validate the exports before
activation; resulting initialization errors are `FAILED`, not successful partial
activation. Cross-renderer rollback is implemented by #262: a renderer that fails
to load an admitted `ui`/`background`/`surface` entry reports it through
`plugins.activation.report`, which rolls the whole plugin back on the backend
(`PluginKernel.fail_renderer_entry`) and emits `plugins.changed` so every other
window's next `plugins.list()` tears down its own now-stale contribution. Every
admitted entry (and `plugins.list()` row) carries an opaque `activation_token`
minted fresh whenever a plugin's handle becomes `ACTIVE`; a renderer echoes it
back with the report, and a mismatch is treated exactly like an unknown plugin.
This closes a disable/re-enable race: an abandoned load from a since-discarded
generation's handle cannot confirm or fail the plugin's *current* handle just
because the plugin id is the same.

The default exports retain the current contribution ABI:

| Entry | Default export |
| --- | --- |
| `ui` | `{ pluginId, navPage?, settingsSection?, roleAssets?, accountDetail?, roleSettings?, chatImageActions? }`, matching `PluginUiModule` |
| `background` | `{ pluginId, setup(ctx) }`, matching `PluginBackgroundContribution` |
| `surface` | `{ pluginId, surface: { component } }`, matching `PluginSurfaceModule` |

A `ui` export that declares `roleMemory` is rejected as a failed export
validation (`UI FAILED`, with a message naming the retired field). That
contribution existed only in unreleased development builds and never belonged to
a released runtime API, so its removal needs no runtime API version change. The
host renders the whole role memory page itself: a memory plugin provides only
the `roles.memory.documents`, `roles.memory.semantic.list` and
`roles.memory.semantic.detail` RPCs, and the page reads the configured memory
plugin alone.

A `ui` export that declares `roleUi` is rejected the same way (runtime API
3.1.1). Contribute role-scoped settings as a `roleSettings` card instead; a
card with `storage: "plugin"` keeps plugin-private documents in its settings
dialog with `usePrivateAutosave`.

`pluginId` must match the manifest ID. UI and surface components receive the
existing host-injected props; background setup receives the existing background
context. Code must not assume Vite globs, host source-relative imports or a host
rebuild. A source package is built in the plugin's own repository.

React and React DOM are peers, never copied into a plugin's bundle. The renderer
ABI currently guarantees `19.2.0` for both (a compatibility floor rather than
probing developer `node_modules`); a host may explicitly advertise a newer peer
version via `HostRuntimeContract`. External resolution must use the host's single
React/React DOM instances, including their public subpaths such as
`react/jsx-runtime` and `react-dom/client`. From runtime API 2.8 the
`@yinfengwindy/shiori-sdk` main entry is a peer resolved the same way; no other bare npm
runtime dependency is part of v1. Plugins may use build tools in their own repository, but must not ship
or request installation of private npm/Python runtime dependencies. CSS is shipped
by the plugin and scoped to its own classes. Relative resource references must
stay inside the package; declared `assets` are validated as required files.

Python code may use the standard library, public Runtime API, local plugin code,
and **declared, host-provided** distributions. `host_dependencies.python` uses
normalized distribution names (for example `PyYAML`, not its `yaml` import name).
The default host inventory reads installed direct production dependencies from
`shiori-agent` distribution metadata, without importing them; development-only,
bundled plugin and incidental transitive packages are not public dependency APIs.
The desktop build preserves the host's distribution metadata and dependency
versions with PyInstaller's `--recursive-copy-metadata shiori-agent`. Other frozen
hosts without that metadata must supply their build inventory explicitly.
An unavailable declared dependency is `BLOCKED`. This validator does not install
anything or attempt to discover arbitrary dynamic imports. Authors must declare
the complete external dependency set; capability/dependency declarations are API
cooperation, not isolation of malicious code.

## External source packages in the repository (#675)

`distribution: external` marks a source package for independent ZIP delivery.
The default is `builtin`; other values, including explicit null, are invalid.
Host-owned source roots skip external packages before requiring built renderer
artifacts. The desktop runtime staging step and Vite's generated UI, background
and surface imports use the same classification, so external source is absent
from the shipped host code. Changing the manifest in the dev server invalidates
those imports and reloads the page. Installed workspace packages always undergo
the existing contract, duplicate-ID and exact-content trust checks regardless of
this field. The declaration never grants trust, overrides a builtin, or installs
anything automatically. Grok Bot is bundled and default disabled since #877;
its source UI and callback client use the host's builtin build paths, while its
existing plugin ID, configuration and workspace data paths remain unchanged.
SenseVoice and GPT-SoVITS remain bundled builtin plugins (default disabled) since
#693. The build smoke and distribution tests below generate their own external
sources rather than relying on a shipped plugin to remain external.

The frozen host collects the complete SDK runtime independently of these plugin
sources, including implicit namespace directories such as `shiori_sdk.files`.
`shiori_sdk.testing` and caches are excluded. The final PyInstaller argument list
is checked against the SDK collection, and a small frozen probe in CI dynamically
imports SDK helpers from outside the repository with Python source paths removed.

From the repository root, build an external source package with:

```powershell
node scripts/build-plugin.mjs --plugin plugins/<id> --output artifacts/plugins
```

The source manifest must declare `api: 2`, `package_contract: 1`, an explicit
runtime range, version, backend entry and renderer artifacts. Source entries are
`ui/index.tsx`, `background/index.ts`, and `surface/index.tsx`; each declared kind
is compiled to its `renderer.<kind>.entry` `.mjs` path. The SDK and React remain
host peers. Imported CSS generates a sibling stylesheet (for example
`renderer/ui.css`) that must appear in that entry's `css` list; additional listed
stylesheets are copied from source. Plugins supply scoped CSS themselves.

The ZIP includes `backend/`, declared assets, README/license/notice files and
`docs/`. Development environments, hidden files, tests, bytecode and caches are
excluded. Symlinks are rejected. Archive limits match host admission (4096 files,
64 MiB uncompressed). The command does not install dependencies or models. Install
and update through the existing ZIP preview and explicit trust confirmation,
then restart; disable uses the current runtime transaction. Uninstall retains
private data unless deletion is explicitly selected and removes package code at
restart. The repository source stays excluded after removal.

`node apps/desktop/scripts/test-plugin-ui-build-smoke.mjs` proves static exclusion
using invalid external JavaScript. After `pnpm build:desktop`, run
`pnpm exec tsx --tsconfig apps/desktop/tests/plugin-ui/packaged.tsconfig.json apps/desktop/tests/plugin-ui/distribution.e2e.ts`
for the real development Electron/bridge installation, toggle, update, rollback
and uninstall flow while matching external source remains in the repository.
This is development-runtime evidence; packaged acceptance remains the separate
procedure in `packaged-plugin-acceptance.md`.

## Main-window UI loader (#213)

The desktop main window can consume `renderer.ui` as precompiled ESM and CSS at
runtime. For example, declare `entry: ui/dist/index.mjs` and
`css: [ui/dist/style.css]`; the directory name is not fixed. The plugin author
runs the build. The application carries no plugin compiler and does not invoke
the user's Node/npm installation. Externalize `react`, `react/jsx-runtime`,
`react-dom`, `react-dom/client` and (runtime API 2.8+) `@yinfengwindy/shiori-sdk` in that
build; bundle other browser libraries. An import map resolves these peers to the
same instances used by the host.

Only a unique, enabled `ACTIVE` workspace candidate receives a resource grant.
Main-process `plugins.list` responses contain the granted entry/CSS URLs alongside
the same authoritative state snapshot. Grants use `shiori-plugin:` URLs, retain
package-relative module chunks and CSS resources, and survive repeated list
requests. The resource handler rechecks package and resource realpaths, rejects
ungranted tokens and escapes, and serves only `.mjs`, `.js`, `.css`, `.png`, `.jpg`,
`.jpeg`, `.webp`, `.svg`, `.gif`, `.woff`, and `.woff2` files. Source files and
arbitrary filesystem URLs are not exposed through this protocol. CSP admits this
controlled scheme and the exact import-map hash; production adds neither
`unsafe-inline` scripts nor `unsafe-eval`.

Initial roster loading, bridge reconnection, `runtime.applied`, `plugins.changed`, `plugins.reloaded`, and plugin toggles
share one serialized refresh path. Disable/removal cleans this window's registry
entries and CSS. JavaScript module evaluation follows browser caching; replace a
plugin package and restart the application to load its new code.
Package identity and module URLs survive disable/re-enable for the app session;
changing its directory, version, or renderer declarations requires a restart.
The backend retains the approved startup file hashes, including chunks not yet
imported, and attaches them to the authoritative plugin roster. Main-process grants
first verify disk contents against those hashes; they never trust a newer local
baseline. Every resource response verifies the same hashes again. New or changed
scripts, CSS and assets are refused instead of mixing approved and unapproved content.
A failed import,
stylesheet, or export validation removes that plugin's partial UI and preserves
the original error as `UI FAILED` in plugin management and a renderer diagnostic,
then reports the failure to the backend (#262), which rolls the plugin back to
`FAILED`/`RESTART_REQUIRED` and republishes the roster. Other plugins continue
loading and are never affected by one plugin's rollback.

Workspace packages start `UNTRUSTED`. Enabled, valid, non-conflicting candidates
are prompted after the desktop workspace opens, without visiting Settings.
Disabled candidates wait until the user enables them or chooses **信任…** in
Settings → Plugins. The shared persona dialog shows the package name, version,
actual path and full host-permission disclosure. Cancel grants nothing, skips
only that candidate and is remembered for this desktop session, including
renderer refreshes and bridge reconnects. Manual retry remains available.
Confirm persists the exact approval and activates a first-time enabled candidate
in the current application through normal loading or a safe generation swap.
Trust-only confirmation preserves a disabled preference; **信任并启用** explicitly
requests enablement. Activation failures remain visible independently of the
saved grant. Invalid, conflicting or missing-artifact packages cannot be trusted.

The host atomically stores approval in `private_runtime/plugin-trust.json`, outside
plugin directories. Approval binds the candidate path and a SHA-256 identity of
the real package directory, all published filenames and bytes. Confirmation
rechecks static validation, ID conflicts and content against the displayed
fingerprint; changed or replaced candidates must be reviewed again after restart.
Any published source, manifest, JavaScript, CSS or asset change invalidates trust.
Trust does not modify the separately persisted enabled/disabled preference.
Explicit enablement during confirmation is a separate intent in the same
serialized operation. Existing startup candidates can have their dependency
diagnostics rechecked after a provider is approved, but each external dependency
requires its own grant. New directories are never admitted by that recheck.
`private_runtime/plugin-executions.json` records which external package ID and
directory has executed in the current Electron application session. Changed
executed contents require an application restart, including after a bridge
reconnect; this record is not an authorization grant.

Trust snapshots reject package-content symlinks/junctions, including contained
links, rather than expanding the approved tree through aliases. Only regular
`.pyc` and `.pyo` bytecode files are excluded; other content inside `__pycache__`
or directories with cache-like names remains fingerprinted. To keep bytecode from being
an unapproved execution path, external Python namespaces use a source-only loader:
entry and lazy relative imports compile only verified snapshot bytes. New modules,
bytecode-only modules and native extensions cannot bypass that namespace boundary.
Every settings generation rechecks the original approved fingerprint before
re-importing an external backend. Finder lifetime follows the plugin effect scope.

Manual trust and the ZIP lifecycle below share the same complete-trust disclosure.
All confirmations use the shared desktop confirmation dialog. Bundled plugins
remain host-owned and cannot be overwritten or uninstalled through these actions.

## Desktop ZIP installation, updates and removal (#216)

Settings → Plugins keeps **安装插件 ZIP** in the toolbar. Each plugin title opens
a separate details dialog, including builtin and conflicting directory candidates.
The dialog shows the current candidate's identity, version, source, description,
actual directory and diagnostics. **从 ZIP 更新** and **卸载插件** appear only in
the details of a unique, installed workspace package; builtin, conflicting,
pending, and uninstalled failed candidates cannot perform those actions.
Update trust and uninstall confirmations remain separate nested dialogs; closing
them returns to details, and closing details restores focus to the plugin title.
Online update checks and updating all plugins are deferred until a distribution
source exists (#323); there is no placeholder toolbar action. The native file picker stages ZIP files in
`private_runtime/imports/plugin-packages/`; renderer-supplied arbitrary paths are
not accepted. The picker permits at most 32 MiB compressed, while the shared ZIP
validator retains its 4,096-member / 64 MiB uncompressed limits and root-manifest
layout. Extraction performs the same static contract, entry, runtime compatibility
and declared host-dependency checks as manual discovery; it never executes code or
installs additional dependencies.

Preview returns an opaque token for the exact staged package and target directory.
The confirmation shows ID, version, prior version for updates, ZIP filename and
destination. Every install and every update requires **信任并安装** or
**信任并更新**, with explicit notice that backend and renderer receive the host's
permissions, can read/write the workspace, access the network and execute arbitrary
frontend code, and have no runtime sandbox. Cancel removes the preview without
installing, scheduling an update or granting trust. Confirmation rechecks the
displayed bytes and current target; duplicate IDs, builtin IDs and competing
confirmed operations are rejected before publication.

Confirmed operations are journaled under `private_runtime/plugin-operations/`,
outside plugin discovery. `plugins.list` exposes `pending_operation`
(`install`, `update`, `uninstall`) and `pending_version`; the page shows **待重启**.
The running generation retains its current code and activation state. The next
application launch applies operations before config loading and plugin discovery:
validated directories are renamed into `workspace/plugins/`, with the previous
directory retained for rollback until trust and journal publication finish. An
interrupted rename is recovered before any plugin can execute. A failed update
restores the old directory and its trust record, removes staged package bytes and
retains the original cause in `package_operation_error`. Restarting only the bridge
within the same desktop application session never applies a pending operation.
Updates preserve the user's existing enabled/disabled setting.

Uninstall first requests disable through the existing settings-generation
transaction so renderer, background and surface resources reconcile normally.
If the runtime or a dependent does not support hot unload, the operation waits for
application exit and final resource cleanup; it never forces a hot unload. Code
removal occurs at the following startup. The default keeps `plugin-data/<id>/`
and `[plugins.<id>]` configuration so reinstalling the same ID retains its data.
The independent, initially unchecked **同时删除插件数据** option permanently
removes both the private data directory and that plugin's config table at startup.
Inline/dotted TOML settings are normalized when necessary while preserving other
configuration values. Uninstall always revokes the removed code's trust approval,
independently of data retention; reinstall requires fresh explicit trust.

Private-directory deletion is not a complete reset of role or device content.
Opaque role namespaces in `roles/roles.json` are retained for atomic role saves;
NovelAI and desktop_pet own their respective `plugin_data.<id>` schema. Reinstalling
and reauthorizing that ID lets it read the retained role preferences. Complete
plugin backups include its private directory, configuration table, applicable role
namespace and `private_runtime/plugin-data-migrations/<id>/` receipts. Restore role
namespaces by merging their role entries without overwriting unrelated state.
Receipts survive data deletion so retained legacy sources cannot resurrect cleared
data. Device-level Story localStorage preferences and desktop_pet's
`userData/plugin-data/desktop_pet.json` require separate device backup. The
workspace `recovery/shell_restore/` stores original user files and is protected
from ordinary plugin-data deletion; explicit `AKASIC_RESTORE_DIR` and historical
`~/restore` remain separately managed and are never reassigned or moved automatically.

The bridge lifecycle methods are `plugins.install.preview` (`source`, optional
`candidate_id` for updates), `plugins.install.confirm` (`token`, `trusted: true`),
`plugins.install.cancel` (`token`), and `plugins.uninstall` (`candidate_id`,
`delete_data`, `operation_id`). They share existing management diagnostics and
roster refresh notifications. There is no store, automatic update, package-level
HMR, dependency installer or additional sandbox.

Focused Electron verification builds a separate test renderer, uses a fixture
`ACTIVE` roster, and checks actual `file://` ESM loading, shared React hooks, the
host's `@yinfengwindy/shiori-sdk` instance reached through the import map, relative chunks, CSS, failure isolation, disable/re-enable cleanup, protocol
rejection and CSP rejection. It does not prove workspace trust. Run after the
desktop main/preload build:

```powershell
pnpm exec tsx --tsconfig apps/desktop/renderer/tsconfig.json apps/desktop/tests/plugin-ui/electron.e2e.ts
```

The real workspace flow uses the production main process, preload and backend in
an isolated QA home. It verifies automatic persona confirmation, zero execution
before approval, cancellation across bridge reconnection, immediate React hooks
and RPC, remembered approval after restart, content-change approval,
and removal without residual UI, CSS or plugin errors. Screenshots are retained in
`.test-tmp-root/plugin-trust-real-*`. This uses the repository `.venv` by default;
set `SHIORI_QA_RUNTIME_EXE` to an existing frozen runtime executable to verify that
runtime with the same test bootstrap without changing production interpreter selection.

```powershell
pnpm exec tsx --tsconfig apps/desktop/renderer/tsconfig.json apps/desktop/tests/plugin-ui/trust.e2e.ts
```

## Paths, archive limits and lifecycle

Paths use canonical relative `/` segments. Absolute paths, drive/UNC paths,
backslashes, `.`/`..`, empty segments, Windows alternate data streams, reserved
device names, trailing dots/spaces and control characters are rejected on every
platform. Every declared file and `manifest.yaml` must resolve to a regular file
inside the package root; an escaping symlink/junction is rejected. Zip member
names are checked before temporary extraction, including their original spelling
before Python's Windows normalization. Archives reject links, special files,
encryption and case-colliding member paths. Limits are 4,096 members and 64 MiB
uncompressed. Validation never installs or modifies a workspace package.

Host state vocabulary extends the existing lifecycle enum:

| State | Meaning / next boundary |
| --- | --- |
| `UNTRUSTED` | manifest inspectable, no code allowed until explicit trust |
| `BLOCKED` | static contract/runtime/dependency failure, retry after correction |
| `FAILED` | import/setup or contribution initialization failed; reclaim started resources |
| `CONFLICT` | multiple candidates claim one ID or one declared channel name; select none until resolved |
| `RESTART_REQUIRED` | an accepted code-directory change awaits application restart, **or** (#262) a failed load's rollback could not fully dispose its own effects — retry is unsafe until the next application launch |
| `DISCOVERED`, `DISABLED`, `LOADING`, `ACTIVE`, `UNLOADING`, `DISPOSED` | existing runtime lifecycle |

Workspace discovery (#211) reports `UNTRUSTED` until the exact content has a valid
approval, and marks every candidate with a duplicate manifest ID `CONFLICT`.
Both states prevent execution; enabling an eligible untrusted candidate opens
the host confirmation rather than bypassing admission. `RESTART_REQUIRED`
remains the boundary for replacing code already executed in this application.
Enabled/disabled preferences remain separate from code
version/restart state. Updates must not silently re-enable disabled plugins.

Static rejection raises `PackageContractError` with `diagnostic.to_dict()`:

```json
{
  "code": "missing_file",
  "stage": "validation",
  "field": "renderer.surface.entry",
  "reason": "Original file-system error or precise contract rejection",
  "path": "renderer/surface.mjs",
  "state": "BLOCKED"
}
```

The host snapshot supplies identity, directory and lifecycle state. `code` is
machine-readable; `field` identifies the declaration, `reason` retains the cause
and `path` identifies the artifact when applicable. Kernel `states()` and
`plugins.list` retain validation diagnostics, including malformed opt-in manifest
candidates. Missing or inactive strong plugin dependencies use stage `dependency`,
field `dependencies[index]`, and code `missing_dependency` or
`dependency_unavailable`; their original dependency error is retained in `reason`.
Runtime failures retain their original `error`; they do not reuse a static
`BLOCKED` diagnostic. A passing validator alone does not mean trusted,
active or ready to run in every renderer.

## Independent example and validation

Copy `tests/fixtures/external-plugin/` to a directory outside Shiori. Its pinned
pnpm/esbuild build compiles TSX/TS into ESM, externalizes the host peers, copies its
backend/CSS/assets and produces the package root. No host npm package, Vite build,
private path or source checkout is needed to **build** it. See the fixture README
for commands and how to validate its directory/zip from a host environment.


## Runtime API 3.0: unified Shiori SDK

`@yinfengwindy/shiori-sdk` and `shiori-sdk` share one version (3.0.0 at introduction, now
3.1.1) and the source tree `packages/sdk/`. External packages must declare `runtime_api: ">=3.0.0 <4.0.0"`.
The previous frontend package name has no alias. Existing 2.x ranges are rejected
with `incompatible_runtime` before backend execution; rebuild renderer peers and
update the declared range when migrating. The 2.x sections above describe feature
history; all current examples target the unified 3.x ABI.

Before the first public release, the npm identity was finalized as the personal
scope `@yinfengwindy/shiori-sdk`. That rename retained Runtime API `3.1.0` because no
public version preceded this rename. Renderer plugins built against the earlier
internal name must update their imports and rebuild; the import map and host peer
wrappers expose only the public name, without a compatibility alias.

Python contracts, shared lifecycle values, event handler/effect types and
independent test fakes belong to `shiori_sdk`. All 22 bundled plugins consume SDK
contracts and explicitly declared dependencies: browser_use, citation, computer_use,
context_pressure, default_memory, desktop_pet, feishu, gpt_sovits_tts, meme,
novelai, observe, plugin_undo, qq, qqbot, screen_perception, sensevoice_asr,
shell_restore, shell_safety, status_commands, story, telegram and tool_loop_guard
(the 20 of #585–#591 plus the two speech providers of #678/#693).

Every plugin's backend, tests and packaged test support are guarded against host
implementation dependencies without migration exemptions. Repository-external
verification installs each target and its declared closure as ordinary wheels,
uses `shiori-sdk[testing]`, and executes the tests without the host. The SDK never
imports host or concrete plugin implementations or creates host storage. Real
AppRuntime, channel, window and process integration remains in separate host CI;
`shiori-host-testing` provides Python runtime fixtures. Memory construction,
resource handoff and typed setup capabilities are documented in
[the shared SDK guide](../../packages/sdk/README.md);
the default memory implementation and vector compatibility rules belong to its
plugin. The guide also covers installation, testing and artifact checks.


The hook/command/observation setup surfaces are `HookPluginContext`,
`CommandPluginContext` and `ObservePluginContext` in `shiori_sdk.extensions`.
Observe declares `diagnostics` and `storage` alongside events/background/workspace.
Diagnostics connects to the owning host's global handler stack and active session;
code roots are resolved from installed host packages and discovered plugin roots.
The plugin never guesses a repository root. `storage.migrate_data` uses the existing
host migration receipts and leases. These ports are part of Runtime API 3.0.

Before-turn command contributors read `CommandFrame.command` and request
`abort_command(reply)`, so abort construction/context preservation remain host-owned.
The optional Observe reader is queried through `dependencies.get_optional("observe")`
each time; availability is scoped to the active provider generation.


### SDK 3.0 role and process capabilities (#588)

Role, generation and native-tool plugins use the manifest-granted SDK
`ServicePluginContext`: `roles`, `models`, `sessions`, `http`, `resources`,
`processes`, `tool_turn`, `background` and `runtime`. The role model activation
context is held across awaits; runtime background tasks retain the current
generation. MCP and owned process cleanup remain implemented by the host,
including Windows Job ownership before execution. See the SDK README for the
small contracts and independent test fixtures. Plugin-private generation, Story
and observation policy is unchanged. Story/NovelAI and Meme/Citation remain
explicit dependencies; desktop-pet integration is tested on the host side.

### SDK 3.0 channel services (#589)

QQBot, QQ, Telegram and Feishu consume the public `ChannelPluginContext`/`ChannelContext` and SDK-only testing support. Channel values (accounts, targets, message events, declarations, session keys and message source/quotes) have one SDK definition. `ctx.intake_factory` creates host-owned admission coordination; `avatars` schedules host-owned caching, and `http` provides bounded requests. `processes.popen` exposes the synchronous counterpart to owned async spawn, preserving WindowsJob adoption before execution without moving any OS implementation into the SDK. Platform credentials, clients, reconnect/streaming, NapCat installation and QR/profile policy remain plugin-owned. Actual host construction checks these protocols with pyright.

Channel groups and identity indexes are obtained from granted services (`channels.group`, `session_manager.identity_index`); their runtime and persistence implementations remain host-owned. The SDK only declares these protocols and supplies independent fakes. Channel credential references resolve through granted `config.resolve_reference` at use time while stored credentials retain their original reference. `KeyValueStore.delete` is idempotent.


### Schema configuration autosave

The host-generated plugin schema form merges edits after 400 ms without changes.
Only one complete draft is submitted at a time; later edits replace the pending
draft and wait for both the current request and their quiet period. Leaving or
switching the form flushes its last pending draft under the original plugin ID.
Pending drafts are shown as saving, and reverting to the persisted value cancels
a save that has not started. Definite/unknown failure pauses and same-operation-ID
retries remain unchanged. `host.config.save()` retains its awaitable patch protocol
and is not debounced. Each actual configuration change still uses the full runtime
generation transaction; this optimization reduces transactions, not their scope.
