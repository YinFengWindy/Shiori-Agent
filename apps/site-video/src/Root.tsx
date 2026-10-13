import type { ComponentType } from "react";
import { Composition } from "remotion";
import { SHOWCASE_CLIP_IDS, type ShowcaseClipId } from "../../site/src/content/showcase";
import { CLIP_FORMAT, CLIP_TIMING } from "./clips";
import { AffectionClip } from "./clips/AffectionClip";
import { ChannelsClip } from "./clips/ChannelsClip";
import { MemoryClip } from "./clips/MemoryClip";
import { PluginsClip } from "./clips/PluginsClip";
import { ProactiveClip } from "./clips/ProactiveClip";
// The design tokens first, then the clips' palette built from them.
import "../../desktop/renderer/src/tokens.css";
import "./clips.css";

const CLIP_COMPONENTS: Record<ShowcaseClipId, ComponentType> = {
  memory: MemoryClip,
  affection: AffectionClip,
  proactive: ProactiveClip,
  channels: ChannelsClip,
  plugins: PluginsClip,
};

/** One composition per demo clip (scripts/render.ts renders each). */
export function Root() {
  return (
    <>
      {SHOWCASE_CLIP_IDS.map((id) => (
        <Composition
          key={id}
          id={id}
          component={CLIP_COMPONENTS[id]}
          durationInFrames={Math.round(CLIP_TIMING[id].seconds * CLIP_FORMAT.fps)}
          {...CLIP_FORMAT}
        />
      ))}
    </>
  );
}
