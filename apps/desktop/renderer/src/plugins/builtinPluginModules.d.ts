declare module "virtual:shiori-builtin-plugins" {
  const modules: Record<string, import("@yinfengwindy/shiori-sdk").PluginFrontendModule>;
  export default modules;
}
