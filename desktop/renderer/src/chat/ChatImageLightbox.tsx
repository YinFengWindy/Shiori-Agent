import type React from "react";
import { useEffect, useRef, useState } from "react";
import { ArrowClockwise } from "@phosphor-icons/react";
import {
  clampChatImageOffset,
  fitChatImageToStage,
  type ChatImageLightboxSize,
} from "./chatImageLightboxLayout";
import { clampChatImageZoom, getNextChatImageZoom } from "./chatImageLightboxState";
import { toFileUrl } from "../shared/format";
import { DeleteIcon, LocateIcon } from "../shared/icons";

type ChatImageLightboxProps = {
  canAddToAssetLibrary: boolean;
  canGoToNext: boolean;
  canGoToPrevious: boolean;
  canLocateMessage: boolean;
  canRegenerate: boolean;
  imagePath: string;
  addingToAssetLibrary: boolean;
  regenerating: boolean;
  open: boolean;
  onAddToAssetLibrary: () => void;
  onClose: () => void;
  onGoToNext: () => void;
  onGoToPrevious: () => void;
  onLocateMessage: () => void;
  onRegenerate: () => void;
};

/** Renders the enlarged chat image preview dialog for the selected sidebar image. */
export function ChatImageLightbox({
  canAddToAssetLibrary,
  canGoToNext,
  canGoToPrevious,
  canLocateMessage,
  canRegenerate,
  imagePath,
  addingToAssetLibrary,
  regenerating,
  open,
  onAddToAssetLibrary,
  onClose,
  onGoToNext,
  onGoToPrevious,
  onLocateMessage,
  onRegenerate,
}: ChatImageLightboxProps) {
  const [zoom, setZoom] = useState(1);
  const [dragging, setDragging] = useState(false);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [imageNaturalSize, setImageNaturalSize] = useState<ChatImageLightboxSize>({ width: 0, height: 0 });
  const [stageSize, setStageSize] = useState<ChatImageLightboxSize>({ width: 0, height: 0 });
  const dragStateRef = useRef<{
    originX: number;
    originY: number;
    startX: number;
    startY: number;
  } | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const navigationButtonClass =
    "pointer-events-auto grid h-10 w-10 place-items-center rounded-full border border-transparent bg-transparent text-[#4B5563] transition hover:border-black hover:bg-white/92 hover:text-[#1F2937] focus:outline-none disabled:cursor-default disabled:opacity-40";
  const fittedImageSize = fitChatImageToStage(stageSize, imageNaturalSize);

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
    setOffset({ x: 0, y: 0 });
    dragStateRef.current = null;
    setDragging(false);
  }, [imagePath, open]);

  useEffect(() => {
    if (!open) return undefined;
    const stage = stageRef.current;
    if (!stage) return undefined;

    const updateStageSize = () => {
      const rect = stage.getBoundingClientRect();
      const nextSize = { width: rect.width, height: rect.height };
      setStageSize((currentSize) => (
        currentSize.width === nextSize.width && currentSize.height === nextSize.height
          ? currentSize
          : nextSize
      ));
    };

    updateStageSize();

    const resizeObserver = new ResizeObserver(() => updateStageSize());
    resizeObserver.observe(stage);
    window.addEventListener("resize", updateStageSize);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", updateStageSize);
    };
  }, [open]);

  useEffect(() => {
    setOffset((currentOffset) => {
      const nextOffset = clampChatImageOffset(currentOffset, stageSize, fittedImageSize, clampChatImageZoom(zoom));
      return currentOffset.x === nextOffset.x && currentOffset.y === nextOffset.y ? currentOffset : nextOffset;
    });
  }, [fittedImageSize, stageSize, zoom]);

  if (!open || !imagePath) {
    return null;
  }

  function handleWheel(event: React.WheelEvent<HTMLDivElement>): void {
    event.preventDefault();
    setZoom((currentZoom) => clampChatImageZoom(getNextChatImageZoom(currentZoom, event.deltaY)));
  }

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>): void {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragStateRef.current = {
      originX: offset.x,
      originY: offset.y,
      startX: event.clientX,
      startY: event.clientY,
    };
    setDragging(true);
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>): void {
    const dragState = dragStateRef.current;
    if (!dragState) return;

    const unclampedOffset = {
      x: dragState.originX + event.clientX - dragState.startX,
      y: dragState.originY + event.clientY - dragState.startY,
    };
    const nextOffset = clampChatImageOffset(unclampedOffset, stageSize, fittedImageSize, clampChatImageZoom(zoom));
    setOffset((currentOffset) => (
      currentOffset.x === nextOffset.x && currentOffset.y === nextOffset.y
        ? currentOffset
        : nextOffset
    ));
  }

  function stopDragging(): void {
    dragStateRef.current = null;
    setDragging(false);
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
        className="relative z-[1] grid h-full max-h-[min(92vh,980px)] w-full max-w-[min(92vw,1400px)] min-h-0 min-w-0 place-items-center overflow-hidden rounded-[28px] bg-[#F4F7FB] p-5 shadow-[0_32px_90px_rgba(15,23,42,0.22)]"
        role="dialog"
        aria-modal="true"
        aria-label="聊天图片放大预览"
      >
        <button
          className="absolute right-4 top-4 z-[3] grid h-10 w-10 place-items-center rounded-full border border-black/12 bg-white/94 text-[#272636] shadow-[0_10px_24px_rgba(15,23,42,0.12)] transition hover:border-black hover:bg-white"
          type="button"
          aria-label="关闭聊天图片弹层"
          onClick={onClose}
        >
          <DeleteIcon className="h-3.5 w-3.5 fill-current" />
        </button>
        <div
          ref={stageRef}
          className="relative grid h-full w-full min-h-0 min-w-0 place-items-center overflow-hidden rounded-[22px] bg-[#F4F7FB]"
          onWheel={handleWheel}
        >
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
            className={`grid h-full w-full min-h-0 min-w-0 place-items-center select-none ${dragging ? "cursor-grabbing" : "cursor-grab"}`}
            style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${clampChatImageZoom(zoom)})` }}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={stopDragging}
            onPointerCancel={stopDragging}
            onLostPointerCapture={stopDragging}
          >
            <img
              className="block object-contain"
              src={toFileUrl(imagePath)}
              alt="enlarged chat preview"
              style={{ width: fittedImageSize.width || undefined, height: fittedImageSize.height || undefined }}
              onLoad={(event) => {
                const nextSize = {
                  width: event.currentTarget.naturalWidth,
                  height: event.currentTarget.naturalHeight,
                };
                setImageNaturalSize((currentSize) => (
                  currentSize.width === nextSize.width && currentSize.height === nextSize.height
                    ? currentSize
                    : nextSize
                ));
              }}
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
          <div className="pointer-events-none absolute bottom-4 right-4 z-[2] flex items-center gap-3">
            <button
              className="pointer-events-auto grid h-11 w-11 place-items-center rounded-full border border-black/12 bg-white/94 text-[#272636] shadow-[0_10px_24px_rgba(15,23,42,0.12)] transition hover:border-black hover:bg-white disabled:cursor-default disabled:opacity-40"
              type="button"
              aria-label="重新生成图片"
              title="重新生成图片"
              onClick={onRegenerate}
              disabled={!canRegenerate || regenerating}
            >
              <ArrowClockwise className={`h-5 w-5 ${regenerating ? "animate-spin" : ""}`} weight="bold" />
            </button>
            <button
              className="pointer-events-auto grid h-11 w-11 place-items-center rounded-full border border-black/12 bg-white/94 text-[#272636] shadow-[0_10px_24px_rgba(15,23,42,0.12)] transition hover:border-black hover:bg-white disabled:cursor-default disabled:opacity-40"
              type="button"
              aria-label="定位到对应消息"
              onClick={onLocateMessage}
              disabled={!canLocateMessage}
            >
              <LocateIcon className="h-5 w-5 fill-current" />
            </button>
            <button
              className="pointer-events-auto grid h-11 w-11 place-items-center rounded-full border border-black/12 bg-white/94 text-[#272636] shadow-[0_10px_24px_rgba(15,23,42,0.12)] transition hover:border-black hover:bg-white disabled:cursor-default disabled:opacity-40"
              type="button"
              aria-label="加入素材库"
              onClick={onAddToAssetLibrary}
              disabled={!canAddToAssetLibrary || addingToAssetLibrary}
            >
              {addingToAssetLibrary ? (
                <span className="text-[11px] font-medium">...</span>
              ) : (
                <svg viewBox="0 0 1024 1024" className="h-5 w-5 fill-current" aria-hidden="true">
                  <path d="M881.29024 412.94848a28.16 28.16 0 0 0-28.16 28.16v111.06816c-53.1456-38.9888-118.13376-60.76416-185.78432-61.14816l-1.87392-0.00512c-105.81504 0-209.51552 50.47296-292.17792 142.2592-45.19936 50.18624-93.08672 76.47744-142.32576 78.13632-54.84544 1.95584-98.74432-27.41248-116.44416-41.42592V239.8208a15.83616 15.83616 0 0 1 15.8208-15.8208h509.35808a28.16 28.16 0 0 0 0-56.32H130.33984c-39.77728 0-72.1408 32.36352-72.1408 72.1408v598.12352c0 39.77728 32.36352 72.13568 72.1408 72.13568h706.9696c39.7824 0 72.14592-32.3584 72.14592-72.13568V441.10848a28.17024 28.17024 0 0 0-28.16512-28.16z m-43.98592 440.81152H130.33984a15.83616 15.83616 0 0 1-15.8208-15.81568v-100.49024c27.8016 15.50336 66.20672 30.36672 111.40096 30.36672 2.03264 0 4.08576-0.03072 6.14912-0.09216 65.41312-1.95584 127.01184-34.5088 183.07584-96.75776 71.84384-79.7696 160.68096-123.62752 250.3424-123.62752h1.55136c71.94624 0.40448 137.6 28.60032 186.10176 79.5392v211.06176a15.85664 15.85664 0 0 1-15.83616 15.81568z" />
                  <path d="M193.4336 457.51808c0 64.0256 52.09088 116.11648 116.1216 116.11648 64.0256 0 116.11648-52.09088 116.11648-116.11648S373.5808 341.4016 309.5552 341.4016c-64.03072 0-116.1216 52.09088-116.1216 116.11648z m175.91808 0c0 32.9728-26.82368 59.79648-59.79648 59.79648s-59.8016-26.82368-59.8016-59.79648S276.5824 397.7216 309.5552 397.7216c32.9728 0 59.79648 26.82368 59.79648 59.79648zM962.39616 211.87584H869.2224V118.70208c0-18.46784-13.5168-33.44384-30.1824-33.44384s-30.1824 14.976-30.1824 33.44384v93.17376h-93.17376c-18.46784 0-33.44384 13.5168-33.44384 30.1824s14.976 30.1824 33.44384 30.1824h93.17376V365.4144c0 18.46784 13.5168 33.44384 30.1824 33.44384s30.1824-14.976 30.1824-33.44384V272.24064h93.17376c18.46784 0 33.44384-13.5168 33.44384-30.1824s-14.976-30.1824-33.44384-30.1824z" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
