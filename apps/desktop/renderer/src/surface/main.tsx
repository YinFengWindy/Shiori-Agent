import { createRoot } from "react-dom/client";
import { SurfaceRoot } from "./SurfaceRoot";
import { SurfaceFailure } from "./SurfaceFailure";
import "../styles.css";

const root = createRoot(document.getElementById("root") as HTMLElement);
const surface = window.miraDesktop.surface;
// Keep the existing build-time registry, but isolate its evaluation so a bad
// module cannot prevent the host's failure card from mounting and reporting ready.
void import("./pluginSurfaceModules").then(
  () => root.render(<SurfaceRoot search={window.location.search} surface={surface} />),
  (error: unknown) => {
    console.error("[surface] 插件模块加载失败", error);
    root.render(<SurfaceFailure detail="插件模块加载失败" surface={surface} />);
  },
);
