declare module "electron" {
  export type IpcMainInvokeEvent = unknown;

  export interface BrowserWindowOptions {
    width?: number;
    height?: number;
    minWidth?: number;
    minHeight?: number;
    frame?: boolean;
    backgroundColor?: string;
    webPreferences?: {
      preload?: string;
      contextIsolation?: boolean;
      nodeIntegration?: boolean;
      sandbox?: boolean;
    };
  }

  export interface BrowserWindowInstance {
    loadFile(path: string): Promise<void>;
    loadURL(url: string): Promise<void>;
    minimize(): void;
    maximize(): void;
    unmaximize(): void;
    isMaximized(): boolean;
    close(): void;
    webContents: {
      send(channel: string, payload: unknown): void;
      on(event: string, handler: (...args: unknown[]) => void): void;
      executeJavaScript(code: string): Promise<unknown>;
    };
  }

  export const BrowserWindow: {
    new (options?: BrowserWindowOptions): BrowserWindowInstance;
    getAllWindows(): BrowserWindowInstance[];
  };

  export const app: {
    whenReady(): Promise<void>;
    on(event: string, handler: (...args: unknown[]) => void): void;
    setPath(name: string, path: string): void;
    quit(): void;
    exit(code?: number): void;
  };

  export const dialog: {
    showOpenDialog(options: {
      properties?: string[];
      filters?: Array<{ name: string; extensions: string[] }>;
    }): Promise<{ canceled: boolean; filePaths: string[] }>;
  };

  export const ipcMain: {
    handle(
      channel: string,
      listener: (
        event: IpcMainInvokeEvent,
        ...args: any[]
      ) => Promise<unknown> | unknown,
    ): void;
  };

  export const ipcRenderer: {
    invoke(channel: string, ...args: unknown[]): Promise<unknown>;
    on(
      channel: string,
      listener: (event: unknown, payload: unknown) => void,
    ): void;
    off(
      channel: string,
      listener: (event: unknown, payload: unknown) => void,
    ): void;
  };

  export const contextBridge: {
    exposeInMainWorld(key: string, api: unknown): void;
  };
}
