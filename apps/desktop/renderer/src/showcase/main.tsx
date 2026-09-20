import { createRoot } from "react-dom/client";
import { installRendererHost } from "../shared/rendererHost";
import { unavailableLocalAssetUrl } from "../../../src/bridge/shared";
import { demoAvatar, demoBackdrop } from "./demoContent";
import { ShowcaseApp } from "./ShowcaseApp";
import { ShowcaseErrorBoundary } from "./ShowcaseErrorBoundary";
import "../styles.css";
import "../../../../../plugins/story/ui/story.css";
import "./showcase.css";

const publicAssets = new Set([demoAvatar, demoBackdrop]);
installRendererHost({
  localAssetUrl: (path) => publicAssets.has(path) ? path : unavailableLocalAssetUrl,
  openExternal: (url) => { window.open(url, "_blank", "noopener,noreferrer"); },
});
const root = document.getElementById("root");
if (!root) throw new Error("Showcase root is missing");
createRoot(root).render(<ShowcaseErrorBoundary><ShowcaseApp /></ShowcaseErrorBoundary>);
