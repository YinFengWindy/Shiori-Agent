/**
 * `@shiori/sdk/contract`: the SDK's React- and DOM-free contract types,
 * for host code compiled outside the renderer (the Electron main process and
 * preload, whose TypeScript programs have neither JSX nor the DOM library and
 * so cannot load the main entry's components).
 *
 * Type-only: it has no runtime presence and is not part of the renderer import
 * map. It carries only the types that host code actually uses; plugins import
 * the same types from the main entry.
 */
export type { NativeFilePickerOptions } from "./contract/filePicker";
export type { BridgeEvent } from "./rpc";
export type {
  SurfaceCreateResult,
  SurfaceExtension,
  SurfaceHandle,
  SurfaceMenuItem,
  SurfacePlacement,
  SurfaceSettleReason,
  SurfaceSpec,
  SurfaceWorkArea,
} from "./contract/surface";
export type { PluginBackgroundSettled } from "./contract/background";
export type { VoiceStatePayload, VoiceInputSource } from "./contract/voice";
export type { SurfaceInteractionTarget, SurfaceVoiceGesture, SurfaceVoice, SurfaceRoleActivity } from "./contract/surfaceInteraction";
