const storyMenuThemeSampleSize = 32;
const baseCommandHue = 329;

/** One RGB color sampled from a Story backdrop. */
export type StoryMenuRgb = {
  r: number;
  g: number;
  b: number;
};

/** Dynamic visual adjustments applied to the Story launcher controls. */
export type StoryMenuTheme = {
  commandFilter: string;
  titleHighlight: string;
};

/** Dependencies used to keep browser image and canvas work isolated from color math. */
export type StoryMenuThemeResolverDependencies = {
  createImage?: () => HTMLImageElement;
  createCanvas?: () => HTMLCanvasElement;
};

/** Neutral theme used before sampling finishes or when browser pixel access is unavailable. */
export const DEFAULT_STORY_MENU_THEME: StoryMenuTheme = {
  commandFilter: "none",
  titleHighlight: "rgba(255,255,255,0.35)",
};

/** Picks the most common saturated color from a small RGBA pixel sample. */
export function extractDominantStoryMenuColor(pixels: ArrayLike<number>): StoryMenuRgb | null {
  const buckets = new Map<string, { color: StoryMenuRgb; weight: number }>();
  for (let index = 0; index + 3 < pixels.length; index += 4) {
    const alpha = pixels[index + 3] ?? 0;
    if (alpha < 128) continue;
    const red = pixels[index] ?? 0;
    const green = pixels[index + 1] ?? 0;
    const blue = pixels[index + 2] ?? 0;
    const maximum = Math.max(red, green, blue);
    const minimum = Math.min(red, green, blue);
    const saturation = maximum ? (maximum - minimum) / maximum : 0;
    if (saturation < 0.14 || maximum < 20 || minimum > 246) continue;

    const color = {
      r: quantizeColorChannel(red),
      g: quantizeColorChannel(green),
      b: quantizeColorChannel(blue),
    };
    const key = `${color.r},${color.g},${color.b}`;
    const bucket = buckets.get(key) ?? { color, weight: 0 };
    bucket.weight += 1 + saturation * 2;
    buckets.set(key, bucket);
  }

  let winner: { color: StoryMenuRgb; weight: number } | null = null;
  for (const bucket of buckets.values()) {
    if (!winner || bucket.weight > winner.weight) winner = bucket;
  }
  return winner?.color ?? null;
}

/** Maps an RGB accent to a hue-shifted launcher theme while preserving readable contrast. */
export function createStoryMenuTheme(color: StoryMenuRgb): StoryMenuTheme {
  const hue = rgbToHue(color);
  const hueRotation = Math.round(shortestHueDelta(baseCommandHue, hue));
  const saturation = Math.min(1.8, Math.max(0.85, 0.85 + rgbSaturation(color) * 0.9));
  return {
    commandFilter: `hue-rotate(${hueRotation}deg) saturate(${saturation.toFixed(2)})`,
    titleHighlight: `rgba(${color.r},${color.g},${color.b},0.35)`,
  };
}

/** Samples the selected backdrop and resolves its launcher theme, falling back on browser read failures. */
export function resolveStoryMenuTheme(
  assetUrl: string,
  dependencies: StoryMenuThemeResolverDependencies = {},
): Promise<StoryMenuTheme> {
  if (!assetUrl || typeof document === "undefined") return Promise.resolve(DEFAULT_STORY_MENU_THEME);

  return new Promise((resolve) => {
    const image = dependencies.createImage?.() ?? createDefaultStoryMenuImage();
    const settle = (theme: StoryMenuTheme) => resolve(theme);
    image.onload = () => {
      try {
        const canvas = dependencies.createCanvas?.() ?? document.createElement("canvas");
        canvas.width = storyMenuThemeSampleSize;
        canvas.height = storyMenuThemeSampleSize;
        const context = canvas.getContext("2d", { willReadFrequently: true });
        if (!context) {
          settle(DEFAULT_STORY_MENU_THEME);
          return;
        }
        context.drawImage(image, 0, 0, storyMenuThemeSampleSize, storyMenuThemeSampleSize);
        const color = extractDominantStoryMenuColor(
          context.getImageData(0, 0, storyMenuThemeSampleSize, storyMenuThemeSampleSize).data,
        );
        settle(color ? createStoryMenuTheme(color) : DEFAULT_STORY_MENU_THEME);
      } catch {
        settle(DEFAULT_STORY_MENU_THEME);
      }
    };
    image.onerror = () => settle(DEFAULT_STORY_MENU_THEME);
    image.src = assetUrl;
  });
}

function createDefaultStoryMenuImage(): HTMLImageElement {
  const image = new Image();
  image.crossOrigin = "anonymous";
  return image;
}

function quantizeColorChannel(value: number): number {
  return Math.min(255, Math.round(value / 32) * 32);
}

function rgbSaturation(color: StoryMenuRgb): number {
  const maximum = Math.max(color.r, color.g, color.b);
  const minimum = Math.min(color.r, color.g, color.b);
  return maximum ? (maximum - minimum) / maximum : 0;
}

function rgbToHue(color: StoryMenuRgb): number {
  const red = color.r / 255;
  const green = color.g / 255;
  const blue = color.b / 255;
  const maximum = Math.max(red, green, blue);
  const minimum = Math.min(red, green, blue);
  const delta = maximum - minimum;
  if (delta === 0) return baseCommandHue;
  if (maximum === red) return 60 * (((green - blue) / delta) % 6);
  if (maximum === green) return 60 * ((blue - red) / delta + 2);
  return 60 * ((red - green) / delta + 4);
}

function shortestHueDelta(from: number, to: number): number {
  return ((to - from + 540) % 360) - 180;
}
