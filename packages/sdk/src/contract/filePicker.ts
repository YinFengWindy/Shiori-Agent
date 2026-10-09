/**
 * Renderer-safe options for a native file selection returned by its original
 * path (`host.pickFilePaths`, runtime API 3.1.1): nothing is copied.
 */
export type NativeFilePathPickerOptions = {
  filters: Array<{ name: string; extensions: string[] }>;
  multiple?: boolean;
  maxFileBytes: number;
};

/** Renderer-safe options for a native selection copied into private import staging (`host.pickFiles`). */
export type NativeFilePickerOptions = NativeFilePathPickerOptions & {
  namespace: string;
};
