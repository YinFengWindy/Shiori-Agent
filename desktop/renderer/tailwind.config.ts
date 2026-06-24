import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import type { Config } from "tailwindcss";

const here = dirname(fileURLToPath(import.meta.url));

export default {
  content: [
    resolve(here, "index.html"),
    resolve(here, "src/**/*.{ts,tsx}"),
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Segoe UI", "Microsoft YaHei UI", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["Georgia", "Times New Roman", "serif"],
      },
      colors: {
        bg: "var(--bg)",
        "bg-soft": "var(--bg-soft)",
        panel: "var(--panel)",
        "panel-strong": "var(--panel-strong)",
        text: "var(--text)",
        muted: "var(--muted)",
        accent: "var(--accent)",
        "accent-deep": "var(--accent-deep)",
        primary: "var(--accent)",
        stroke: "var(--stroke)",
      },
      boxShadow: {
        panel: "var(--shadow)",
        composer: "0 18px 48px rgba(0, 0, 0, 0.08)",
        editor: "0 20px 60px rgba(0, 0, 0, 0.12)",
      },
      gridTemplateRows: {
        app: "var(--titlebar-height) minmax(0, 1fr)",
        chat: "70px minmax(0, 1fr)",
        conversation: "auto minmax(0, 1fr) auto",
      },
    },
  },
  plugins: [],
} satisfies Config;
