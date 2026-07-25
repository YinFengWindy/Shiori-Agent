export type BridgeRequest = {
  id: string;
  method: string;
  payload: Record<string, unknown>;
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

/** Result of creating a provider voice asset through the trusted main process. */
export type VoiceCloneResult = {
  ok: boolean;
  canceled?: boolean;
  provider?: string;
  ownership?: "shiori_managed";
  voiceId?: string;
  audioBase64?: string;
  format?: "mp3";
  error?: string;
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

export type SettingsFormData = {
  models: {
    provider: string;
    mainModel: string;
    mainApiKey: string;
    mainBaseUrl: string;
    enableThinking: boolean;
    reasoningEffort: string;
    multimodal: boolean;
    fastModel: string;
    fastApiKey: string;
    fastBaseUrl: string;
    agentModel: string;
    agentApiKey: string;
    agentBaseUrl: string;
    vlModel: string;
    vlApiKey: string;
    vlBaseUrl: string;
  };
  channels: {
    telegramToken: string;
    qqBotUin: string;
    qqBotAppId: string;
    qqBotClientSecret: string;
  };
  memory: {
    enabled: boolean;
    engine: string;
    embeddingModel: string;
    embeddingApiKey: string;
    embeddingBaseUrl: string;
    outputDimensionality: string;
  };
  integrations: {
    novelaiEnabled: boolean;
    novelaiToken: string;
    novelaiNsfwEnabled: boolean;
    novelaiAddQualityTags: boolean;
    novelaiUndesiredContentPreset: number;
    novelaiAutoWritebackRoleAssets: boolean;
  };
  voice: {
    enabled: boolean;
    hotkey: string;
    microphoneDeviceId: string;
    asrProvider: string;
    asrBaseUrl: string;
    asrModel: string;
    asrSecretId: string;
    asrSecretKey: string;
    ttsProvider: string;
    ttsBaseUrl: string;
    ttsModel: string;
    ttsApiKey: string;
  };
  advanced: {
    systemPrompt: string;
    maxTokens: number;
    maxIterations: number;
    devMode: boolean;
    memoryWindow: number;
    searchEnabled: boolean;
    spawnEnabled: boolean;
    memoryOptimizerEnabled: boolean;
    memoryOptimizerIntervalSeconds: number;
    pluginsRawToml: string;
  };
};

export type SettingsSnapshot = {
  configPath: string;
  formData: SettingsFormData;
};

export type SaveSettingsResult = {
  ok: boolean;
  restart: {
    ok: boolean;
    running: boolean;
    lastError: string | null;
  };
  health: {
    ok: boolean;
    message: string;
  };
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
  kind: "image" | "document";
};

/** Fixed non-sensitive URL used when no local asset capability is available. */
export const unavailableLocalAssetUrl = "shiori-asset://local/unavailable";

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

export type DesktopApi = {
  invoke(request: Omit<BridgeRequest, "id">): Promise<BridgeResponse>;
  onEvent(listener: (event: BridgeEvent) => void): () => void;
  pickImages(options?: { multiple?: boolean }): Promise<string[]>;
  pickChatAttachments(options?: { multiple?: boolean }): Promise<string[]>;
  /** Opens a picker for a self-contained Codex-compatible desktop-pet package. */
  pickPetPackage(): Promise<string | null>;
  /** Resolves a previously transported local path to its opaque asset URL. */
  localAssetUrl(path: string): string;
  startAttachmentDrag(request: StartAttachmentDragRequest): void;
  openAttachment(request: LocalAssetOpenRequest): Promise<LocalAssetOpenResult>;
  reportRendererDiagnostic(payload: RendererDiagnosticPayload): void;
  bridgeStatus(): Promise<{ running: boolean; lastError: string | null }>;
  restartBridge(): Promise<{
    ok: boolean;
    running: boolean;
    lastError: string | null;
  }>;
  readSettings(): Promise<SettingsSnapshot>;
  saveSettings(formData: SettingsFormData): Promise<SaveSettingsResult>;
  /** Lists input devices exposed by the hidden capture renderer. */
  listVoiceInputDevices(): Promise<VoiceInputDevice[]>;
  /** Starts a short local microphone test without sending it to ASR. */
  startVoiceTest(deviceId?: string): Promise<void>;
  /** Stops the local microphone test and plays it back locally. */
  stopVoiceTest(): Promise<void>;
  /** Opens the native picker and clones one transient voice sample through the bridge. */
  cloneVoice(): Promise<VoiceCloneResult>;
  /** Plays a provider-generated voice preview through the hidden audio surface. */
  playVoicePreview(audioBase64: string): Promise<void>;
  /** Controls the custom frameless Electron window chrome. */
  windowControl(action: WindowControlAction): Promise<void>;
  /** Returns the current custom window state used by the frameless title bar. */
  windowState(): Promise<WindowState>;
  /** Synchronizes the desktop-pet window with the role saved by the detail form. */
  syncPet(forceVisible?: boolean): Promise<void>;
  /** Dismisses the active safe observation bubble. */
  dismissPetObservationBubble(): Promise<void>;
  /** Starts following the system cursor from the given local pet offset and screen sample. */
  beginPetDrag(offsetX: number, offsetY: number, screenX?: number, screenY?: number): void;
  /** Applies an immediate renderer cursor sample during a pet drag. */
  movePet(screenX: number, screenY: number): void;
  /** Stops the current pet drag and optionally starts a Codex-style release glide. */
  endPetDrag(screenX?: number, screenY?: number, velocityX?: number, velocityY?: number): void;
  /** Restores the main Shiori window from a pet double click. */
  openPetRole(): void;
  /** Opens the native context menu for the desktop-pet window. */
  openPetMenu(): void;
  /** Announces that the pet renderer has installed its initial-state listeners. */
  petRendererReady(): void;
  /** Reports the rendered full-reply bubble height so the main process can resize the transparent pet window. */
  setPetBubbleHeight(height: number): void;
  /** Subscribes to package loads from the dedicated desktop-pet window. */
  onPetLoad(listener: (event: unknown, payload: unknown) => void): void;
  offPetLoad(listener: (event: unknown, payload: unknown) => void): void;
  /** Subscribes to sprite state transitions from the desktop-pet controller. */
  onPetPlay(listener: (event: unknown, payload: unknown) => void): void;
  offPetPlay(listener: (event: unknown, payload: unknown) => void): void;
  /** Subscribes to safe observation status and speech-bubble updates. */
  onPetObservation(listener: (event: unknown, payload: unknown) => void): void;
  offPetObservation(listener: (event: unknown, payload: unknown) => void): void;
  /** Subscribes to main-process placement updates for the current full-reply bubble. */
  onPetBubbleLayout(listener: (event: unknown, payload: unknown) => void): void;
  offPetBubbleLayout(listener: (event: unknown, payload: unknown) => void): void;
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
