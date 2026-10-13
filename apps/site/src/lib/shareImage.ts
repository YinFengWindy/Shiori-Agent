import type { ImageMetadata } from "astro";
import { getImage } from "astro:assets";
import { galleryArtOf, socialPreviewImage } from "./siteAssets";

/*
 * The picture a page is shared with (Open Graph / Twitter card, a post's
 * structured data). Link previewers crop to about 1.91:1 and some cannot
 * render WebP, so every share picture is a 1200×630 JPEG (#799).
 */

/** Size of every share picture, in pixels. */
export const SHARE_IMAGE_WIDTH = 1200;
export const SHARE_IMAGE_HEIGHT = 630;

/** A share picture: its site path, size and alt text. */
export interface ShareImage {
  readonly src: string;
  readonly width: number;
  readonly height: number;
  readonly alt: string;
}

/** The site's own share picture (`socialPreviewImage`): every page without one of its own. */
export const defaultShareImage: ShareImage = {
  src: socialPreviewImage.image.src,
  width: socialPreviewImage.image.width,
  height: socialPreviewImage.image.height,
  alt: socialPreviewImage.alt,
};

/**
 * A post's share picture: its cover, cover-cropped to 1200×630 and encoded
 * as JPEG at build time; the site's picture when it has no cover. A cover
 * from the photo strip's previews (480 px tall, too small for the card) is
 * made from the full-size art it was shrunk from; any other cover must be
 * large enough itself, as the image service never enlarges.
 */
export async function postShareImage(cover: { image: ImageMetadata; alt: string } | undefined): Promise<ShareImage> {
  if (!cover) return defaultShareImage;
  const source = galleryArtOf(cover.image) ?? cover.image;
  if (source.width < SHARE_IMAGE_WIDTH || source.height < SHARE_IMAGE_HEIGHT) {
    throw new Error(
      `a post cover's share picture is cropped from a picture of at least ${SHARE_IMAGE_WIDTH}×${SHARE_IMAGE_HEIGHT}; ${cover.image.src} is ${source.width}×${source.height}`,
    );
  }
  const image = await getImage({
    src: source,
    width: SHARE_IMAGE_WIDTH,
    height: SHARE_IMAGE_HEIGHT,
    fit: "cover",
    format: "jpg",
    quality: 82,
  });
  return { src: image.src, width: SHARE_IMAGE_WIDTH, height: SHARE_IMAGE_HEIGHT, alt: cover.alt };
}
