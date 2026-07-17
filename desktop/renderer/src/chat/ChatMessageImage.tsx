import { useState } from "react";
import { toFileUrl } from "../shared/format";
import { fitChatMessageImage, type ChatMessageImageSize } from "./chatMessageImageLayout";

type ChatMessageImageProps = {
  imagePath: string;
};

/** Renders a chat attachment at a bounded size derived from its intrinsic dimensions. */
export function ChatMessageImage({ imagePath }: ChatMessageImageProps) {
  const [displaySize, setDisplaySize] = useState<ChatMessageImageSize | null>(null);

  return (
    <img
      className="block object-contain"
      src={toFileUrl(imagePath)}
      alt="message attachment"
      loading="lazy"
      decoding="async"
      style={displaySize ? { width: displaySize.width, height: displaySize.height } : { width: 1, height: 1, visibility: "hidden" }}
      onLoad={(event) => {
        const nextSize = fitChatMessageImage({
          width: event.currentTarget.naturalWidth,
          height: event.currentTarget.naturalHeight,
        });
        setDisplaySize((currentSize) => (
          currentSize?.width === nextSize.width && currentSize.height === nextSize.height
            ? currentSize
            : nextSize
        ));
      }}
    />
  );
}
