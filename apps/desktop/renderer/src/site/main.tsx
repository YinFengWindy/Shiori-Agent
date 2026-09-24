import { createRoot } from "react-dom/client";
import { SiteApp } from "./SiteApp";
import { SoundProvider } from "./sound/SoundProvider";
import "../styles.css";
import "../shared/adv/adv.css";
import "./site.css";
import "./site-subscreens.css";

const root = document.getElementById("root");
if (!root) throw new Error("Site root is missing");
createRoot(root).render(
  <SoundProvider>
    <SiteApp />
  </SoundProvider>,
);
