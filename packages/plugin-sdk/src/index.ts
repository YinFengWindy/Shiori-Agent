/**
 * `@shiori/plugin-sdk`: the renderer contract between plugins and the Shiori
 * desktop host (#440).
 *
 * At runtime this entry is a host peer, like React: every value exported here
 * must also be listed in the renderer peer ABI
 * (`pluginUiPeerExports["@shiori/plugin-sdk"]` in
 * `apps/desktop/src/plugins/uiContract.ts`), and changing that list is a
 * runtime API change. This package must never import host source. Host-only
 * internals shared with the SDK live in `./hostInternal.ts`
 * (`@shiori/plugin-sdk/host-internal`), outside the plugin contract.
 */

// Errors and the injected RPC client (runtime API 2.8.0).
export { BridgeError, PluginBridgeError } from "./errors";
export type { BridgeEvent, PluginBackgroundHandler, PluginEventHandler, PluginPeer, PluginRpcClient } from "./rpc";

// From here to the 2.10.0 block below: runtime API 2.9.0 (#504).

// Pure helpers and hooks.
export { errorMessage } from "./errors";
export { useLatestRef } from "./useLatestRef";
export { roleToggleStatus, type RoleCapabilityStatus, type RoleCapabilityTone } from "./roleCapability";
export {
  accountOnline,
  type AccountPendingAction,
  type AccountResponseRules,
  type AccountSnapshot,
  type AccountStatusTone,
  type AccountStatusView,
} from "./account/account";
export { useAccountAction } from "./account/useAccountAction";

// Shared class names.
export {
  badgeClass,
  cardClass,
  compactButtonSizeClass,
  compactGhostButtonClass,
  compactPressableClass,
  cx,
  ghostButtonClass,
  ghostButtonSurfaceClass,
  iconButtonClass,
  inputClass,
  pressableClass,
  primaryButtonSurfaceClass,
  secondarySidebarSurfaceClass,
  sidebarContentMotionClass,
  sidebarNavItemClass,
  textareaClass,
} from "./styles";
export { menuPanelClass, menuSeparatorClass } from "./menuStyles";

// Components.
export { ActionMenu, type ActionMenuItem } from "./components/ActionMenu";
export { AutosizeTextarea } from "./components/AutosizeTextarea";
export { RoleCapabilityCard } from "./components/RoleCapabilityCard";
export { Select, type SelectOption, type SelectProps } from "./components/Select";
export { SettingsToggleCard } from "./components/SettingsToggleCard";

// Icons.
export type { IconProps } from "./icons/types";
export { UploadIcon } from "./icons/UploadIcon";
export { PetalIcon, SparkleIcon } from "./icons/brand";
export { navMotifs, withMotif, type NavGlyphMotion } from "./icons/navGlyphs";

// Domain types.
export type {
  LonelinessRuntime,
  RelationshipSnapshot,
  RoleAssetCategory,
  RoleLastMessage,
  RoleProactiveCandidate,
  RoleProactiveConfig,
  RoleRecord,
} from "./domain/role";
export type {
  ChatImageHistoryEntry,
  ChatToolCall,
  ChatToolCallGroup,
  SessionMessage,
  SessionMessagePage,
  SessionMessageUpdatePayload,
  SessionPaginationState,
  SessionPayload,
  SessionSummary,
} from "./domain/session";

// Contract types: host services, slot props and the UI module.
export type {
  FeedbackAction,
  FeedbackTone,
  PersonaSceneKey,
  PluginFeedbackOptions,
  PluginHostFeedback,
  PluginPersona,
} from "./contract/feedback";
export type {
  AccountDetailAction,
  AccountDetailActionsProps,
  AccountStatusCardAction,
  AccountStatusCardProps,
  HostConfirmDialogProps,
  HostInlineErrorProps,
  PluginHostUi,
  RevealProps,
} from "./contract/hostUi";
export type { NativeFilePickerOptions } from "./contract/filePicker";
export type {
  PluginConfigValues,
  PluginHostAssets,
  PluginHostConfig,
  PluginHostServices,
} from "./contract/hostServices";
export type {
  PluginAccountDetailProps,
  PluginNavPageProps,
  PluginNavPageSidebarProps,
  PluginRoleAssetsProps,
  StandaloneSettingsSectionProps,
} from "./contract/slots";
export type {
  PluginChatImageActionProps,
  PluginImageTarget,
  PluginRoleSettingsContribution,
  PluginRoleSettingsProps,
  PluginRoleValues,
} from "./contract/features";
export type {
  PluginAccountDetailComponentProps,
  PluginAccountDetailContribution,
  PluginInjectedProps,
  PluginNavPageComponentProps,
  PluginNavPageContribution,
  PluginNavPageSidebarComponentProps,
  PluginRoleAssetsComponentProps,
  PluginRoleAssetsContribution,
  PluginSettingsSectionComponentProps,
  PluginSettingsSectionContribution,
  PluginUiModule,
} from "./contract/uiModule";

// Runtime API 2.10.0 (#505): the host services context. One instance for host
// and plugins, so a component anywhere below a mounted contribution reads the
// services that contribution was injected with.
export { PluginHostServicesProvider, usePluginHostServices } from "./hostServicesContext";

// Type-only (#508): the desktop.surface and app.background contribution
// contracts, the surface payloads the main process shares, and the voice state
// the host pushes to the pet. `BackgroundCtx.reportFailure` is runtime API 2.11.0.
export type {
  PluginSurfaceComponentProps,
  SurfaceCreateResult,
  SurfaceExtension,
  SurfaceHandle,
  SurfaceMenuItem,
  SurfacePlacement,
  SurfaceSettleReason,
  SurfaceSpec,
  SurfaceWorkArea,
} from "./contract/surface";
export type { PluginSurfaceContribution, PluginSurfaceModule } from "./contract/surfaceModule";
export type {
  BackgroundCtx,
  BackgroundEffectDispose,
  PluginBackgroundAssets,
  PluginBackgroundContribution,
  PluginBackgroundEvents,
  PluginBackgroundSettled,
  PluginBackgroundStore,
  PluginBackgroundSurfaces,
  PluginBackgroundTray,
} from "./contract/background";
export type { VoiceStatePayload } from "./contract/voice";

// Runtime API 2.16.0: shared visual transitions and sidebar resizing.
export { CrossfadeLayers } from "./components/CrossfadeLayers";
export { SidebarResizeHandle } from "./components/SidebarResizeHandle";
