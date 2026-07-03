import { useEffect } from "react";
import { toFileUrl } from "../shared/format";

type ChatImageLightboxProps = {
  imagePath: string;
  open: boolean;
  onClose: () => void;
};

/** Renders the enlarged chat image preview dialog for the selected sidebar image. */
export function ChatImageLightbox({ imagePath, open, onClose }: ChatImageLightboxProps) {
  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleEscape(event: KeyboardEvent): void {
      if (event.key !== "Escape") return;
      event.preventDefault();
      onClose();
    }

    window.addEventListener("keydown", handleEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleEscape);
    };
  }, [onClose, open]);

  if (!open || !imagePath) {
    return null;
  }

  return (
    <div className="chat-image-lightbox fixed inset-0 z-40 flex items-center justify-center px-4 py-6">
      <button
        className="absolute inset-0 border-0 bg-[rgba(15,23,42,0.56)] p-0 backdrop-blur-[8px]"
        type="button"
        aria-label="关闭聊天图片预览"
        onClick={onClose}
      />
      <section
        className="relative z-[1] grid h-full max-h-[min(92vh,980px)] w-full max-w-[min(92vw,1400px)] min-h-0 min-w-0 place-items-center overflow-hidden rounded-[28px] bg-[rgba(255,255,255,0.98)] p-5 shadow-[0_32px_90px_rgba(15,23,42,0.22)]"
        role="dialog"
        aria-modal="true"
        aria-label="聊天图片放大预览"
      >
        <img
          className="block max-h-full max-w-full object-contain"
          src={toFileUrl(imagePath)}
          alt="enlarged chat preview"
        />
      </section>
    </div>
  );
}
