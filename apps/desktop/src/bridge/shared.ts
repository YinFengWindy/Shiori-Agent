export type BridgeRequest = {
  id: string;
  method: string;
  payload: Record<string, unknown>;
  /** Optional caller-owned deadline, consumed locally by the bridge transport. */
  timeoutMs?: number;
};

/** Where a surface's body ended up after the host clamped and settled it. */
export type SurfacePlacementPayload = {
  anchor: { x: number; y: number };
  bodyOffset: { x: number; y: number };
  workArea: { x: number; y: number; width: number; height: number };
};

/**
 * Where a freshly created surface landed, and which display it landed on.
 *
 * `displayId` rides along with the creation result rather than being a second
 * call because a plugin that remembers a position *per display* needs both in
 * one breath: it has to pick the remembered anchor before the surface has
 * painted anything, and a follow-up round trip would put a visible jump
 * between the fallback corner and the remembered position.
 */
export type SurfaceCreateResultPayload = { x: number; y: number; displayId: string };

/** A settle reported to the owning plugin's `app.background` code. */
export type SurfaceSettledPayload = {
  pluginId: string;
  surfaceId: string;
  placement: SurfacePlacementPayload;
  reason: import("../surface/host.js").SurfaceSettleReason;
  displayId: string;
};

/** What a plugin declares when asking the host to create one of its windows. */
export type SurfaceSpecPayload = {
  body: { width: number; height: number };
  transparent?: boolean;
  alwaysOnTop?: boolean;
  skipTaskbar?: boolean;
  clickThrough?: boolean;
};

/**
 * Creates and addresses plugin-owned desktop windows by name.
 *
 * A surface renderer cannot create its own window, so creation comes from
 * code already running in the main window — a plugin's `nav.page` or
 * `settings.section` from #179.
 */
export type DesktopSurfacesApi = {
  create(
    pluginId: string,
    surfaceId: string,
    spec: SurfaceSpecPayload,
    anchor: { x: number; y: number },
  ): Promise<SurfaceCreateResultPayload>;
  destroy(pluginId: string, surfaceId: string): Promise<void>;
  show(pluginId: string, surfaceId: string): void;
  hide(pluginId: string, surfaceId: string): void;
  workArea(pluginId: string, surfaceId: string): Promise<SurfacePlacementPayload["workArea"]>;
  setPosition(pluginId: string, surfaceId: string, position: { x: number; y: number }): void;
  moveTo(pluginId: string, surfaceId: string, position: { x: number; y: number }, durationMs: number): void;
  /** Relays a transient payload to the surface renderer, delivered on `onMessage`. */
  post(pluginId: string, surfaceId: string, message: unknown): void;
  /**
   * Sets the surface's retained state, replayed whenever its renderer reports
   * ready. Use this for anything the surface must still be showing after a
   * reload; use `post` for one-shot events.
   */
  setState(pluginId: string, surfaceId: string, state: unknown): void;
};

/** One entry of a surface-owned native context menu. */
export type SurfaceMenuItemPayload = { id: string; label: string };

/**
 * Drives the surface window the caller is already inside.
 *
 * No surface is named: the host attributes each request to whichever surface
 * owns the sending window, so this half cannot address anything else.
 */
export type DesktopSurfaceSelfApi = {
  beginDrag(offset: { x: number; y: number }): void;
  endDrag(velocity?: { x: number; y: number }): void;
  setExtension(extension: { side: "above" | "below"; size: number }): void;
  setClickThrough(clickThrough: boolean): void;
  onPlacement(listener: (placement: SurfacePlacementPayload) => void): () => void;
  /** Transient one-shot payloads from the plugin's own `surfaces.post`. */
  onMessage(listener: (payload: unknown) => void): () => void;
  /** Retained state from `surfaces.setState`, replayed after `ready()`. */
  onState(listener: (state: unknown) => void): () => void;
  /**
   * Announces that this renderer has installed its listeners, so the host can
   * replay the retained state and the current placement. Without it a surface
   * that mounts after its state was set would come up blank.
   */
  ready(): void;
  /** Opens a native context menu over this surface; resolves the chosen id, or null. */
  showContextMenu(items: SurfaceMenuItemPayload[]): Promise<string | null>;
  /** Brings the main application window forward. */
  activateMainWindow(): void;
};

export type BridgeResponse = {
  id: string;
  type: "response";
  method: string;
  payload: Record<string, unknown>;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  } | null;
};

export type BridgeEvent = {
  id: string;
  type: "event";
  method: string;
  payload: Record<string, unknown>;
};

/** Public desktop-pet voice state used by the pet and settings surfaces. */
export type VoiceStatePayload = {
  status:
    | "idle"
    | "press_pending"
    | "dragging"
    | "recording"
    | "transcribing"
    | "sending"
    | "waiting_reply"
    | "speaking_prepare"
    | "speaking"
    | "finish_current_sentence_then_idle"
    | "error";
  source?: "pet" | "hotkey";
  message?: string;
};

/** Commands sent from the Electron main process to the hidden capture page. */
export type VoiceInputDevice = {
  deviceId: string;
  label: string;
};

export type VoiceCaptureCommand =
  | "stop"
  | "cancel"
  | { command: "start"; deviceId?: string }
  | { command: "list-devices" }
  | { command: "play-test"; audioBase64: string };

/** Commands sent from the main process to the hidden voice playback surface. */
export type VoicePlaybackCommand =
  | { command: "play"; id: string; audioBase64: string; format: "mp3" }
  | { command: "cancel" };

/** Editable model registration persisted in config.toml. */
export type ModelRegistrationFormData = {
  id: string;
  provider: string;
  baseUrl: string;
  apiKey: string;
  model: string;
  effort: "none" | "low" | "high" | "max";
};

export type SettingsFormData = {
  /** Explicit core motive preferences; omitted keys retain backend defaults and legacy migration. */
  proactiveStrategies: {
    sceneFollowup?: boolean;
    relationship?: boolean;
  };
  models: {
    registrations: ModelRegistrationFormData[];
  };
  channels: {
    telegramToken: string;
    qqBotUin: string;
  };
  memory: {
    enabled: boolean;
    engine: string;
    embeddingModel: string;
    embeddingApiKey: string;
    embeddingBaseUrl: string;
    outputDimensionality: string;
  };
  voice: {
    enabled: boolean;
    hotkey: string;
    microphoneDeviceId: string;
    /** Preserved provider-level switch from config.toml. */
    asrEnabled?: boolean;
    asrProvider: string;
    asrBaseUrl: string;
    asrSecretId: string;
    asrSecretKey: string;
    /** Preserved provider-level switch from config.toml. */
    ttsEnabled?: boolean;
    ttsProvider: string;
    ttsBaseUrl: string;
    ttsModel: string;
    ttsApiKey: string;
    ttsVolume: number;
  };
  advanced: {
    maxTokens: number;
    maxIterations: number;
    devMode: boolean;
    streamingEnabled: boolean;
    memoryWindow: number;
    searchEnabled: boolean;
    spawnEnabled: boolean;
    /** Preserves the core scene observation switch across unrelated settings saves. */
    sceneObservationEnabled?: boolean;
    memoryOptimizerEnabled: boolean;
    memoryOptimizerIntervalSeconds: number;
    consolidationInputTokenThreshold: number;
  };
  pendingRoleModelUpdates?: PendingRoleModelUpdate[];
};

/** Deferred role-reference changes committed atomically with the settings. */
export type PendingRoleModelUpdate = {
  roleId: string;
  runtimeConfig: Record<string, unknown>;
};

export type SettingsSnapshot = {
  configPath: string;
  formData: SettingsFormData;
  /** Active backend version; omitted only by the local configuration reader. */
  generation?: number;
};

/** Optimistic concurrency and retry identity for a settings transaction. */
export type SettingsSaveOptions = {
  expectedGeneration?: number;
  operationId?: string;
};

/** Configuration and role-binding transaction accepted by runtime.apply. */
export type RuntimeApplyRequest = {
  /** Ordinary settings drafts preserve current plugin configuration inside the host transaction. */
  preserve_plugins?: boolean;
  config_toml: string;
  expected_generation?: number;
  operation_id: string;
  role_model_updates: { role_id: string; runtime_config: Record<string, unknown> }[];
};

/** Result of applying settings to the active backend runtime. */
export type SaveSettingsResult = {
  ok: boolean;
  generation?: number;
  changed?: boolean;
  error?: NonNullable<BridgeResponse["error"]>;
};

/** Window chrome actions exposed through the preload bridge. */
export type WindowControlAction = "minimize" | "toggleMaximize" | "close";

export type WindowState = {
  isMaximized: boolean;
  isVisible: boolean;
};

export type StartAttachmentDragRequest = {
  path: string;
};

/** Opaque renderer reference to a main-process-authorized local file. */
export type LocalAssetReference = {
  path: string;
  url: string;
  kind: "image" | "audio" | "document";
};

/** Fixed non-sensitive URL used when no local asset capability is available. */
export { unavailableLocalAssetUrl } from "../assets/localAssetContract.js";

/** Carries renderer-facing data alongside authorized local asset references. */
export type LocalAssetTransport<T> = {
  value: T;
  assets: LocalAssetReference[];
};

/** Requests opening an already authorized attachment with the operating system. */
export type LocalAssetOpenRequest = {
  path?: string;
  url?: string;
};

export type LocalAssetOpenResult = {
  ok: boolean;
  error: string | null;
};

/** Result returned after attempting to open a validated external URL. */
export type ExternalLinkOpenResult = {
  ok: boolean;
  error: string | null;
};

export type RendererDiagnosticPayload = {
  kind: "error" | "unhandledrejection" | "error-boundary";
  message: string;
  stack?: string;
  componentStack?: string;
  filename?: string;
  lineno?: number;
  colno?: number;
  details?: Record<string, unknown>;
};

export type TrayEntryClickedPayload = import("../tray/ipc.js").TrayEntryClickedPayload;

export type DesktopApi = {
  /** Reads and controls the Electron application update lifecycle. */
  updates: import("../updateContract.js").DesktopUpdateApi;
  /** Identifies one main-process lifetime, including renderer reloads. */
  applicationSessionId(): Promise<string>;
  invoke(request: Omit<BridgeRequest, "id">): Promise<BridgeResponse>;
  onEvent(listener: (event: BridgeEvent) => void): () => void;
  pickImages(options?: { multiple?: boolean }): Promise<string[]>;
  /** Selects one role-card file into a temporary, non-role staging directory. */
  pickRoleCard(): Promise<string | null>;
  pickChatAttachments(options?: { multiple?: boolean }): Promise<string[]>;
  /** Opens an http, https, or mailto link through the operating system. */
  openExternal(url: string): Promise<ExternalLinkOpenResult>;
  /** Stages a native file selection without treating arbitrary formats as media. */
  pickFiles(options: import("../assets/filePickerContract.js").NativeFilePickerOptions): Promise<string[]>;
  /** Resolves a previously transported local path to its opaque asset URL. */
  localAssetUrl(path: string): string;
  startAttachmentDrag(request: StartAttachmentDragRequest): void;
  reportRendererDiagnostic(payload: RendererDiagnosticPayload): void;
  bridgeStatus(): Promise<{ running: boolean; lastError: string | null }>;
  restartBridge(): Promise<{
    ok: boolean;
    running: boolean;
    lastError: string | null;
  }>;
  readSettings(): Promise<SettingsSnapshot>;
  saveSettings(formData: SettingsFormData, options?: SettingsSaveOptions): Promise<SaveSettingsResult>;
  /** Lists input devices exposed by the hidden capture renderer. */
  listVoiceInputDevices(): Promise<VoiceInputDevice[]>;
  /** Starts a short local microphone test without sending it to ASR. */
  startVoiceTest(deviceId?: string): Promise<void>;
  /** Stops the local microphone test and plays it back locally. */
  stopVoiceTest(): Promise<void>;
  /** Cancels an active or still-starting microphone test without playback. */
  cancelVoiceTest(): Promise<void>;
  /** Controls the custom frameless Electron window chrome. */
  windowControl(action: WindowControlAction): Promise<void>;
  /** Returns the current custom window state used by the frameless title bar. */
  windowState(): Promise<WindowState>;
  /** Synchronizes the desktop-pet window with the role saved by the detail form. */
  syncPet(forceVisible?: boolean): Promise<void>;
  /**
   * Dismisses the active safe observation bubble.
   *
   * Still a pet-shaped host call: the pet's surface uses it directly until
   * observation itself becomes a plugin (#220) and reaches the pet over
   * plugin-to-plugin messaging (#218).
   */
  dismissPetObservationBubble(): Promise<void>;
  /**
   * The DesktopSurface capability (#181): plugin-owned desktop windows.
   *
   * Split in two because the two halves have different trust properties.
   * `surfaces` names the surface it acts on and is reachable from any
   * main-window code; `surface` acts on the window the caller is already
   * inside, which the host resolves from the sender rather than the payload.
   * See `src/surface/ipc.ts`.
   */
  surfaces: DesktopSurfacesApi;
  surface: DesktopSurfaceSelfApi;
  /**
   * Reports every surface settle to whoever is listening in this window.
   *
   * Unlike `surface.onPlacement`, which the host addresses to one surface's own
   * renderer, this is a broadcast into the plugin-host window: the listener
   * filters by `pluginId`/`surfaceId`. See `surfaceSettledChannel`.
   */
  onSurfaceSettled(listener: (settled: SurfaceSettledPayload) => void): () => void;
  /**
   * Plugin-contributed tray menu items (#181-D).
   *
   * A `Tray` is main-process-only, so a plugin's background code cannot build
   * one; it contributes an item and is told when the user picks it. Items are
   * accepted even on platforms with no tray and even before the tray exists —
   * see `tray/registry.ts`.
   */
  tray: {
    setEntry(pluginId: string, entryId: string, entry: { label: string; enabled?: boolean }): void;
    removeEntry(pluginId: string, entryId: string): void;
    /** Drops every item one plugin contributed, in one call. See `tray/registry.ts`. */
    removeAllEntries(pluginId: string): void;
    onEntryClicked(listener: (payload: TrayEntryClickedPayload) => void): () => void;
  };
  /**
   * Per-plugin persisted JSON, for background code that has no filesystem.
   *
   * Distinct from `plugin.config.*`, which is the user-editable settings form:
   * this is runtime state a plugin keeps to itself. See `plugins/dataStore.ts`.
   */
  pluginData: {
    read(pluginId: string): Promise<unknown>;
    write(pluginId: string, value: unknown): Promise<void>;
  };
  /** Subscribes to microphone commands issued by the main-process recorder. */
  onVoiceCaptureCommand(listener: (command: VoiceCaptureCommand) => void): () => void;
  /** Reports captured 16-bit PCM samples to the owning main-process recorder. */
  voiceCaptureData(samples: ArrayBuffer): void;
  /** Reports that microphone permission and capture initialization succeeded. */
  voiceCaptureReady(): void;
  /** Reports that the current capture stream has stopped. */
  voiceCaptureStopped(): void;
  /** Reports a microphone or Web Audio failure without exposing raw audio. */
  voiceCaptureError(message: string): void;
  /** Reports the sanitized input-device list from the hidden capture renderer. */
  voiceInputDevices(devices: VoiceInputDevice[]): void;
  /** Subscribes to audio playback commands issued by the main process. */
  onVoicePlaybackCommand(listener: (command: VoicePlaybackCommand) => void): () => void;
  /** Reports that one decoded audio item started playing. */
  voicePlaybackStarted(id: string): void;
  /** Reports that one audio item finished naturally. */
  voicePlaybackFinished(id: string): void;
  /** Reports a playback decode or device error. */
  voicePlaybackError(id: string, message: string): void;
  /** Starts the shared pet long-press voice gesture. */
  startVoicePress(): void;
  /** Lets pet dragging cancel a pending voice gesture. */
  voicePointerMoved(): void;
  /** Releases a pending or active pet voice gesture. */
  voiceRelease(): void;
  /** Cancels a pet voice gesture without submitting audio. */
  voiceCancel(): void;
  /** Subscribes to main-process voice state updates. */
  onVoiceState(listener: (payload: VoiceStatePayload) => void): () => void;
};
