import type { RoleRecord, SessionMessage } from "../shared/types";

/** Public assets bundled by Vite; never paths into a visitor's filesystem. */
export const demoAvatar = new URL("../../../../../assets/shiori-app-icon.png", import.meta.url).href;
export const demoBackdrop = new URL("../../../../../plugins/story/ui/assets/default-galgame-bg.png", import.meta.url).href;

/** A public demonstration persona, independent of the developer's role library. */
export const demoRole: RoleRecord = {
  id: "showcase-shiori", name: "栞", description: "守着街角旧书店的少女，喜欢雨声和书页里的小小奇遇。",
  system_prompt: "你是栞，街角旧书店的看店人。说话轻快、细心，偶尔有些俏皮。",
  runtime_config: {}, avatar: null, avatar_abs: demoAvatar,
  chat_background: null, chat_background_abs: null,
  illustrations: [], illustrations_abs: [], asset_categories: [], asset_category_bindings: {},
  created_at: "2026-09-20T14:00:00+08:00", updated_at: "2026-09-20T14:00:00+08:00",
};

/** Prewritten chat excerpts; input demonstrates the composer and does not select a reply. */
export const chatSamples = [
  { text: "（把窗边的椅子拉开一点）这里，给你留的。\n\n雨还没停，今天就先把赶路的事放一放吧。", mood: "轻松", thought: "难得有人愿意停下来，陪我听一会儿雨。" },
  { text: "刚才整理书架，发现一本没有署名的旧书。夹在里面的车票，比书页还薄。\n\n（轻轻翻开封面）你说，它以前陪谁走过很远的路呢？", mood: "好奇", thought: "想把这个小发现也分给你一点。" },
  { text: "（把书签递到你手边）先夹在这里。故事不用一下子读完，下次来也来得及。\n\n窗外好像亮了一点……等雨停，我们去门口看看。", mood: "期待", thought: "今天的书店，比平时热闹了一点。" },
] as const;

/** Initial transcript shown before a visitor tries free text input. */
export function initialChatMessages(): SessionMessage[] {
  return [
    { id: "demo-greeting", role: "assistant", content: "（从书架后探出头）下午好。外面下雨了吧？进来坐坐，窗边的位置还空着。", timestamp: demoRole.created_at },
  ];
}

/** Hand-authored Story pages; every visitor sees these same scenes in sequence. */
export const storySamples = [
  [
    { kind: "narration", text: "雨水沿着玻璃蜿蜒而下。街角的旧书店亮着一盏暖灯，门上的风铃轻轻响了。" },
    { kind: "action", text: "栞从高高的书堆后抬起头，顺手把一本翻开的书压在柜台上。" },
    { kind: "dialogue", text: "来避雨的吗？正好，我刚找到一件有趣的东西。" },
  ],
  [
    { kind: "narration", text: "柜台上的旧书里夹着一张褪色的车票，背面写着一行小字：等到雨停，就去看海。" },
    { kind: "dialogue", text: "只有这句话。没有日期，也没有名字……可我总觉得，它是在等谁读到。" },
    { kind: "action", text: "栞把车票放在灯下，纸张边缘透出柔软的金色。" },
  ],
  [
    { kind: "dialogue", text: "如果每本旧书都藏着一段旅程，这本大概还没到终点吧。" },
    { kind: "narration", text: "窗外的雨声渐渐稀疏。街对面有人收起雨伞，一束光落在湿漉漉的石板路上。" },
    { kind: "action", text: "栞拿起书签，把车票小心地夹回原处，又朝门口望了一眼。" },
  ],
  [
    { kind: "dialogue", text: "雨停了。要去门口看看吗？至于看海的事……就留给下一页。" },
    { kind: "narration", text: "风铃再次轻响，带着潮湿的空气。旧书留在柜台上，书页里藏着一个还未启程的约定。" },
  ],
] satisfies Array<Array<{ kind: "narration" | "action" | "dialogue"; text: string }>>;
