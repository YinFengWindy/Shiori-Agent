import type { ImageMetadata } from "astro";
import { getImage } from "astro:assets";
import { isGalleryPreview } from "./siteAssets";

/**
 * A picture the pages actually request. Built with Astro's image service
 * (`getImage`), so the original file is not copied into the build when
 * nothing reads its `.src`. Widths below are the layout's 2× size, capped
 * where a full 2× viewport would be the multi-hundred-kilobyte to multi-MB
 * responses that stall on the mainland CDN in front of the site.
 */
export interface DisplayImage {
  readonly src: string;
  readonly width: number;
  readonly height: number;
}

/** WebP quality for photographs and illustrations. Flat UI screenshots are left as committed. */
const PHOTO_QUALITY = 72;

async function emit(
  src: ImageMetadata,
  options: { width?: number; format: "webp" | "png"; quality?: number },
): Promise<DisplayImage> {
  const image = await getImage({ src, ...options });
  const width = Number(image.attributes.width);
  const height = Number(image.attributes.height);
  if (!image.src || !width || !height) throw new Error("the image service returned no picture");
  return { src: image.src, width, height };
}

/**
 * Time-of-day scene, full-bleed. 1920px wide is a 1× desktop and about 2×
 * on a laptop; wider than that is the transfer the CDN drops.
 */
export function sceneImage(src: ImageMetadata): Promise<DisplayImage> {
  return emit(src, { width: 1920, format: "webp", quality: 70 });
}

/**
 * 吟风's standing sprite. The file is already the size the stage shows
 * (826×1213 against a CSS height of at most 1152px), so this only
 * re-encodes it.
 */
export function spriteImage(src: ImageMetadata): Promise<DisplayImage> {
  return emit(src, { format: "webp", quality: 70 });
}

/**
 * Event CG beside 吟风. The frame is at most about 38rem by 56dvh, so 1280px
 * on the long side is 2×. Sources smaller than that are not enlarged.
 */
export function cgImage(src: ImageMetadata): Promise<DisplayImage> {
  return emit(src, { width: 1280, format: "webp", quality: PHOTO_QUALITY });
}

/**
 * The loader's illustration, full-viewport. The file is already 1920 wide;
 * this re-encodes it and does not enlarge a smaller source.
 */
export function loaderImage(src: ImageMetadata): Promise<DisplayImage> {
  return emit(src, { width: 1920, format: "webp", quality: PHOTO_QUALITY });
}

/**
 * Blog cover in the reading column (about 34rem, so 1280px is 2×). A cover
 * that is already a photo-strip preview is smaller than that on purpose and
 * is not passed here.
 */
export function coverImage(src: ImageMetadata): Promise<DisplayImage> {
  return emit(src, { width: 1280, format: "webp", quality: PHOTO_QUALITY });
}

/**
 * QQ group card. The card is 13.75rem wide, so the code is about 196 CSS px;
 * 642px is half of the 1284px screenshot (whole pixels) and about 3× the
 * card. PNG quality 100 quantises the flat screenshot without blurring the
 * modules, which a lossy photo encode would.
 */
export const QQ_QR_WIDTH = 642;

export function qrImage(src: ImageMetadata): Promise<DisplayImage> {
  return emit(src, { width: QQ_QR_WIDTH, format: "png", quality: 100 });
}

/** A post cover as the page shows it: a strip preview unchanged, anything else re-encoded. */
export async function displayedCover(cover: { image: ImageMetadata; alt: string }): Promise<DisplayImage & { alt: string }> {
  if (isGalleryPreview(cover.image)) {
    return { src: cover.image.src, width: cover.image.width, height: cover.image.height, alt: cover.alt };
  }
  const image = await coverImage(cover.image);
  return { ...image, alt: cover.alt };
}
