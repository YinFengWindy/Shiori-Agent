/** Renderer-safe options for a native selection copied into private import staging (`host.pickFiles`). */
export type NativeFilePickerOptions = {
  namespace: string;
  filters: Array<{ name: string; extensions: string[] }>;
  multiple?: boolean;
  maxFileBytes: number;
};
