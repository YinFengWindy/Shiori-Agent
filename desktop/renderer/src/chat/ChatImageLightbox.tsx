import type React from "react";
import { useEffect, useState } from "react";
import { clampChatImageZoom, getNextChatImageZoom } from "./chatImageLightboxState";
import { toFileUrl } from "../shared/format";

type ChatImageLightboxProps = {
  canGoToNext: boolean;
  canGoToPrevious: boolean;
  imagePath: string;
  open: boolean;
  onClose: () => void;
  onGoToNext: () => void;
  onGoToPrevious: () => void;
};

/** Renders the enlarged chat image preview dialog for the selected sidebar image. */
export function ChatImageLightbox({
  canGoToNext,
  canGoToPrevious,
  imagePath,
  open,
  onClose,
  onGoToNext,
  onGoToPrevious,
}: ChatImageLightboxProps) {
  const [zoom, setZoom] = useState(1);
  const navigationButtonClass =
    "pointer-events-auto grid h-10 w-10 place-items-center rounded-full border border-transparent bg-transparent text-[#4B5563] transition hover:border-black hover:bg-white/92 hover:text-[#1F2937] focus:outline-none disabled:cursor-default disabled:opacity-40";

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleEscape(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key === "ArrowLeft" && canGoToPrevious) {
        event.preventDefault();
        onGoToPrevious();
        return;
      }
      if (event.key === "ArrowRight" && canGoToNext) {
        event.preventDefault();
        onGoToNext();
      }
    }

    window.addEventListener("keydown", handleEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleEscape);
    };
  }, [canGoToNext, canGoToPrevious, onClose, onGoToNext, onGoToPrevious, open]);

  useEffect(() => {
    if (!open) return;
    setZoom(1);
  }, [imagePath, open]);

  if (!open || !imagePath) {
    return null;
  }

  function handleWheel(event: React.WheelEvent<HTMLDivElement>): void {
    event.preventDefault();
    setZoom((currentZoom) => getNextChatImageZoom(currentZoom, event.deltaY));
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
        <div className="relative grid h-full w-full min-h-0 min-w-0 place-items-center overflow-hidden rounded-[22px] bg-[#F4F7FB]" onWheel={handleWheel}>
          <div className="pointer-events-none absolute inset-y-0 left-0 z-[2] flex items-center pl-4">
            <button
              className={navigationButtonClass}
              type="button"
              aria-label="查看上一张聊天图片"
              onClick={onGoToPrevious}
              disabled={!canGoToPrevious}
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="m15 18-6-6 6-6" />
              </svg>
            </button>
          </div>
          <div
            className="grid h-full w-full min-h-0 min-w-0 place-items-center transition-transform duration-150"
            style={{ transform: `scale(${clampChatImageZoom(zoom)})` }}
          >
            <img
              className="block h-full w-full min-h-0 min-w-0 object-contain"
              src={toFileUrl(imagePath)}
              alt="enlarged chat preview"
            />
          </div>
          <div className="pointer-events-none absolute inset-y-0 right-0 z-[2] flex items-center pr-4">
            <button
              className={navigationButtonClass}
              type="button"
              aria-label="查看下一张聊天图片"
              onClick={onGoToNext}
              disabled={!canGoToNext}
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="m9 18 6-6-6-6" />
              </svg>
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
