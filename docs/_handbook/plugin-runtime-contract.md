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
(#262) are separate delivery slices.

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
| `runtime_api` | yes | compatibility range; host currently advertises `2.16.0` |
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

There is one backend entry in v1. Each renderer kind may declare one entry. Every
declaration is required; there is no `optional` entry flag. A missing stylesheet,
background module or surface entry blocks the whole package before backend import.
A backend entry must be parseable Python with a top-level `async def setup` that
accepts one positional context and has no additional required arguments. The
existing injected context/capability protocol is unchanged. The external fixture
uses that context without importing host internals; public backend import
portability is completed by #212.

Ranges use whitespace-separated comparators with AND semantics: `=`, `>`, `>=`,
`<`, `<=`; a bare SemVer means equality. Example: `>=2.0.0 <3.0.0`. Caret, tilde,
wildcard, comma, OR and hyphen ranges are deliberately unsupported and rejected.
Build metadata does not affect precedence. Prerelease hosts require a comparator
mentioning a prerelease of that same major/minor/patch tuple.

## Runtime API version history

Each minor version only adds opt-in surface; a package declares the lowest
version whose additions it uses.

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
| `2.8.0` | the `@shiori/plugin-sdk` renderer peer, resolved to the host's own instance through the renderer import map (see [Runtime API 2.8 plugin SDK peer](#runtime-api-28-plugin-sdk-peer)) | #503 (#440 T1) |
| `2.9.0` | `@shiori/plugin-sdk` shared renderer primitives: components, class names, icons, pure helpers and hooks, plus the UI module, host service, account and role contract types (see [Runtime API 2.9 plugin SDK primitives](#runtime-api-29-plugin-sdk-primitives)) | #504 (#440 T2) |
| `2.10.0` | the host services context (`PluginHostServicesProvider` / `usePluginHostServices`) exported by `@shiori/plugin-sdk`, plus `host.config` (the plugin's own config: read, save a patch, subscribe) and `host.assets` (local path to displayable URL) (see [Runtime API 2.10 host services context, config and assets](#runtime-api-210-host-services-context-config-and-assets)) | #505 (#440 T3) |
| `2.11.0` | `ctx.reportFailure(operation, error)` on the background `setup(ctx)`: a handled background failure recorded in the host's desktop diagnostic log; `@shiori/plugin-sdk` also becomes the source of the `desktop.surface` and `app.background` contract types (see [Runtime API 2.11 background failure reporting and surface/background types](#runtime-api-211-background-failure-reporting-and-surfacebackground-types)) | #508 (#440) |
| `2.12.0` | the `avatars` capability: `ctx.avatars.refresh(kind, channel, id, fetch)` hands channel senders' and chats' platform avatars to a host-owned cache, released with the plugin scope (see [Runtime API 2.12 channel avatars](#runtime-api-212-channel-avatars)) | #514 |
| `2.13.0` | optional `group_listening: true` on manifest `channels` entries: the channel hands every group message to the host, so its groups offer 群聊旁听 (see [Runtime API 2.2 channel declarations](#runtime-api-22-channel-declarations)) | #538 (#527) |
| `2.14.0` | optional `on_heard=` keyword on `ctx.channel_hub.route_account_inbound`: called with the projected message only when an unaddressed group message is stored in the listening records, so a channel can refresh the avatars it shows (see channel-plugins handbook) | #553 |
| `2.15.0` | quoted messages (#555): `infra.channels.reply_context.with_reply_quote` wraps a routed message with the message it quotes (text never truncated, quoted pictures ahead of its own) and records `reply_to_content` / `reply_to_sender_name` / `reply_to_media`; the hub sets `reply_to_sender_is_user` on a routed message whose quoted sender is bound to the user (plugins cannot set it) | #555 |
| `2.16.0` | SDK `CrossfadeLayers` and `SidebarResizeHandle`; packages importing either require `runtime_api: ">=2.16.0 <3.0.0"`. The host no longer provides NcatBot; external `host_dependencies` declarations requiring it are rejected by the existing missing-dependency check. QQ uses per-account OneBot sockets; `psutil` remains a production dependency. | #576 |

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
The host replaces contexts on a real runtime publication or bridge restart,
reclaims methods/listeners/pending requests on teardown, renderer failure, and
main-frame document reload/navigation. Document ownership tokens prevent delayed
cleanup from touching successor registrations; in-page/subframe navigation leaves
contexts intact. `runtime.applied.changed` means a new runtime generation was
published, independently of the idempotent RPC response's historical `changed`
value. Same-generation retries, no-op saves, and role-only writes emit refresh
events with `changed: false`; retries from retired generations emit no event.
These refreshes leave communication contexts intact. Background request waits are
bounded and do not occupy backend RPC scheduling capacity. Method policies on
backend calls are unchanged. See [the plugin tutorial](plugins-tutorial.md#桌面-rpc事件与-ui)
for examples and delivery/error semantics. Packages using these additions must
require `runtime_api: ">=2.1.0 <3.0.0"`; the existing `client.call` signature and
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
require `runtime_api: ">=2.5.0 <3.0.0"`.

The declaration is static, so the desktop can list a channel while its plugin is
disabled, untrusted or still missing credentials. The channel name is a data key
of role bindings and conversation threads and must stay stable across releases.

At runtime `ctx.channels.add(channel)` only accepts a `channel.name` declared by
the same manifest. Any other name raises during setup, so the plugin rolls back
to `FAILED` with diagnostic code `undeclared_channel` (stage `setup`, field
`channels`). When two plugins declare the same channel name, discovery marks every
claimant `CONFLICT` (code `duplicate_channel`, field `channels`) and none of them
activates; candidates that already conflict by plugin ID keep `duplicate_id`.
Packages using `channels` must require `runtime_api: ">=2.2.0 <3.0.0"`; older
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
`runtime.applied` broadcast; there is no separate channel event.

## Runtime API 2.3 channel hooks

API 2.3 replaces the host's channel-name checks with optional hooks on the
channel object. The core resolves a hook by channel name against the published
connections (a draining, retired connection still answers for its own replies);
an absent hook yields the neutral default. Protocols live in
`infra.channels.contract`:

| Hook | Effect | Default |
| --- | --- | --- |
| `supports_stream_events(chat_id) -> bool` | turns for this chat publish `StreamDeltaReady` | no stream events |
| `system_prompt_hint(chat_id) -> str` | Markdown appended after a blank line at the end of the system prompt | nothing appended |
| `default_chat_type: str` | `chat_type` the hub assigns when inbound metadata has none | `"unknown"` |
| `uses_bot_commands: bool` | the channel reads `ctx.bot_commands` at start; the host folds the command list into its `configuration_key` reuse check, so a command change rebuilds it | `False`: command changes keep the connection |

`desktop` stays host-owned: role-owned `role:<id>` desktop sessions always
stream. `MessagePushTool.register_channel(..., description=...)` accepts a short
identity/`chat_id` format note; the `message_push` tool description lists only
currently registered, non-retired channels with those notes. Packages using the
hooks or `description` must require `runtime_api: ">=2.3.0 <3.0.0"`: older hosts
ignore the hooks and reject the unknown keyword.

## Runtime API 2.4 host feedback and inline errors

API 2.4 opens two host presentation pieces to plugin UIs, so a plugin's
failures read like the host's and can be fronted by the host mascot 吟风:

- Every bound component (`navPage.component` and `sidebar`, a custom
  `settingsSection.component`, `roleAssets.component`) now receives the host
  services as a `host` prop next to `client` (`PluginInjectedProps` in
  `pluginUiModuleContract.tsx`). Bundled source plugins may keep using the
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

Packages that use `host` must require `runtime_api: ">=2.4.0 <3.0.0"`; older
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
`runtime_api: ">=2.7.0 <3.0.0"`; older hosts reject the keyword.

This is a behavior change of 2.7.0 hosts: every plugin tool that does not
declare `external_allowed` is unavailable in restricted external-context turns,
including tools of existing packages that require an older `runtime_api` and
therefore cannot declare it. The registration API itself is unchanged for them;
this is host policy, not an API break. Such packages keep working everywhere
else, and their tools become available in those turns once they declare
`external_allowed=True` and require `runtime_api: ">=2.7.0 <3.0.0"`.

## Runtime API 2.8 plugin SDK peer

API 2.8 adds `@shiori/plugin-sdk` as a renderer peer next to React. It is the
public renderer contract between plugins and the host (#440): contract types
and, from 2.9 on, the shared components, style class names and pure
helpers plugins may use. A precompiled package externalizes `@shiori/plugin-sdk`
exactly like `react`; the renderer import map resolves it to a host-served
wrapper around the **host's own instance**, so `instanceof` checks and shared
state behave exactly as they do for built-in plugins. The SDK is not a
`peer_dependencies` entry: it is versioned by the runtime API, so a package using
it declares `runtime_api: ">=2.8.0 <3.0.0"` (or the lowest 2.x minor whose SDK
exports it uses).

The runtime exports are exactly those listed for `@shiori/plugin-sdk` in the
renderer peer ABI (`pluginUiPeerExports` in
`apps/desktop/src/plugins/uiContract.ts`); at 2.8.0 they are `BridgeError` and
`PluginBridgeError` (2.9.0 adds the primitives below). Type-only exports (such as `PluginRpcClient`, the type of
the injected `client`) have no runtime presence. Adding an export is a new
minor version.

The `@shiori/plugin-sdk/testing` subpath is development-only test support. It is
**not** part of the runtime API or the import map; production renderer code must
not import it. The `@shiori/plugin-sdk/contract` subpath is a type-only,
React- and DOM-free view of contract types for host code compiled outside the
renderer (main process, preload); it has no runtime presence, is not in the
import map, and plugins import the same types from the main entry. The
`@shiori/plugin-sdk/host-internal` subpath is host-only and **not** part of the
plugin contract: it is not in the peer ABI or the import map, and plugin
renderer code is barred from importing it.

## Runtime API 2.9 plugin SDK primitives

API 2.9 moves the shared renderer primitives that plugins use into
`@shiori/plugin-sdk`, which now owns their only implementation (the host
imports them from the SDK too, so host and plugins render the same components
and class names). A precompiled package that imports any of the exports below
declares `runtime_api: ">=2.9.0 <3.0.0"`; on a 2.8 host those names are missing
from the served peer wrapper and the package fails to load.

Runtime exports added in 2.9.0 (all are listed in `pluginUiPeerExports`):

| Group | Exports |
| --- | --- |
| Helpers and hooks | `errorMessage`, `useLatestRef`, `roleToggleStatus`, `accountOnline`, `useAccountAction` |
| Class names | `cx`, `cardClass`, `badgeClass`, `inputClass`, `textareaClass`, `pressableClass`, `compactPressableClass`, `primaryButtonSurfaceClass`, `ghostButtonSurfaceClass`, `ghostButtonClass`, `compactButtonSizeClass`, `compactGhostButtonClass`, `iconButtonClass`, `secondarySidebarSurfaceClass`, `sidebarNavItemClass`, `sidebarContentMotionClass`, `menuPanelClass`, `menuSeparatorClass` |
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
any of them declares `runtime_api: ">=2.10.0 <3.0.0"`.

Runtime exports added in 2.10.0 (listed in `pluginUiPeerExports`):

| Export | Meaning |
| --- | --- |
| `PluginHostServicesProvider` | the React context provider the host mounts every bound contribution (`settings.section` component, `nav.page` and its sidebar, `role.assets`, `account.detail`) under, with the same services object it injects as the `host` prop |
| `usePluginHostServices()` | reads those services from any component below the contribution, so deep components need not pass `host` down; throws outside a mounted contribution |

The SDK owns the context's only instance and the host imports it from the SDK,
so a precompiled plugin, whose `@shiori/plugin-sdk` import resolves to the host's
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

## Runtime API 2.11 background failure reporting and surface/background types

API 2.11 adds one member to the `ctx` a background module's `setup(ctx)`
receives; a package that calls it declares `runtime_api: ">=2.11.0 <3.0.0"`.

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
`@shiori/plugin-sdk` as type-only exports, describing the existing behaviour
unchanged (the host uses the same SDK types):

- `desktop.surface`: `PluginSurfaceModule` (the entry's default export),
  `PluginSurfaceContribution`, `PluginSurfaceComponentProps`, the
  self-directed `SurfaceHandle` and what it reports and accepts
  (`SurfacePlacement`, `SurfaceWorkArea`, `SurfaceExtension`,
  `SurfaceMenuItem`).
- `app.background`: `PluginBackgroundContribution` (the entry's default
  export), `BackgroundCtx` and its capabilities (`PluginBackgroundSurfaces`,
  `PluginBackgroundStore`, `PluginBackgroundTray`, `PluginBackgroundAssets`,
  `PluginBackgroundEvents`, `BackgroundEffectDispose`), plus the surface
  vocabulary they use (`SurfaceSpec`, `SurfaceCreateResult`,
  `PluginBackgroundSettled`, `SurfaceSettleReason`).
- `VoiceStatePayload`, the host's voice state pushed to the desktop pet.

The React-free ones the host's main process and preload use are also available
from `@shiori/plugin-sdk/contract`.

### Test entry

`@shiori/plugin-sdk/testing` remains development-only: it is not in the peer ABI
or the import map, and production renderer code must not import it. It provides:

| Export | Use |
| --- | --- |
| `mountTestComponent(node, { windowGlobals })`, `changeInputValue`, `mockableWindowTimers` | a happy-dom DOM harness: each mount installs a fresh window as the global DOM and `cleanup()` restores the previous globals |
| `chooseSelectOption(label, optionLabel, index?)` | picks an option of the SDK `Select` through its visible trigger and a real pointer event |
| `deferred()` | a promise the test settles on demand |
| `createFakeHostServices(options)` | in-memory `PluginHostServices` whose calls can be asserted: `host` (pass as the prop or to the Provider), `calls` (every service call in order), `feedback` (the toasts), `uiRenders` (the props of each `host.ui` render), `config()` (the stored config), `emit(event)` (delivers a bridge event to `onEvent` listeners) and `accountDetailActionsZone()` (where `host.ui.AccountDetailActions` render). Options answer `listRoles`, `pickImages`, `pickFiles`, the initial `config`, `saveConfig` and `assetUrl` |
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
`runtime_api: ">=2.12.0 <3.0.0"`.

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
(`PluginKernel.fail_renderer_entry`) and republishes the roster so every other
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
| `ui` | `{ pluginId, navPage?, settingsSection?, roleAssets?, roleSettings?, chatImageActions? }`, matching `PluginUiModule` |
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
`@shiori/plugin-sdk` main entry is a peer resolved the same way; no other bare npm
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

## Main-window UI loader (#213)

The desktop main window can consume `renderer.ui` as precompiled ESM and CSS at
runtime. For example, declare `entry: ui/dist/index.mjs` and
`css: [ui/dist/style.css]`; the directory name is not fixed. The plugin author
runs the build. The application carries no plugin compiler and does not invoke
the user's Node/npm installation. Externalize `react`, `react/jsx-runtime`,
`react-dom`, `react-dom/client` and (runtime API 2.8+) `@shiori/plugin-sdk` in that
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

Initial roster loading, bridge reconnection, `runtime.applied`, and plugin toggles
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

Workspace packages start `UNTRUSTED`. Settings → Plugins offers **信任…** only for
valid, non-conflicting packages. The dialog shows the package name, version and
actual path, and explicitly warns that plugin code receives the same permissions
as Shiori. Cancel writes nothing. Confirm persists approval and displays **待重启**;
only the next application launch can activate it. Restarting the bridge within
the same desktop session does not activate a newly approved package.

The host atomically stores approval in `private_runtime/plugin-trust.json`, outside
plugin directories. Approval binds the candidate path and a SHA-256 identity of
the real package directory, all published filenames and bytes. Confirmation
rechecks static validation, ID conflicts and content against the displayed
fingerprint; changed or replaced candidates must be reviewed again after restart.
Any published source, manifest, JavaScript, CSS or asset change invalidates trust.
Trust does not modify the separately persisted enabled/disabled preference.

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
host's `@shiori/plugin-sdk` instance reached through the import map, relative chunks, CSS, failure isolation, disable/re-enable cleanup, protocol
rejection and CSP rejection. It does not prove workspace trust. Run after the
desktop main/preload build:

```powershell
pnpm exec tsx --tsconfig apps/desktop/renderer/tsconfig.json apps/desktop/tests/plugin-ui/electron.e2e.ts
```

The real workspace flow uses the production main process, preload and backend in
an isolated QA home. It verifies cancel, confirmation, pending status across bridge
reconnection, app restart activation, React hooks and RPC, content-change approval,
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
approval from a previous app session, and marks every candidate with a duplicate
manifest ID `CONFLICT`. Both states prevent execution and enable actions.
`RESTART_REQUIRED` remains the code-change boundary for downstream hosts; manual
approval exposes a separate pending-restart flag while backend state stays untrusted.
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
