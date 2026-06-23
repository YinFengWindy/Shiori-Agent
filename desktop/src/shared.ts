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

export type DesktopApi = {
  invoke(request: Omit<BridgeRequest, "id">): Promise<BridgeResponse>;
  onEvent(listener: (event: BridgeEvent) => void): () => void;
  pickImages(options?: { multiple?: boolean }): Promise<string[]>;
  bridgeStatus(): Promise<{ running: boolean; lastError: string | null }>;
  restartBridge(): Promise<{ ok: boolean; running: boolean; lastError: string | null }>;
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
