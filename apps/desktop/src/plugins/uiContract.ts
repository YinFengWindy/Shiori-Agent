/** Controlled origin for admitted, precompiled plugin renderer resources. */
export const pluginUiScheme = "shiori-plugin";

/** The browser resolves React peers to wrappers around the host's own instances. */
export const pluginUiImportMap = JSON.stringify({ imports: Object.fromEntries(
  ["react", "react/jsx-runtime", "react-dom", "react-dom/client"].map((name) => [name, `${pluginUiScheme}://host/${name}.mjs`]),
) });

/** One admitted workspace UI entry returned by the main process. */
export type RuntimePluginUi = { pluginId: string; entry: string; css: string[]; error?: string };

/** Module export names guaranteed by the renderer peer ABI. */
export const pluginUiPeerExports: Record<string, string[]> = {
  "react": ["Children", "Component", "Fragment", "Profiler", "PureComponent", "StrictMode", "Suspense", "Activity", "cache", "cacheSignal", "cloneElement", "createContext", "createElement", "createRef", "forwardRef", "isValidElement", "lazy", "memo", "startTransition", "use", "useActionState", "useCallback", "useContext", "useDebugValue", "useDeferredValue", "useEffect", "useEffectEvent", "useId", "useImperativeHandle", "useInsertionEffect", "useLayoutEffect", "useMemo", "useOptimistic", "useReducer", "useRef", "useState", "useSyncExternalStore", "useTransition", "version"],
  "react/jsx-runtime": ["Fragment", "jsx", "jsxs"],
  "react-dom": ["createPortal", "flushSync", "preconnect", "prefetchDNS", "preinit", "preinitModule", "preload", "preloadModule", "requestFormReset", "unstable_batchedUpdates", "useFormState", "useFormStatus", "version"],
  "react-dom/client": ["createRoot", "hydrateRoot", "version"],
};
