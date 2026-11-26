/** `import size from "./picture.webp?bytes"`: the file's size in bytes (src/lib/imageQueries.ts). */
declare module "*?bytes" {
  const bytes: number;
  export default bytes;
}

/** `import url from "./picture.png?url"`: the emitted file URL, bytes unchanged. */
declare module "*.png?url" {
  const url: string;
  export default url;
}
