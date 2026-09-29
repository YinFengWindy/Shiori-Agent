export type ChatMessageImageSize = {
  width: number;
  height: number;
};

/** The desktop chat's largest attachment size. */
const chatMessageImageBounds: ChatMessageImageSize = { width: 420, height: 280 };

/**
 * Calculates a display size within `bounds` (the desktop chat's by default)
 * without enlarging or cropping the source image.
 */
export function fitChatMessageImage(image: ChatMessageImageSize, bounds = chatMessageImageBounds): ChatMessageImageSize {
  if (image.width <= 0 || image.height <= 0) {
    return { width: 0, height: 0 };
  }

  const scale = Math.min(
    1,
    bounds.width / image.width,
    bounds.height / image.height,
  );
  return {
    width: Math.round(image.width * scale),
    height: Math.round(image.height * scale),
  };
}
