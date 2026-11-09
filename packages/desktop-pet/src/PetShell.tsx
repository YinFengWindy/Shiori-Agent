import React from "react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { X } from "@phosphor-icons/react";
import type { SurfaceHandle, SurfacePlacement } from "@yinfengwindy/shiori-sdk";
import { usePetInteraction } from "./usePetInteraction";
import { isSamePetBubbleExtension, noPetBubble, petBubbleSurfaceExtension, resolvePetBubblePlacement } from "./bubbleExtension";
import type { PetPointerState } from "./interactionContract";
import type { PetPresentationState } from "./protocol";

/** Shared desktop window chrome; providers supply only the model drawing. */
export function PetShell({ surface, body, state, children }: {
  surface: SurfaceHandle;
  body: { width: number; height: number };
  state: PetPresentationState;
  children: (pointer: PetPointerState | null) => ReactNode;
}) {
  const interaction = usePetInteraction(surface);
  const [layout, setLayout] = useState(noPetBubble);
  const placement = useRef<SurfacePlacement | null>(null);
  const height = useRef(0);
  const extension = useRef({ side: "below" as "above" | "below", size: 0 });
  const voiceText = state.voice.status === "recording" ? "我在听"
    : ["transcribing", "sending", "waiting_reply", "speaking_prepare"].includes(state.voice.status) ? "正在理解"
      : state.voice.status === "error" ? state.voice.message || "没听清，再试一次" : "";
  const text = voiceText || state.reply.text;
  const sync = useCallback(() => {
    if (!placement.current) return;
    const next = resolvePetBubblePlacement(placement.current.anchor.y, placement.current.workArea, height.current, body.height);
    setLayout((current) => current.height === next.height && current.placement === next.placement ? current : next);
    const nextExtension = petBubbleSurfaceExtension(next);
    if (isSamePetBubbleExtension(extension.current, nextExtension)) return;
    extension.current = nextExtension;
    surface.setExtension(nextExtension);
  }, [body.height, surface]);
  const measured = useCallback((value: number) => {
    height.current = Number.isFinite(value) ? Math.max(0, Math.ceil(value)) : 0;
    sync();
  }, [sync]);
  useEffect(() => {
    const unsubscribe = surface.onPlacement((next) => { placement.current = next; sync(); });
    // The model's retained state mounts this shell after the outer surface's first
    // ready replay. Subscribe first, then request the current placement again.
    surface.ready();
    return unsubscribe;
  }, [surface, sync]);
  useEffect(() => { if (!text) measured(0); }, [text, measured]);
  const menu = async () => {
    const choice = await surface.showContextMenu([
      { id: "voice.stop", label: "停止语音" },
      { id: "main", label: "显示主窗口" },
      { id: "hide", label: "隐藏桌宠" },
    ]);
    if (choice === "main") surface.activateMainWindow();
    else if (choice === "voice.stop" || choice === "hide") surface.postToBackground({ kind: choice });
  };
  return <div className={text ? `pet-surface pet-bubble-${layout.placement}` : "pet-surface"}>
    {text ? <PetBubble text={text} height={layout.height} persistent={!voiceText && state.reply.persistent} onHeight={measured} onDismiss={() => surface.postToBackground({ kind: "bubble.dismiss" })} /> : null}
    <div aria-label="桌宠" className={interaction.isDragging ? "pet-drag-region pet-dragging" : "pet-drag-region"}
      {...interaction.pointerHandlers} onLostPointerCapture={interaction.pointerHandlers.onPointerCancel}
      onContextMenu={(event) => { event.preventDefault(); void menu().catch((error: unknown) => console.error("[pet] 菜单操作失败", error)); }}
      style={{ width: body.width, height: body.height }}>
      {children(interaction.interactionState)}
    </div>
  </div>;
}

function PetBubble({ text, height, persistent, onHeight, onDismiss }: { text: string; height: number; persistent: boolean; onHeight: (height: number) => void; onDismiss: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => onHeight(element.scrollHeight);
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(element);
    return () => observer?.disconnect();
  }, [text, persistent, onHeight]);
  return <div ref={ref} className="pet-bubble" role="status" style={height > 0 ? { maxHeight: height } : undefined}>
    <span>{text}</span>
    {persistent ? <button type="button" className="pet-bubble-dismiss" aria-label="关闭消息" title="关闭消息" onPointerDown={(event) => event.stopPropagation()} onClick={onDismiss}><X size={12} weight="bold" /></button> : null}
  </div>;
}
