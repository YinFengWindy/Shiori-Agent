import type { AdvScript } from "../adv/advModel";

/**
 * Art slots the ADV screen can show. `siteAssets` maps every key to an image
 * (`advSprites` / `advEventCgs`), so the script below only names slots and
 * never imports files.
 */
export type AdvSpriteKey = "sprite-1" | "sprite-2" | "sprite-3";
export type AdvEventCgKey = "topic-1" | "topic-2" | "topic-3" | "cg-8" | "cg-10";

/** A segment's art: 吟风's standing sprite, or an event CG that replaces it. */
export type AdvArtRef = { readonly kind: "sprite"; readonly key: AdvSpriteKey } | { readonly kind: "cg"; readonly key: AdvEventCgKey };

const sprite = (key: AdvSpriteKey): AdvArtRef => ({ kind: "sprite", key });
const eventCg = (key: AdvEventCgKey): AdvArtRef => ({ kind: "cg", key });

/**
 * 「开始」 dialogue: 吟风 (Shiori 的看板娘, a playful little devil) walks the
 * visitor through Shiori's real features. Every claim here must match
 * README.md; keep each line short (≤ 40 characters).
 *
 * Art: the opening and closing show 吟风's standing sprite over the scene
 * background (gothic dress to greet, casual clothes to say goodbye); each
 * topic swaps the sprite for an event CG — the 3 topic illustrations plus
 * two of the night CGs — and 生图 and 插件 share the bright window one.
 */
export const ADV_SCRIPT: AdvScript<AdvArtRef> = {
  speaker: "吟风",
  opening: {
    art: sprite("sprite-1"),
    lines: [
      "哎呀，终于点进来了？让我等了好久呢，笨蛋访客～",
      "我是吟风，Shiori 的看板娘。记住了哦，不许忘。",
      "Shiori 是 Windows 上本地优先的 AI 角色陪伴应用。",
      "你可以养好多角色，每个都有自己的人设和记忆。",
      "不管在桌面、Telegram 还是 QQ，她都是同一个人。",
      "好啦，想知道什么就挑吧。我心情好，就讲给你听～",
    ],
  },
  choicePrompt: {
    first: "想先听哪个？快选，我可没那么多耐心。",
    again: "还有想问的吗？不问的话，我可要走了哦。",
  },
  topics: [
    {
      id: "chat",
      label: "聊天与多端",
      art: eventCg("topic-2"),
      lines: [
        "每个角色都能开好几个会话，聊天记录全都留着。",
        "回复是流式一点点冒出来的，不用傻等哦。",
        "桌面、Telegram、QQ 共用同一份角色状态和记录。",
        "她还会看关系和气氛，自己决定要不要主动找你。",
        "就算你出门在外，也躲不掉 Telegram 上的消息啦～",
      ],
    },
    {
      id: "memory",
      label: "角色与记忆",
      art: eventCg("cg-8"),
      lines: [
        "每个角色的人设、立绘和素材都分开放，互不打扰。",
        "聊过的事会变成记忆，分近期和长期两层，还会定期整理。",
        "侧栏能看到她此刻的心情和想法，每轮回复后都会变。",
        "还有关系标签和寂寞值……太久不理人的话，哼。",
        "才、才不是在想你！闲下来时会跑 Drift 任务而已。",
      ],
    },
    {
      id: "image",
      label: "生图",
      art: eventCg("topic-1"),
      lines: [
        "生图靠 NovelAI，用提示词标签就能控制画面。",
        "画好直接在应用里预览，很方便吧？",
        "聊到合适的时候，还会自动出一张场景 CG。",
        "顺带一提，这个网站上的我，也是 NovelAI 画的哦。",
        "要自己配好 NovelAI 服务才能用，别怪我没提醒你。",
      ],
    },
    {
      id: "story",
      label: "故事模式",
      art: eventCg("topic-3"),
      lines: [
        "故事模式里，每段故事都是一次独立的经历。",
        "角色快照、背景、剧情记录和场景状态都会带着。",
        "剧情推进和自由对话随时切换，还能暂停、保存、恢复。",
        "也能从某个节点开分支……想看别的结局？贪心鬼。",
        "重要节点还能挂上 CG 和语音，演出感拉满～",
      ],
    },
    {
      id: "pet",
      label: "桌宠",
      art: eventCg("cg-10"),
      lines: [
        "每个角色都能单独变成桌宠，住进你的桌面。",
        "素材包支持 ZIP 导入，会做安全校验和动作映射。",
        "拖着走时会按方向做动作，停下就回到待机。",
        "回复直接在桌宠旁边冒气泡，还会常驻托盘。",
        "配好 ASR / TTS 还能语音聊天……才没想听你的声音。",
      ],
    },
    {
      id: "plugins",
      label: "插件",
      art: eventCg("topic-1"),
      lines: [
        "故事模式、桌宠、NovelAI 生图，其实本身都是插件。",
        "在「设置 → 插件」里能逐个启用、停用和配置。",
        "插件打成 ZIP 就能装，也能更新和卸载，重启后生效。",
        "工作区里的插件，要你亲手确认信任才会运行。",
        "还有「24h视奸插件」，能按需看一眼你的屏幕……只看不碰哦。",
      ],
    },
  ],
  exit: {
    label: "没什么想问的了",
    art: sprite("sprite-3"),
    lines: [
      "哼，这就问完了？……好吧，也不是不能放你走。",
      "想要我陪的话，就去「下载」把 Shiori 带回家吧。",
      "下次见面，可别让我等太久哦～",
    ],
  },
};
