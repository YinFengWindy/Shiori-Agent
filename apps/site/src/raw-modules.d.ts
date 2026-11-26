/** Vite's `?raw` import: the file's text, not a module. */
declare module "*.js?raw" {
  const source: string;
  export default source;
}
