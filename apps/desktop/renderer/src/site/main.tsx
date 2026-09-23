import { createRoot } from "react-dom/client";
import { SiteApp } from "./SiteApp";
import "../styles.css";
import "./site.css";

const root = document.getElementById("root");
if (!root) throw new Error("Site root is missing");
createRoot(root).render(<SiteApp />);
