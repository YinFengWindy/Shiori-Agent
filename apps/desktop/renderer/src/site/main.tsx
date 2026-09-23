import { createRoot } from "react-dom/client";
import { SiteApp } from "./SiteApp";
import { SoundProvider } from "./sound/SoundProvider";
import "../styles.css";
import "./site.css";

const root = document.getElementById("root");
if (!root) throw new Error("Site root is missing");
createRoot(root).render(
  <SoundProvider>
    <SiteApp />
  </SoundProvider>,
);
