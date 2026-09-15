import { useEffect } from "react";
import { cardClass, cx } from "../shared/styles";
import type { SurfaceHandle } from "./pluginSurfaceRegistry";

/** Paints a readable diagnostic before allowing a failed surface to appear. */
export function SurfaceFailure({ detail, surface }: { detail: string; surface: SurfaceHandle }) {
  useEffect(() => {
    console.error(`[surface] ${detail}`);
    surface.ready();
  }, [detail, surface]);
  return (
    <div role="alert" className={cx(cardClass, "p-3 text-body-sm text-danger-text break-words")}>
      桌面窗口加载失败：{detail}
    </div>
  );
}
