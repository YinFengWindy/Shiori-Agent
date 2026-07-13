declare module "electron" {
  export type IpcMainInvokeEvent = unknown;
  export type NativeImage = unknown;
  export type MenuInstance = unknown;
  export type BrowserWindowCloseEvent = {
    preventDefault(): void;
  };

  export type MenuItemConstructorOptions = {
    label?: string;
    click?: () => void;
  };

  export type Privileges = {
    standard?: boolean;
    secure?: boolean;
    supportFetchAPI?: boolean;
    corsEnabled?: boolean;
  };

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
      spellcheck?: boolean;
    };
  }

  export interface BrowserWindowInstance {
    loadFile(path: string): Promise<void>;
    loadURL(url: string): Promise<void>;
    show(): void;
    hide(): void;
    focus(): void;
    restore(): void;
    minimize(): void;
    maximize(): void;
    unmaximize(): void;
    isMaximized(): boolean;
    isMinimized(): boolean;
    isVisible(): boolean;
    close(): void;
    on(event: string, handler: (...args: unknown[]) => void): void;
    webContents: {
      send(channel: string, payload: unknown): void;
      on(event: string, handler: (...args: unknown[]) => void): void;
      executeJavaScript(code: string): Promise<unknown>;
      startDrag(item: { file: string; icon: NativeImage | string }): void;
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
    getPath(name: string): string;
    requestSingleInstanceLock(): boolean;
    quit(): void;
    exit(code?: number): void;
  };

  export const protocol: {
    registerSchemesAsPrivileged(customSchemes: Array<{ scheme: string; privileges?: Privileges }>): void;
    handle(scheme: string, handler: (request: { url: string }) => Promise<Response> | Response): void;
  };

  export const dialog: {
    showOpenDialog(options: {
      properties?: string[];
      filters?: Array<{ name: string; extensions: string[] }>;
    }): Promise<{ canceled: boolean; filePaths: string[] }>;
  };

  export const Menu: {
    buildFromTemplate(template: MenuItemConstructorOptions[]): MenuInstance;
  };

  export const Tray: {
    new (image: NativeImage | string): {
      setToolTip(toolTip: string): void;
      setContextMenu(menu: MenuInstance): void;
      destroy(): void;
      on(event: string, handler: (...args: unknown[]) => void): void;
    };
  };

  export const ipcMain: {
    handle(
      channel: string,
      listener: (
        event: IpcMainInvokeEvent,
        ...args: unknown[]
      ) => Promise<unknown> | unknown,
    ): void;
    on(
      channel: string,
      listener: (
        event: IpcMainInvokeEvent & { sender: BrowserWindowInstance["webContents"] },
        ...args: unknown[]
      ) => void,
    ): void;
  };

  export const ipcRenderer: {
    invoke(channel: string, ...args: unknown[]): Promise<unknown>;
    send(channel: string, ...args: unknown[]): void;
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

  export const nativeImage: {
    createFromDataURL(dataURL: string): NativeImage;
  };
}
