declare module "virtual:shiori-builtin-plugins/ui" {
  const modules: Record<string, { default: import("@yinfengwindy/shiori-sdk").PluginUiModule }>;
  export default modules;
}

declare module "virtual:shiori-builtin-plugins/background" {
  const modules: Record<string, { default: import("@yinfengwindy/shiori-sdk").PluginBackgroundContribution }>;
  export default modules;
}

declare module "virtual:shiori-builtin-plugins/surface" {
  const modules: Record<string, { default: import("@yinfengwindy/shiori-sdk").PluginSurfaceModule }>;
  export default modules;
}
