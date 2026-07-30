import { Texture } from "pixi.js";
import type { WorldAssetLoader } from "./worldAssetManager";

export const maxWorldTextureDimension = 4096;

/** Decodes one controlled local image into a Pixi texture with a hard GPU-size guard. */
export const loadPixiWorldTexture: WorldAssetLoader<Texture> = (entry, { signal }) => (
  new Promise((resolve, reject) => {
    const image = new Image();
    const cleanup = () => {
      image.onload = null;
      image.onerror = null;
      signal.removeEventListener("abort", abort);
    };
    const abort = () => {
      image.src = "";
      cleanup();
      reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
    };
    image.onload = () => {
      cleanup();
      if (image.naturalWidth > maxWorldTextureDimension || image.naturalHeight > maxWorldTextureDimension) {
        reject(new Error(`world asset ${entry.id} exceeds ${maxWorldTextureDimension}px`));
        return;
      }
      resolve({
        asset: Texture.from(image, true),
        sizeBytes: image.naturalWidth * image.naturalHeight * 4,
      });
    };
    image.onerror = () => {
      cleanup();
      reject(new Error(`world asset ${entry.id} could not be decoded`));
    };
    signal.addEventListener("abort", abort, { once: true });
    image.src = entry.url;
  })
);
