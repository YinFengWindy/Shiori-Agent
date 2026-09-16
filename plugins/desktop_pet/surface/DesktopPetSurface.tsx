import { useCallback, useEffect, useRef, useState } from "react";
import { openPetContextMenu } from "./petMenu";
import { CodexSpritePetRenderer } from "./CodexSpritePetRenderer";
import {
  isSamePetBubbleExtension,
  noPetBubble,
  petBubbleSurfaceExtension,
  resolvePetBubblePlacement,
  type PetBubblePlacement,
} from "./bubbleExtension";
import { type SpriteState } from "./spriteContract";
import { usePetActivityState } from "./usePetActivityState";
import {
  petSurfaceLoadSignature,
  readPetSurfaceMessage,
  readPetSurfaceState,
  type PetSurfaceLoad,
} from "./surfaceState";
import type {
  PluginSurfaceComponentProps,
  SurfacePlacement,
} from "../../../apps/desktop/renderer/src/surface/pluginSurfaceRegistry";
import { emptyPetReply, type PetReplyBubble } from "../shared/replyBubble";
import type { VoiceStatePayload } from "../../../apps/desktop/src/bridge/shared";

const defaultVoice: VoiceStatePayload = { status: "idle" };
const noExtension = { side: "below" as const, size: 0 };

/**
 * The desktop pet, as a plugin-owned surface.
 *
 * Everything about the window itself goes through `props.surface`: the host
 * creates and drives it and never learns that it contains a pet. Three details
 * are worth knowing before editing:
 *
 * - **Retained vs transient.** Package, sprite state and reply arrive as
 *   one retained `onState` payload that the host replays after `ready()`. A
 *   surface renderer mounts asynchronously and can reload at any time, and on
 *   a transparent window "blank" and "broken" look identical — so nothing the
 *   pet must still be showing may travel by `onMessage`, which is one-shot.
 * - **The bubble sizes the window, and the window feeds the bubble.** The host
 *   reports a settled placement, the plugin decides which side the bubble goes
 *   on and asks for an extension, and that request settles the surface again.
 *   The request is therefore deduplicated, or the two would ping-pong.
 * - **No per-frame anything.** The pet never tells the host where it is; the
 *   host tells the pet, and only once the motion stops.
 */
export function DesktopPetSurface({ surface, client }: PluginSurfaceComponentProps) {
  const [load, setLoad] = useState<PetSurfaceLoad | null>(null);
  const [state, setState] = useState<SpriteState>("idle");
  const [transientState, setTransientState] = useState<SpriteState | null>(null);
  const [reply, setReply] = useState<PetReplyBubble>(emptyPetReply);
  const [bubbleLayout, setBubbleLayout] = useState<PetBubblePlacement>(noPetBubble);
  const [voice, setVoice] = useState<VoiceStatePayload>(defaultVoice);
  const activityState = usePetActivityState(state);
  const onTransientFinished = useCallback(() => setTransientState(null), []);

  const placementRef = useRef<SurfacePlacement | null>(null);
  const bubbleHeightRef = useRef(0);
  const appliedExtensionRef = useRef<{ side: "above" | "below"; size: number }>(noExtension);
  const loadSignatureRef = useRef<string | null>(null);

  /**
   * Re-derives the bubble side from the latest placement and measured height.
   *
   * Called from both inputs because either can change alone: the pet can be
   * thrown to the bottom of the screen with the same bubble, or grow a longer
   * bubble without moving.
   */
  const syncBubble = useCallback(() => {
    const placement = placementRef.current;
    if (!placement) return;
    const next = resolvePetBubblePlacement(
      placement.anchor.y,
      placement.workArea,
      bubbleHeightRef.current,
    );
    setBubbleLayout((current) => (
      current.placement === next.placement && current.height === next.height ? current : next
    ));
    const extension = petBubbleSurfaceExtension(next);
    // `setExtension` settles the surface, which pushes a fresh placement, which
    // lands back here. Without this guard that is an endless resize loop.
    if (isSamePetBubbleExtension(appliedExtensionRef.current, extension)) return;
    appliedExtensionRef.current = extension;
    surface.setExtension(extension);
  }, [surface]);

  const onBubbleHeight = useCallback((height: number) => {
    const measured = Number.isFinite(height) ? Math.max(0, Math.ceil(height)) : 0;
    if (measured === bubbleHeightRef.current) return;
    bubbleHeightRef.current = measured;
    syncBubble();
  }, [syncBubble]);

  useEffect(() => {
    const offState = surface.onState((value) => {
      const next = readPetSurfaceState(value);
      if (!next) return;
      const signature = petSurfaceLoadSignature(next.load);
      // Reply updates re-send the whole retained payload, so the sprite
      // state may only be reset when the *package* actually changed — otherwise
      // every bubble would cancel a running animation.
      if (loadSignatureRef.current !== signature) {
        loadSignatureRef.current = signature;
        setLoad(next.load);
        setState(next.load.state);
        setTransientState(null);
      }
      setReply(next.reply ?? emptyPetReply);
    });
    const offMessage = surface.onMessage((value) => {
      const play = readPetSurfaceMessage(value);
      if (!play) return;
      if (play.transient) {
        setTransientState(play.state);
        return;
      }
      setState(play.state);
      setTransientState(null);
    });
    const offPlacement = surface.onPlacement((placement) => {
      placementRef.current = placement;
      syncBubble();
    });
    // TEMPORARY COUPLING: voice stays a host feature (#221); see petMenu.ts and
    // useCodexPetInteraction.ts for the other two.
    const offVoice = window.miraDesktop.onVoiceState((next) => {
      if (isVoiceState(next)) setVoice(next);
    });
    // Tells the host to replay the retained state and the current placement.
    // Without this the pet comes up as an empty transparent rectangle whenever
    // it mounts after its state was set.
    surface.ready();
    return () => {
      offState();
      offMessage();
      offPlacement();
      offVoice();
    };
  }, [surface, syncBubble]);

  if (!load) return null;
  return (
    <CodexSpritePetRenderer
      spritesheetUrl={load.package.spritesheetUrl}
      state={activityState}
      transientState={transientState}
      onTransientFinished={onTransientFinished}
      reply={reply}
      onDismissBubble={() => { void client.call("bubble.dismiss"); }}
      bubbleLayout={bubbleLayout}
      voice={voice}
      surface={surface}
      onContextMenu={() => { void openPetContextMenu(surface, client).catch((error: unknown) => console.error("[desktop_pet] 菜单操作失败", error)); }}
      onBubbleHeight={onBubbleHeight}
    />
  );
}

function isVoiceState(value: unknown): value is VoiceStatePayload {
  if (!value || typeof value !== "object") return false;
  const status = (value as { status?: unknown }).status;
  return status === "idle"
    || status === "press_pending"
    || status === "dragging"
    || status === "recording"
    || status === "transcribing"
    || status === "sending"
    || status === "waiting_reply"
    || status === "speaking_prepare"
    || status === "speaking"
    || status === "finish_current_sentence_then_idle"
    || status === "error";
}
