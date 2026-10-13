import { FileTextIcon, MagnifyingGlassIcon, TerminalWindowIcon } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { AbsoluteFill, Img, Sequence, useCurrentFrame } from "remotion";
import storyMenuShot from "../../../../assets/readme/story-menu.png";
import storySceneShot from "../../../../assets/readme/story-scene.png";
import mascotLaugh from "../../../desktop/renderer/src/shared/assets/mascot/yinfeng-laugh.webp";
import wallpaper from "../../../desktop/renderer/src/shared/assets/scene/bg-day.webp";
import generatedCg from "../../../site/src/assets/art/cg-3.webp";
import { CHAT_SHOT, ChatMessages } from "../chatShot";
import { cardStyle, Pill, Pop } from "../overlay";
import { progress, Screen, SCREEN_HEIGHT, SCREEN_WIDTH, Shot, useSeconds } from "../screen";

/** Frames one shot takes to fade over the previous one. */
const CROSSFADE = 10;

/** One shot of the clip, fading in over the shot before it. */
function FadeIn({ children }: { children: ReactNode }) {
  const frame = useCurrentFrame();
  return <AbsoluteFill style={{ opacity: progress(frame, 0, CROSSFADE) }}>{children}</AbsoluteFill>;
}

/** The feature name in the top-left corner of a shot. */
function Caption({ children }: { children: ReactNode }) {
  return (
    <Pop at={4} style={{ left: 40, bottom: 36 }}>
      <Pill style={{ fontSize: 22, padding: "10px 22px", fontWeight: 700, background: "var(--clip-paper)" }}>{children}</Pill>
    </Pop>
  );
}

const toolIcon = { size: 20, weight: "bold", color: "var(--clip-icon)" } as const;

/** The work shot: 吟风 answers, and the tools she used to get there stack up beside her reply. */
function ToolsShot() {
  const s = useSeconds();
  return (
    <Screen zoom={0.03} origin="40% 75%">
      <Shot src={CHAT_SHOT} />
      <ChatMessages appearAt={[-1, -1, -1, -1, -1, s(2.6)]} />
      <div style={{ position: "absolute", left: 340, top: 606, display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 8 }}>
        <Pop at={s(0.2)} outAt={s(2.4)} style={{ position: "relative" }}>
          <Pill icon={<FileTextIcon {...toolIcon} />}>读取文件 · 旅行清单.md</Pill>
        </Pop>
        <Pop at={s(0.7)} outAt={s(2.4)} style={{ position: "relative" }}>
          <Pill icon={<MagnifyingGlassIcon {...toolIcon} />}>搜索 · 河边银杏观赏期</Pill>
        </Pop>
        <Pop at={s(1.2)} outAt={s(2.4)} style={{ position: "relative" }}>
          <Pill icon={<TerminalWindowIcon {...toolIcon} />}>shell · 新建 今日散步 文件夹</Pill>
        </Pop>
      </div>
      <Caption>文件 · 搜索 · shell</Caption>
    </Screen>
  );
}

/** The story shots: the story menu, then a scene in play. */
function StoryShot({ src }: { src: string }) {
  return (
    <Screen zoom={0.05}>
      <Shot src={src} />
      <Caption>故事模式</Caption>
    </Screen>
  );
}

/** The desk pet and image generation shot: 吟风 on a desktop wallpaper, a speech bubble, and a picture she drew. */
function DeskShot() {
  const s = useSeconds();
  return (
    <Screen zoom={0.03} origin="100% 100%">
      <Img src={wallpaper} style={{ position: "absolute", inset: 0, width: SCREEN_WIDTH, height: SCREEN_HEIGHT, objectFit: "cover" }} />
      <Pop at={s(0.5)} rise={30} style={{ left: 150, top: 170 }}>
        <div style={{ ...cardStyle, padding: 10, borderRadius: "var(--radius-lg)", transform: "rotate(-3deg)" }}>
          <Img src={generatedCg} style={{ display: "block", width: 560, borderRadius: "var(--radius-md)" }} />
        </div>
      </Pop>
      <Pop at={s(0.2)} rise={50} style={{ right: 70, bottom: 0, width: 360 }}>
        <Img src={mascotLaugh} style={{ display: "block", width: "100%" }} />
      </Pop>
      <Pop at={s(1.0)} style={{ right: 300, bottom: 470 }}>
        <div style={{ ...cardStyle, padding: "12px 18px", fontSize: 20, borderRadius: "var(--radius-xl)" }}>画好啦，桌面也给你换上了～</div>
      </Pop>
      <Caption>桌宠 · 生图</Caption>
    </Screen>
  );
}

/**
 * 帮你做事与插件: four shots — tools at work in the chat, the story mode menu
 * and a story scene, then 吟风 as a desk pet beside a picture she generated.
 */
export function PluginsClip() {
  const s = useSeconds();
  return (
    <AbsoluteFill style={{ background: "var(--clip-paper)" }}>
      <Sequence durationInFrames={s(4) + CROSSFADE}>
        <ToolsShot />
      </Sequence>
      <Sequence from={s(4)} durationInFrames={s(2) + CROSSFADE}>
        <FadeIn>
          <StoryShot src={storyMenuShot} />
        </FadeIn>
      </Sequence>
      <Sequence from={s(6)} durationInFrames={s(2) + CROSSFADE}>
        <FadeIn>
          <StoryShot src={storySceneShot} />
        </FadeIn>
      </Sequence>
      <Sequence from={s(8)}>
        <FadeIn>
          <DeskShot />
        </FadeIn>
      </Sequence>
    </AbsoluteFill>
  );
}
