/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider } from "@yinfengwindy/shiori-sdk";
import { createFakeHostServices, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { StoryGameSurface } from "./StoryGameSurface";
import { createStoryBeat, createStoryDetails, renderStoryMarkup } from "./testFixtures";
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
    const markup = renderStoryMarkup(<StoryGameSurface background={resolvedBackground} story={createStoryDetails()} busy={false} error="" characterAvatarUrl="shiori-asset://local/role" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);
    assert.match(markup, /data-testid="story-game-surface"/);
    assert.match(markup, /data-dialogue-visible="true"/);
    assert.match(markup, />你终于来了。</);
    assert.match(markup, /data-testid="story-current-time"/);
    assert.match(markup, /2026年8月2日/);
    assert.match(markup, />上午</);
    assert.doesNotMatch(markup, /aria-label="提交剧情行动"/);
    assert.match(markup, /aria-label="查看剧情记录"/);
    assert.match(markup, /data-testid="story-dialogue-panel"/);
    assert.match(markup, /data-testid="story-dialogue-text"/);
    assert.match(markup, /color-mix\(in srgb, rgba\(224,96,160,0.35\) 40%, transparent\)/);
    assert.doesNotMatch(markup, /剧情正在生成/);
    assert.doesNotMatch(markup, /data-testid="story-game-character"/);
  });

  it("shows the current scene beside the Story time", () => {
    const markup = renderStoryMarkup(<StoryGameSurface story={createStoryDetails({ currentScene: { key: "home-living-room-night", name: "夜间客厅", characterIds: ["role-1", "player"] } })} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.match(markup, /data-testid="story-current-scene"/);
    assert.match(markup, /场景：夜间客厅/);
    assert.doesNotMatch(markup, /home-living-room-night/);
  });

  it("uses the Story-owned background resource when it is ready", () => {
    const markup = renderStoryMarkup(<StoryGameSurface characterAvatarUrl="shiori-asset://local/role" story={createStoryDetails({ currentScene: { key: "default", name: "默认场景", characterIds: ["role-1"] }, backgroundResource: { id: "resource-1", storyId: "story-1", kind: "background", visualType: "scene", sceneKey: "default", status: "ready", path: "D:\\stories\\opening.png", prompt: "anime screencap", sourceTurnId: "turn-1", sequence: 1, errorCode: null, createdAt: "", updatedAt: "" } })} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);
    assert.match(markup, /data-testid="story-game-backdrop"/);
    assert.match(markup, /url\(fake-asset:\/\/D:\\stories\\opening\.png\)/);
    assert.match(markup, /data-testid="story-game-character"/);
    assert.match(markup, /shiori-asset:\/\/local\/role/);
    assert.doesNotMatch(markup, /default-galgame-bg\.png/);
  });

  it("uses the latest ready progression CG as the active stage visual", () => {
    const markup = renderStoryMarkup(<StoryGameSurface characterAvatarUrl="shiori-asset://local/role" story={createStoryDetails({
      cgGallery: [
        { id: "resource-1", storyId: "story-1", kind: "cg", visualType: "scene", sceneKey: "default", status: "ready", path: "D:\\stories\\scene-1.png", prompt: "scene one", sourceTurnId: "turn-2", sequence: 1, errorCode: null, createdAt: "", updatedAt: "" },
        { id: "resource-2", storyId: "story-1", kind: "cg", visualType: "character", sceneKey: "default", status: "ready", path: "D:\\stories\\scene-2.png", prompt: "scene two", sourceTurnId: "turn-3", sequence: 2, errorCode: null, updatedAt: "", createdAt: "" },
      ],
    })} busy={false} error="" onSubmitInput={async () => true} onRegenerateCg={() => undefined} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.match(markup, /url\(fake-asset:\/\/D:\\stories\\scene-2\.png\)/);
    assert.match(markup, /aria-label="重新生成当前 CG"/);
    assert.doesNotMatch(markup, /scene-1\.png/);
    assert.doesNotMatch(markup, /data-testid="story-game-character"/);
    assert.doesNotMatch(markup, /default-galgame-bg\.png/);
  });

  it("keeps the previous CG visible while its replacement is generating", () => {
    const markup = renderStoryMarkup(<StoryGameSurface characterAvatarUrl="shiori-asset://local/role" story={createStoryDetails({
      cgGallery: [
        { id: "resource-1", storyId: "story-1", kind: "cg", visualType: "scene", sceneKey: "default", status: "generating", path: "D:\\stories\\scene-old.png", prompt: "scene", sourceTurnId: "turn-2", sequence: 1, errorCode: null, createdAt: "", updatedAt: "" },
      ],
    })} busy={false} error="" onSubmitInput={async () => true} onRegenerateCg={() => undefined} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.match(markup, /url\(fake-asset:\/\/D:\\stories\\scene-old\.png\)/);
    assert.match(markup, /aria-label="重新生成当前 CG"/);
    assert.doesNotMatch(markup, /default-galgame-bg\.png/);
  });

  it("overlays the current role difference on a character-free scene CG", () => {
    const markup = renderStoryMarkup(<StoryGameSurface characterAvatarUrl="shiori-asset://local/role" story={createStoryDetails({
      currentScene: { key: "default", name: "默认场景", characterIds: ["role-1"] },
      cgGallery: [
        { id: "resource-1", storyId: "story-1", kind: "cg", visualType: "scene", sceneKey: "default", status: "ready", path: "D:\\stories\\scene.png", prompt: "empty station", sourceTurnId: "turn-2", sequence: 1, errorCode: null, createdAt: "", updatedAt: "" },
      ],
    })} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.match(markup, /data-testid="story-game-character"/);
  });

  it("does not show a role difference when that role is not in the current scene", () => {
    const markup = renderStoryMarkup(<StoryGameSurface characterAvatarUrl="shiori-asset://local/role" story={createStoryDetails({
      cgGallery: [
        { id: "resource-1", storyId: "story-1", kind: "cg", visualType: "scene", sceneKey: "default", status: "ready", path: "D:\\stories\\scene.png", prompt: "girl feeding man", sourceTurnId: "turn-2", sequence: 1, errorCode: null, createdAt: "", updatedAt: "" },
      ],
    })} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.doesNotMatch(markup, /data-testid="story-game-character"/);
  });

  it("does not overlay the role difference when the current CG already contains characters", () => {
    const markup = renderStoryMarkup(<StoryGameSurface characterAvatarUrl="shiori-asset://local/role" story={createStoryDetails({
      currentScene: { key: "default", name: "默认场景", characterIds: ["role-1"] },
      cgGallery: [
        { id: "resource-1", storyId: "story-1", kind: "cg", visualType: "character", sceneKey: "default", status: "ready", path: "D:\\stories\\scene.png", prompt: "girl feeding man", sourceTurnId: "turn-2", sequence: 1, errorCode: null, createdAt: "", updatedAt: "" },
      ],
    })} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.doesNotMatch(markup, /data-testid="story-game-character"/);
  });

  it("does not substitute menu art when the current scene has no CG", () => {
    const markup = renderStoryMarkup(<StoryGameSurface background={resolvedBackground} story={createStoryDetails()} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.doesNotMatch(markup, /story-menu-random\.webp/);
    assert.doesNotMatch(markup, /default-galgame-bg\.png/);
  });

  it("replaces the dialogue with one generation state and hides player input while the turn generates", () => {
    const generating = createStoryDetails();
    const markup = renderStoryMarkup(<StoryGameSurface story={{ ...generating, segment: { ...generating.segment, operation: "generating" } }} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.match(markup, />剧情生成中\.\.\.</);
    assert.doesNotMatch(markup, />你终于来了。</);
    assert.doesNotMatch(markup, /data-testid="story-player-input"/);
    assert.doesNotMatch(markup, /剧情正在生成。/);
  });

  it("distinguishes narration from dialogue in the normal game surface", () => {
    const story = createStoryDetails({ beats: [{ ...createStoryDetails().beats[0], text: "她嘴上凶着，却伸手把你碗里凉掉的汤换成了自己手边那碗还温着的。玫粉色的眼睛低垂着，声音细得像抱怨：“……吃快点，凉了又该胃疼了。”", speaker: "澪", kind: "narration" }] });
    const markup = renderStoryMarkup(<StoryGameSurface story={story} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.match(markup, /data-story-fragment-kind="narration"/);
    assert.match(markup, />旁白</);
    assert.match(markup, /她嘴上凶着/);
    assert.doesNotMatch(markup, /data-testid="story-player-input"/);
  });

  it("uses the frozen Story role name for legacy generic dialogue speakers", () => {
    const story = createStoryDetails({ beats: [{ ...createStoryDetails().beats[0], speaker: "角色" }] });
    const markup = renderStoryMarkup(<StoryGameSurface story={story} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);

    assert.match(markup, />澪</);
    assert.doesNotMatch(markup, />角色</);
  });

  it("finishes the typing line before advancing and offers input only after the last line", async () => {
    const story = createStoryDetails({ beats: [createStoryBeat({ id: "beat-1", text: "第一句。" }), createStoryBeat({ id: "beat-2", sequence: 2, text: "第二句。" })] });
    let archiveOpened = 0;
    const { host } = createFakeHostServices();
    const view = await mountTestComponent(<PluginHostServicesProvider services={host}><StoryGameSurface story={story} busy={false} error="" onSubmitInput={async () => true} onOpenArchive={() => { archiveOpened += 1; }} onOpenSettings={() => undefined} onExit={() => undefined} /></PluginHostServicesProvider>);
    try {
      const surface = view.container.querySelector<HTMLElement>('[data-testid="story-game-surface"]')!;
      const text = () => view.container.querySelector<HTMLElement>('[data-testid="story-dialogue-text"]')!;
      const click = () => act(async () => { surface.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
      // The page opens on the latest committed beat, still typing.
      assert.equal(text().dataset.storyBeatId, "beat-2");
      assert.equal(text().dataset.storyTextComplete, "false");
      assert.equal(view.container.querySelector('[data-testid="story-player-input"]'), null);
      await click();
      assert.equal(text().dataset.storyBeatId, "beat-2");
      assert.equal(text().dataset.storyTextComplete, "true");
      assert.ok(view.container.querySelector('[data-testid="story-player-input"]'));
      // Scrolling down reads on; only scrolling up opens the record.
      await act(async () => { surface.dispatchEvent(new window.WheelEvent("wheel", { bubbles: true, deltaY: 120 })); });
      assert.equal(archiveOpened, 0);
      await act(async () => { surface.dispatchEvent(new window.WheelEvent("wheel", { bubbles: true, deltaY: -120 })); });
      assert.equal(archiveOpened, 1);
    } finally { await view.cleanup(); }
  });
});
