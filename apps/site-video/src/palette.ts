/**
 * The design tokens the clips draw with, as plain values: a Remotion
 * composition renders in its own page, without the desktop's styles.css.
 * Each one mirrors the primitive of the same name in
 * apps/desktop/renderer/src/styles.css (the single source); keep them in step.
 */
export const palette = {
  neutral50: "#fbf9fa",
  neutral100: "#f5f3f4",
  neutral200: "#e7e1e4",
  neutral600: "#83787e",
  neutral700: "#70666b",
  neutral900: "#3c3639",
  neutral950: "#272225",
  pink150: "#ffe5ed",
  pink300: "#ffb8d1",
  pink500: "#e6659c",
  pinkGrad: "#b93f76",
  blue150: "#dcf0ff",
  blue300: "#a6d6f9",
  blueGrad: "#1e79ad",
  lavender100: "#f6f1ff",
  lavender200: "#e9dcff",
  /** `--shadow-panel` */
  shadowPanel: "0 12px 40px rgba(95, 26, 58, 0.1)",
  /** `--shadow-soft` */
  shadowSoft: "0 2px 8px rgba(95, 26, 58, 0.05), 0 8px 24px rgba(95, 26, 58, 0.06)",
  /** `--gradient-accent-medium` */
  accentMedium: "linear-gradient(90deg, #a6d6f9, #ffb8d1)",
  /** `--gradient-accent` */
  accent: "linear-gradient(135deg, #dcf0ff, #ffe5ed)",
  /** `--radius-md` / `--radius-lg` / `--radius-xl` */
  radiusMd: 12,
  radiusLg: 16,
  radiusXl: 20,
} as const;

/** The app's UI font stack (what the screenshots were taken with on Windows). */
export const uiFont = '"Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", system-ui, sans-serif';
