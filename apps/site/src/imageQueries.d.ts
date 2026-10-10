/** `import placeholder from "./picture.webp?lqip"`: a tiny WebP `data:` URI (src/lib/imageQueries.ts). */
declare module "*?lqip" {
  const dataUri: string;
  export default dataUri;
}

/** `import size from "./picture.webp?bytes"`: the file's size in bytes (src/lib/imageQueries.ts). */
declare module "*?bytes" {
  const bytes: number;
  export default bytes;
}
