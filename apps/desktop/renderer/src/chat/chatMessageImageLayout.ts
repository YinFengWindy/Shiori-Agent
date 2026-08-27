export type ChatMessageImageSize = {
  width: number;
  height: number;
};

const maxChatMessageImageWidth = 420;
const maxChatMessageImageHeight = 280;

/** Calculates a bounded display size without enlarging or cropping the source image. */
export function fitChatMessageImage(image: ChatMessageImageSize): ChatMessageImageSize {
  if (image.width <= 0 || image.height <= 0) {
    return { width: 0, height: 0 };
  }

  const scale = Math.min(
    1,
    maxChatMessageImageWidth / image.width,
    maxChatMessageImageHeight / image.height,
  );
  return {
    width: Math.round(image.width * scale),
    height: Math.round(image.height * scale),
  };
}
