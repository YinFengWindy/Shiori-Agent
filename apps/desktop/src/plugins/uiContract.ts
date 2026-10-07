/** Controlled origin for admitted, precompiled plugin renderer resources. */
export const pluginUiScheme = "shiori-plugin";

/**
 * One admitted (or failed-to-admit) workspace renderer entry returned by the
 * main process. The same shape serves all three renderer contribution
 * points (`renderer.ui`, `renderer.background`, `renderer.surface`) — they
 * are admitted under identical trust and resource-authorization rules, so
 * only the field name they travel under (`renderer_ui` / `renderer_background`
 * / `renderer_surface`, see `ipcRegistrations.ts`) tells them apart.
 */
export type RuntimePluginUi = {
  pluginId: string;
  entry: string;
  css: string[];
  error?: string;
  /**
   * Opaque per-activation-attempt identity, echoed back by
   * `plugins.activation.report` (#262). Shared by every kind a plugin
   * declares — it identifies the backend handle, not the renderer entry —
   * so a report about a since-superseded generation's abandoned load cannot
   * be mistaken for one belonging to the plugin's current handle.
   */
  activationToken?: string;
};

/** The three renderer contribution points a plugin package may declare (`renderer_contract.py`). */
export type PluginRendererKind = "ui" | "background" | "surface";

/** One `RuntimePluginUi` grant tagged with which renderer contribution point it admits. */
export type RuntimePluginRendererEntry = RuntimePluginUi & { kind: PluginRendererKind };

/**
 * Module export names guaranteed by the renderer peer ABI, keyed by the bare
 * specifier a precompiled plugin imports. Adding a peer or an export name is a
 * runtime API change (`RUNTIME_API_VERSION` in `host_contract.py`); every
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
    // Runtime API 3.1.2: shared private document lifecycle.
    "usePrivateDraft",
    // Runtime API 3.1.3: generic private runtime controls.
    "ManagedRuntimePanel", "useManagedRuntime",
    // Runtime API 3.1.4 (#683): private document autosave and the settings page layout.
    "usePrivateAutosave", "SettingsField", "SettingsGroup", "SettingsSectionCard", "SettingsToggleField",
    "settingsGroupStackClass", "settingsInputClass",
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
