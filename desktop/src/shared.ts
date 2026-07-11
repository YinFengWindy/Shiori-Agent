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

export type SettingsChannelGroup = {
  groupId: string;
  allowFrom: string[];
  requireAt: boolean;
};

export type SettingsChannelRoleBinding = {
  channel: string;
  chatId: string;
  roleId: string;
};

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
    telegramAllowFrom: string[];
    qqBotUin: string;
    qqAllowFrom: string[];
    qqGroups: SettingsChannelGroup[];
    roleBindings: SettingsChannelRoleBinding[];
  };
  memory: {
    enabled: boolean;
    engine: string;
    embeddingModel: string;
    embeddingApiKey: string;
    embeddingBaseUrl: string;
    outputDimensionality: string;
  };
  proactive: {
    enabled: boolean;
    profile: string;
    agentMaxSteps: number;
    agentContentLimit: number;
    agentWebFetchMaxChars: number;
    driftEnabled: boolean;
    driftMaxSteps: number;
    driftMinIntervalHours: number;
  };
  integrations: {
    novelaiEnabled: boolean;
    novelaiToken: string;
    novelaiNsfwEnabled: boolean;
    novelaiAddQualityTags: boolean;
    novelaiUndesiredContentPreset: number;
    novelaiAutoWritebackRoleAssets: boolean;
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

export type SettingsBindingsSnapshot = {
  bindings: SettingsChannelRoleBinding[];
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
  startAttachmentDrag(request: StartAttachmentDragRequest): void;
  reportRendererDiagnostic(payload: RendererDiagnosticPayload): void;
  bridgeStatus(): Promise<{ running: boolean; lastError: string | null }>;
  restartBridge(): Promise<{
    ok: boolean;
    running: boolean;
    lastError: string | null;
  }>;
  readSettings(): Promise<SettingsSnapshot>;
  saveSettings(formData: SettingsFormData): Promise<SaveSettingsResult>;
  readChannelRoleBindings(): Promise<SettingsBindingsSnapshot>;
  saveChannelRoleBindings(
    bindings: SettingsChannelRoleBinding[],
  ): Promise<SettingsBindingsSnapshot>;
  /** Controls the custom frameless Electron window chrome. */
  windowControl(action: WindowControlAction): Promise<void>;
  /** Returns the current custom window state used by the frameless title bar. */
  windowState(): Promise<WindowState>;
  smoke(): Promise<{
    status: { running: boolean; lastError: string | null };
    health: BridgeResponse;
    roles: BridgeResponse;
    restarted: { ok: boolean; running: boolean; lastError: string | null };
    healthAfterRestart: BridgeResponse;
    createdRole: BridgeResponse;
    openedSession: BridgeResponse;
    deletedRole: BridgeResponse;
  }>;
};
