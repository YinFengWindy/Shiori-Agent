import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import type { Config } from "tailwindcss";

const here = dirname(fileURLToPath(import.meta.url));

export default {
  content: [
    resolve(here, "index.html"),
    resolve(here, "src/**/*.{ts,tsx}"),
    // The static site skeleton's own entry HTML lives outside renderer/src
    // (apps/desktop/site/); its React entry under renderer/src/site/ is
    // already covered by the glob above.
    resolve(here, "../site/index.html"),
    // Plugin UI lives outside renderer/ (top-level plugins/<id>/ui/, see
    // issue #174); without this Tailwind never scans it and any class name
    // used only there is silently dropped from the production build.
    resolve(here, "../../../plugins/*/ui/**/*.{ts,tsx}"),
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)"],
        display: ["var(--font-display)"],
        // Story mode relies on the serif face for its decorative text; leave
        // it untouched and migrate headings to font-display per surface.
        serif: ["Georgia", "Times New Roman", "serif"],
      },
      // Semantic type scale. Chinese body text needs >=14px; captions floor at 12px.
      fontSize: {
        caption: ["12px", { lineHeight: "1.4" }],
        "body-sm": ["13px", { lineHeight: "1.5" }],
        body: ["14px", { lineHeight: "1.6" }],
        "body-lg": ["15px", { lineHeight: "1.6" }],
        "title-sm": ["16px", { lineHeight: "1.4", fontWeight: "600" }],
        title: ["18px", { lineHeight: "1.35", fontWeight: "600" }],
        headline: ["22px", { lineHeight: "1.25", fontWeight: "650" }],
        display: ["28px", { lineHeight: "1.15", fontWeight: "700" }],
      },
      colors: {
        // ---- semantic tier (preferred in new/refactored code) ----
        surface: {
          DEFAULT: "var(--color-bg-surface)",
          soft: "var(--color-bg-soft)",
          app: "var(--color-bg-app)",
          hover: "var(--color-bg-hover)",
          active: "var(--color-bg-active)",
        },
        ink: {
          DEFAULT: "var(--color-text-primary)",
          secondary: "var(--color-text-secondary)",
          muted: "var(--color-text-muted)",
          faint: "var(--color-text-faint)",
        },
        line: {
          soft: "var(--color-border-soft)",
          DEFAULT: "var(--color-border)",
          strong: "var(--color-border-strong)",
          accent: "var(--color-border-accent)",
        },
        accent: {
          DEFAULT: "var(--color-accent-solid)",
          hover: "var(--color-accent-hover)",
          soft: "var(--color-accent-soft)",
          softer: "var(--color-accent-softer)",
          text: "var(--color-text-accent)",
        },
        lavender: {
          soft: "var(--lavender-100)",
          DEFAULT: "var(--lavender-600)",
          text: "var(--color-text-lavender)",
        },
        success: {
          soft: "var(--color-success-soft)",
          DEFAULT: "var(--color-success-solid)",
          text: "var(--color-success-text)",
        },
        warning: {
          soft: "var(--color-warning-soft)",
          DEFAULT: "var(--color-warning-solid)",
          text: "var(--color-warning-text)",
        },
        danger: {
          soft: "var(--color-danger-soft)",
          DEFAULT: "var(--color-danger-solid)",
          text: "var(--color-danger-text)",
        },
        ring: "var(--color-ring)",
        "ring-soft": "var(--color-ring-soft)",

        // ---- legacy tier (existing components; same rendered values) ----
        bg: "var(--bg)",
        "bg-soft": "var(--bg-soft)",
        panel: "var(--panel)",
        "panel-strong": "var(--panel-strong)",
        text: "var(--text)",
        muted: "var(--muted)",
        "accent-deep": "var(--accent-deep)",
        primary: "var(--accent)",
        stroke: "var(--stroke)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
      },
      boxShadow: {
        soft: "var(--shadow-soft)",
        panel: "var(--shadow-panel)",
        pop: "var(--shadow-pop)",
        composer: "var(--shadow-soft)",
        editor: "var(--shadow-pop)",
      },
      // DEFAULT is what every bare `transition` / `transition-colors` /
      // `transition-[...]` falls back to when no duration or ease class is
      // given, so un-annotated transitions follow the motion tokens too.
      transitionTimingFunction: {
        DEFAULT: "var(--ease-out-soft)",
        "out-soft": "var(--ease-out-soft)",
        drawer: "var(--ease-drawer)",
      },
      transitionDuration: {
        DEFAULT: "var(--duration-fast)",
        fade: "var(--duration-fade)",
        fast: "var(--duration-fast)",
        quick: "var(--duration-quick)",
        base: "var(--duration-base)",
        panel: "var(--duration-panel)",
      },
      // Press-feedback scales (see pressableClass in shared/styles.ts).
      scale: {
        96: "0.96",
        97: "0.97",
      },
      gridTemplateRows: {
        // title bar · status banner slot (collapses to 0 when empty) · shell
        app: "calc(var(--titlebar-height) + 5px) auto minmax(0, 1fr)",
        chat: "55px minmax(0, 1fr)",
        conversation: "auto minmax(0, 1fr) auto",
      },
    },
  },
  plugins: [],
} satisfies Config;
