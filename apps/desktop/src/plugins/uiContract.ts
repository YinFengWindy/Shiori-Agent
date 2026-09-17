/** Controlled origin for admitted, precompiled plugin renderer resources. */
export const pluginUiScheme = "shiori-plugin";

/** The browser resolves React peers to wrappers around the host's own instances. */
export const pluginUiImportMap = JSON.stringify({ imports: Object.fromEntries(
  ["react", "react/jsx-runtime", "react-dom", "react-dom/client"].map((name) => [name, `${pluginUiScheme}://host/${name}.mjs`]),
) });

/**
 * One admitted (or failed-to-admit) workspace renderer entry returned by the
 * main process. The same shape serves all three renderer contribution
 * points (`renderer.ui`, `renderer.background`, `renderer.surface`) — they
 * are admitted under identical trust and resource-authorization rules, so
 * only the field name they travel under (`renderer_ui` / `renderer_background`
 * / `renderer_surface`, see `ipcRegistrations.ts`) tells them apart.
 */
export type RuntimePluginUi = { pluginId: string; entry: string; css: string[]; error?: string };

/** The three renderer contribution points a plugin package may declare (`renderer_contract.py`). */
export type PluginRendererKind = "ui" | "background" | "surface";

/** One `RuntimePluginUi` grant tagged with which renderer contribution point it admits. */
export type RuntimePluginRendererEntry = RuntimePluginUi & { kind: PluginRendererKind };

/** Module export names guaranteed by the renderer peer ABI. */
export const pluginUiPeerExports: Record<string, string[]> = {
  "react": ["Children", "Component", "Fragment", "Profiler", "PureComponent", "StrictMode", "Suspense", "Activity", "cache", "cacheSignal", "cloneElement", "createContext", "createElement", "createRef", "forwardRef", "isValidElement", "lazy", "memo", "startTransition", "use", "useActionState", "useCallback", "useContext", "useDebugValue", "useDeferredValue", "useEffect", "useEffectEvent", "useId", "useImperativeHandle", "useInsertionEffect", "useLayoutEffect", "useMemo", "useOptimistic", "useReducer", "useRef", "useState", "useSyncExternalStore", "useTransition", "version"],
  "react/jsx-runtime": ["Fragment", "jsx", "jsxs"],
  "react-dom": ["createPortal", "flushSync", "preconnect", "prefetchDNS", "preinit", "preinitModule", "preload", "preloadModule", "requestFormReset", "unstable_batchedUpdates", "useFormState", "useFormStatus", "version"],
  "react-dom/client": ["createRoot", "hydrateRoot", "version"],
};
