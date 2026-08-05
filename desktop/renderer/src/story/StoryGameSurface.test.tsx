/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryGameSurface } from "./StoryGameSurface";
import { createStoryDetails } from "./testFixtures";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

const resolvedBackground: StoryMenuBackground = {
  url: "shiori-asset://local/story-menu-random.webp",
  theme: {
    commandFilter: "hue-rotate(18deg) saturate(1.12)",
    titleHighlight: "rgba(224,96,160,0.35)",
  },
};

describe("StoryGameSurface", () => {
  it("renders the active Story as a visual-novel stage with dialogue and player input", () => {
    const markup = renderToStaticMarkup(<StoryGameSurface background={resolvedBackground} story={createStoryDetails()} busy={false} error="" characterAvatarUrl="shiori-asset://local/role" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);
    assert.match(markup, /data-testid="story-game-surface"/);
    assert.match(markup, /data-dialogue-visible="true"/);
    assert.match(markup, /url\(shiori-asset:\/\/local\/story-menu-random\.webp\)/);
    assert.match(markup, />你终于来了。</);
    assert.match(markup, /data-testid="story-current-time"/);
    assert.match(markup, /2026年8月2日/);
    assert.match(markup, />上午</);
    assert.doesNotMatch(markup, /aria-label="提交剧情行动"/);
    assert.match(markup, /placeholder="写下你的行动或回应\.\.\."/);
    assert.match(markup, /aria-label="查看剧情记录"/);
    assert.match(markup, /data-testid="story-dialogue-panel"/);
    assert.match(markup, /data-testid="story-dialogue-text"/);
    assert.match(markup, /story-game-chrome story-game-readable/);
    assert.match(markup, /story-game-control story-game-readable/);
    assert.match(markup, /story-game-readable m-0 min-h-14/);
    assert.match(markup, /color-mix\(in srgb, rgba\(224,96,160,0.35\) 40%, transparent\)/);
    assert.match(markup, /backdrop-blur-xl/);
    assert.match(markup, /backdrop-saturate-150/);
    assert.doesNotMatch(markup, /剧情正在生成/);
    assert.doesNotMatch(markup, /rgba\(13,20,25/);
    assert.doesNotMatch(markup, /data-testid="story-game-character"/);
  });

  it("uses the Story-owned background resource when it is ready", () => {
    const markup = renderToStaticMarkup(<StoryGameSurface characterAvatarUrl="shiori-asset://local/role" story={createStoryDetails({ backgroundResource: { id: "resource-1", storyId: "story-1", kind: "background", visualType: "scene", status: "ready", path: "D:\\stories\\opening.png", prompt: "anime screencap", sourceTurnId: "turn-1", sequence: 1, errorCode: null, createdAt: "", updatedAt: "" } })} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);
    assert.match(markup, /data-testid="story-game-backdrop"/);
    assert.match(markup, /shiori-asset:\/\/local\/unavailable/);
    assert.match(markup, /data-testid="story-game-character"/);
    assert.match(markup, /shiori-asset:\/\/local\/role/);
    assert.match(markup, /-bottom-6 right-\[clamp\(4vw,10vw,12rem\)\] z-10/);
    assert.match(markup, /h-\[min\(78vh,52rem\)\] max-w-\[48vw\]/);
    assert.match(markup, /origin-bottom-right scale-120/);
    assert.match(markup, /bottom-0 z-20/);
    assert.doesNotMatch(markup, /default-galgame-bg\.png/);
  });

  it("uses the latest ready progression CG as the active stage visual", () => {
    const markup = renderToStaticMarkup(<StoryGameSurface characterAvatarUrl="shiori-asset://local/role" story={createStoryDetails({
      cgGallery: [
        { id: "resource-1", storyId: "story-1", kind: "cg", visualType: "scene", status: "ready", path: "D:\\stories\\scene-1.png", prompt: "scene one", sourceTurnId: "turn-2", sequence: 1, errorCode: null, createdAt: "", updatedAt: "" },
        { id: "resource-2", storyId: "story-1", kind: "cg", visualType: "character", status: "ready", path: "D:\\stories\\scene-2.png", prompt: "scene two", sourceTurnId: "turn-3", sequence: 2, errorCode: null, createdAt: "", updatedAt: "" },
      ],
    })} busy={false} error="" onSubmitInput={async () => true} onRegenerateCg={() => undefined} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.match(markup, /shiori-asset:\/\/local\/unavailable/);
    assert.match(markup, /aria-label="重新生成当前 CG"/);
    assert.doesNotMatch(markup, /scene-1\.png/);
    assert.doesNotMatch(markup, /data-testid="story-game-character"/);
    assert.doesNotMatch(markup, /default-galgame-bg\.png/);
  });

  it("keeps the previous CG visible while its replacement is generating", () => {
    const markup = renderToStaticMarkup(<StoryGameSurface characterAvatarUrl="shiori-asset://local/role" story={createStoryDetails({
      cgGallery: [
        { id: "resource-1", storyId: "story-1", kind: "cg", visualType: "scene", status: "generating", path: "D:\\stories\\scene-old.png", prompt: "scene", sourceTurnId: "turn-2", sequence: 1, errorCode: null, createdAt: "", updatedAt: "" },
      ],
    })} busy={false} error="" onSubmitInput={async () => true} onRegenerateCg={() => undefined} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.match(markup, /shiori-asset:\/\/local\/unavailable/);
    assert.match(markup, /aria-label="重新生成当前 CG"/);
    assert.doesNotMatch(markup, /default-galgame-bg\.png/);
  });

  it("does not overlay the role difference while a CG is active", () => {
    const markup = renderToStaticMarkup(<StoryGameSurface characterAvatarUrl="shiori-asset://local/role" story={createStoryDetails({
      cgGallery: [
        { id: "resource-1", storyId: "story-1", kind: "cg", visualType: "scene", status: "ready", path: "D:\\stories\\scene.png", prompt: "girl feeding man", sourceTurnId: "turn-2", sequence: 1, errorCode: null, createdAt: "", updatedAt: "" },
      ],
    })} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.doesNotMatch(markup, /data-testid="story-game-character"/);
  });

  it("falls back to the shared Story background when no Story CG is ready", () => {
    const markup = renderToStaticMarkup(<StoryGameSurface background={resolvedBackground} story={createStoryDetails()} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.match(markup, /url\(shiori-asset:\/\/local\/story-menu-random\.webp\)/);
    assert.doesNotMatch(markup, /default-galgame-bg\.png/);
  });

  it("replaces the dialogue with one generation state and hides player input while busy", () => {
    const markup = renderToStaticMarkup(<StoryGameSurface story={createStoryDetails()} busy error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.match(markup, />剧情生成中\.\.\.</);
    assert.doesNotMatch(markup, />你终于来了。</);
    assert.doesNotMatch(markup, /data-testid="story-player-input"/);
    assert.doesNotMatch(markup, /剧情正在生成。/);
  });

  it("distinguishes narration from dialogue in the normal game surface", () => {
    const story = createStoryDetails({ beats: [{ ...createStoryDetails().beats[0], text: "她嘴上凶着，却伸手把你碗里凉掉的汤换成了自己手边那碗还温着的。玫粉色的眼睛低垂着，声音细得像抱怨：“……吃快点，凉了又该胃疼了。”", speaker: "澪", kind: "narration" }] });
    const markup = renderToStaticMarkup(<StoryGameSurface story={story} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.match(markup, /data-story-fragment-kind="narration"/);
    assert.match(markup, />旁白</);
    assert.match(markup, /她嘴上凶着/);
    assert.doesNotMatch(markup, /data-testid="story-player-input"/);
  });

  it("uses the frozen Story role name for legacy generic dialogue speakers", () => {
    const story = createStoryDetails({ beats: [{ ...createStoryDetails().beats[0], speaker: "角色" }] });
    const markup = renderToStaticMarkup(<StoryGameSurface story={story} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.match(markup, />澪</);
    assert.doesNotMatch(markup, />角色</);
  });
});
