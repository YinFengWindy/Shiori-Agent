/** Public, metadata-free exports selected from Yinfeng's character and daily artwork. */
export const demoAvatar = new URL("./assets/yinfeng-avatar.webp", import.meta.url).href;

/** The five Story illustrations, bundled locally and unlocked in narrative order. */
export const storyArtwork = {
  rain: new URL("./assets/yinfeng-rain-window.webp", import.meta.url).href,
  sunset: new URL("./assets/yinfeng-sunset-window.webp", import.meta.url).href,
  desk: new URL("./assets/yinfeng-lamplit-desk.webp", import.meta.url).href,
  walk: new URL("./assets/yinfeng-night-walk.webp", import.meta.url).href,
  fireworks: new URL("./assets/yinfeng-fireworks.webp", import.meta.url).href,
};

/** The opening visual also used by fixture restoration checks. */
export const demoBackdrop = storyArtwork.rain;

/** Every trusted character asset available to shared renderer views. */
export const showcasePublicAssets = new Set([demoAvatar, ...Object.values(storyArtwork)]);
