// Remotion's webpack emits imported pictures as files and hands back their URL.
declare module "*.png" {
  const src: string;
  export default src;
}
declare module "*.webp" {
  const src: string;
  export default src;
}
