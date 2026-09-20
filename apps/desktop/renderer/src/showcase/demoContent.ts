import type { RoleRecord, SessionMessage } from "../shared/types";
import { demoAvatar, storyArtwork } from "./demoAssets";
export { demoAvatar, demoBackdrop } from "./demoAssets";

/** A public demonstration persona, independent of the developer's role library. */
export const demoRole: RoleRecord = {
  id: "showcase-shiori", name: "吟风", description: "俏皮的小恶魔，喜欢把平凡的相处变成值得记住的小事。",
  system_prompt: "你是吟风，一个俏皮又温柔的小恶魔。此故事从雨天的旧书店相逢开始。",
  runtime_config: {}, avatar: null, avatar_abs: demoAvatar,
  chat_background: null, chat_background_abs: null,
  illustrations: [], illustrations_abs: [storyArtwork.sunset], asset_categories: [], asset_category_bindings: {},
  created_at: "2026-09-20T14:00:00+08:00", updated_at: "2026-09-20T14:00:00+08:00",
};

/** Prewritten chat excerpts; input demonstrates the composer and does not select a reply. */
export const chatSamples = [
  { text: "（把窗边的椅子拉开一点）这里，给你留的。\n\n雨还没停，今天就先把赶路的事放一放吧。放心，我暂时还没有打算收避雨费。", mood: "轻松", thought: "难得有人愿意停下来，陪我听一会儿雨。" },
  { text: "刚才整理书架，发现一本没有署名的旧书。夹在里面的车票，比书页还薄。\n\n（轻轻翻开封面）你说，它以前陪谁走过很远的路呢？", mood: "好奇", thought: "想把这个小发现也分给你一点。" },
  { text: "（把书签递到你手边）先夹在这里。故事不用一下子读完，下次来也来得及。\n\n窗外好像亮了一点……等雨停，我们去门口看看。", mood: "期待", thought: "今天的书店，比平时热闹了一点。" },
] as const;

/** Initial transcript shown before a visitor tries free text input. */
export function initialChatMessages(): SessionMessage[] {
  return [
    { id: "demo-greeting", role: "assistant", content: "（从书架后探出头）下午好，我是吟风。外面下雨了吧？进来坐坐，窗边的位置还空着。\n\n别怕，小恶魔今天心情不错。", timestamp: demoRole.created_at },
  ];
}
