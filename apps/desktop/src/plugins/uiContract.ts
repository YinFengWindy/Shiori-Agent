import type { PluginFrontendExport } from "@yinfengwindy/shiori-sdk/contract";
/** Controlled origin for admitted, precompiled plugin renderer resources. */
export const pluginUiScheme = "shiori-plugin";

/** One admitted frontend namespace and its package-scoped resources. */
export type RuntimePluginFrontend = {
  pluginId: string;
  entry: string;
  css: string[];
  exports: PluginFrontendExport[];
  error?: string;
  /** Opaque identity echoed to activation reports; never inferred from code identity. */
  activationToken?: string;
};

/**
 * Module export names guaranteed by the renderer peer ABI, keyed by the bare
 * specifier a precompiled plugin imports. Adding a peer or an export name is a
 * runtime API change (`__version__` in `shiori_sdk/_version.py`); every
 * key must also be installed by `runtimePluginPeers.ts`.
 */
export const pluginUiPeerExports: Record<string, string[]> = {
  "react": ["Children", "Component", "Fragment", "Profiler", "PureComponent", "StrictMode", "Suspense", "Activity", "cache", "cacheSignal", "cloneElement", "createContext", "createElement", "createRef", "forwardRef", "isValidElement", "lazy", "memo", "startTransition", "use", "useActionState", "useCallback", "useContext", "useDebugValue", "useDeferredValue", "useEffect", "useEffectEvent", "useId", "useImperativeHandle", "useInsertionEffect", "useLayoutEffect", "useMemo", "useOptimistic", "useReducer", "useRef", "useState", "useSyncExternalStore", "useTransition", "version"],
  "react/jsx-runtime": ["Fragment", "jsx", "jsxs"],
  "react-dom": ["createPortal", "flushSync", "preconnect", "prefetchDNS", "preinit", "preinitModule", "preload", "preloadModule", "requestFormReset", "unstable_batchedUpdates", "useFormState", "useFormStatus", "version"],
  "react-dom/client": ["createRoot", "hydrateRoot", "version"],
  // Only the main entry: `@yinfengwindy/shiori-sdk/testing` is development-only,
  // `@yinfengwindy/shiori-sdk/contract` is type-only and
  // `@yinfengwindy/shiori-sdk/host-internal` is host-only (not plugin contract).
  "@yinfengwindy/shiori-sdk": [
    // Runtime API 2.8.0 (#503).
    "BridgeError", "PluginBridgeError",
    // Runtime API 2.9.0 (#504): helpers and hooks.
    "errorMessage", "useLatestRef", "roleToggleStatus", "accountOnline", "useAccountAction",
    // Runtime API 2.9.0: shared class names.
    "badgeClass", "cardClass", "compactButtonSizeClass", "compactGhostButtonClass", "compactPressableClass", "cx",
    "ghostButtonClass", "ghostButtonSurfaceClass", "iconButtonClass", "inputClass", "pressableClass",
    "primaryButtonSurfaceClass", "secondarySidebarSurfaceClass", "sidebarContentMotionClass", "sidebarNavItemClass",
    "textareaClass", "menuPanelClass", "menuSeparatorClass",
    // Runtime API 2.9.0: components and icons.
    "ActionMenu", "AutosizeTextarea", "RoleCapabilityCard", "Select", "SettingsToggleCard",
    "UploadIcon", "PetalIcon", "SparkleIcon", "navMotifs", "withMotif",
    // Runtime API 2.10.0 (#505): the host services context.
    "PluginHostServicesProvider", "usePluginHostServices",
    // Runtime API 2.16.0 (#576): shared visual components.
    "CrossfadeLayers", "SidebarResizeHandle",
    // Runtime API 3.1.1: generic private runtime controls.
    "ManagedRuntimePanel", "useManagedRuntime",
    // Runtime API 3.1.1 (#683): private document autosave and the settings page layout.
    "usePrivateAutosave", "SettingsField", "SettingsGroup", "SettingsSectionCard", "SettingsToggleField",
    "settingsGroupStackClass", "settingsInputClass",
    // Runtime API 3.1.1 (#734): the events that end a chat turn.
    "chatTerminalEventMethods", "isChatTerminalEvent",
    // SDK 4.1.1: authoritative surface lifecycle events for presentation providers.
    "surfaceLifecycleEvent",
    "nativeAudioPlaybackEvent",
    // Runtime API 3.1.1 (#720): the compact icon-only button.
    "compactIconButtonClass",
    // Unreleased (#827): the shared secondary sidebar shell.
    "secondarySidebarShellClass",
    // Unreleased (P6s, #906): chat-sidebar surfaces and the detail row, for the `roleTasks` block.
    "chatSidebarPanelClass", "chatSidebarHeaderClass", "chatSidebarScrollableClass", "DetailRow",
    "roleTaskGroupHeadClass", "roleTaskGroupCountClass", "roleTaskRowClass", "roleTaskRowTitleClass", "roleTaskRowSummaryClass",
    // Shared role-editor controls used by plugin-owned settings cards.
    "roleControlClass", "roleFieldClass", "roleFieldLabelClass", "rolePanelGhostButtonClass",
  ],
};

/**
 * The browser resolves every renderer peer to a wrapper around the host's own
 * instance (served by `PluginUiResources.load`), so a precompiled plugin shares
 * the host's React and plugin SDK instead of bundling copies.
 */
export const pluginUiImportMap = JSON.stringify({ imports: Object.fromEntries(
  Object.keys(pluginUiPeerExports).map((name) => [name, `${pluginUiScheme}://host/${name}.mjs`]),
) });
