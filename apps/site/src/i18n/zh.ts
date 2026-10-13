import type { GalleryArt } from "../content/gallery";
import type { NarrativeCgKey, NarrativeLineId } from "../content/narrative";
import type { ShowcaseClipId, ShowcaseFeatureCopy } from "../content/showcase";
import { SITE_NAME } from "../lib/siteMeta";

/*
 * The site's words in Chinese (#806): every piece of interface text the
 * pages show or name — titles and descriptions, the narrative, the
 * showcase, alt text, labels — so a component takes its words from the
 * dictionary of its page's language (`siteText`, ./index.ts) and never
 * spells them out itself. Its shape is the dictionaries' type
 * (`SiteDictionary`): the English one (./en.ts) must give every key.
 *
 * Keyword wording (#799): the companion search words (AI 伴侣 / AI 女友 /
 * Personal Agent, remembers you, comes to find you, open source and free,
 * Windows), in the slogan's voice.
 */

/** Product slogan (also on the README). */
const slogan = "会慢慢喜欢上你的 AI 伴侣";

export const zh = {
  /** Page head and the home page's keyword heading. */
  meta: {
    /** The home page's `<title>`: the name, the slogan and the search words it lacks. */
    homeTitle: `${SITE_NAME} · ${slogan} · 开源免费的 Personal Agent`,
    /** The home page's description (meta, OG, structured data), and the default for pages without their own. */
    description:
      "Shiori 是会慢慢喜欢上你的 AI 伴侣，一款开源免费的 Windows Personal Agent。她可以是你的 AI 女友：记得你们聊过的往事，太久不理她就会主动来找你，也能陪你处理文件、搜索这些手头的事。",
    /**
     * The home page's one `h1`. The download call shows the app icon in its
     * place, so this text is visually hidden: it names the page for search
     * engines and screen readers without touching the design.
     */
    homeHeading: `${SITE_NAME}：会慢慢喜欢上你的 AI 伴侣，开源的 Personal Agent`,
    /** What every other page's `<title>` ends with, after its own name (`pageTitle`). */
    titleSuffix: `${SITE_NAME} AI 伴侣`,
    /** Name of the blog feed's `<link rel="alternate">`. */
    feedTitle: `${SITE_NAME} 博客`,
  },
  /** Product slogan, under the closing call. */
  slogan,
  /** Closing call of the home page, in 吟风's voice; the slogan sits under it. */
  downloadHeadline: "把我带回家吧，笨蛋。",
  /** The Windows download button closing the narrative; the script appends the release tag. */
  downloadButton: "下载 Windows 版",
  /** The top bar. */
  header: {
    label: "站点导航",
    /** Its download button, in the bar's narrow space. */
    download: "下载 Windows 版",
    blog: "博客",
    changelog: "更新日志",
  },
  /** The footer's project links. */
  footer: {
    label: "项目链接",
    releases: "Release",
    license: "MIT 许可",
  },
  breadcrumbs: {
    label: "面包屑",
    home: "首页",
  },
  /** The background music switch: its name, and the tooltip naming the action. */
  sound: {
    label: "背景音乐",
    turnOn: "播放背景音乐",
    turnOff: "关闭背景音乐",
  },
  /** The switch to the other language: what it shows, and its accessible name. */
  languageSwitch: {
    text: "EN",
    label: "切换到英文版（English）",
  },
  /**
   * The one-time prompt offering the site in this language
   * (LanguagePrompt.astro), worded in this language for a visitor who reads
   * it rather than the page's: the Chinese pages show the English entry.
   * This Chinese one is for a page that would offer Chinese (none yet).
   */
  languagePrompt: {
    label: "语言",
    question: "要看中文版吗？",
    switch: "切换",
    dismiss: "关闭",
  },
  /** The home page narrative (content/narrative.ts). */
  narrative: {
    /** The dialogue box's name plate. */
    speaker: "吟风",
    lines: {
      arrival: "哎呀，终于来了？让我等了好久呢，笨蛋访客～",
      introduction: "我是吟风，Shiori 的看板娘。记住了哦，不许忘。",
      companion: "Shiori 呢，就是会慢慢喜欢上你的 AI 伴侣……比如我。",
      characters: "你可以养好多角色，每个都有自己的人设、性格和经历。",
      remembers: "聊过的事都会好好记着，还会整理成长期记忆。别想赖账哦。",
      affinity: "好感度会随相处慢慢变化，从厌恶到挚爱……就看你表现了。",
      "comes-to-find-you": "太久不理人的话，我们可是会自己找上门的。",
      everywhere: "Telegram、QQ、飞书都能接。就算出门在外，也躲不掉我的消息～",
      "gets-things-done": "诶，以为我只会陪聊？文件、搜索、shell，手头的事也能一起做。",
      "story-mode": "想冒险的话，就带着角色走进故事模式，用行动推进剧情。",
      "desktop-pet": "还能变成桌宠住进你的桌面，回复直接在旁边冒气泡。",
      "plugins-on-demand": "这些都要装吗？不用。故事、桌宠、生图和渠道都是插件，想开哪个开哪个。",
      "take-me-home": "哼，这就听完了？……想要我陪的话，就把 Shiori 带回家吧。",
      "see-you": "下次见面，可别让我等太久哦～",
    } satisfies Record<NarrativeLineId, string>,
  },
  /** The product showcase after the narrative (content/showcase.ts). */
  showcase: {
    label: "Shiori 功能展示",
    features: {
      memory: {
        title: "聊过的事，她都记得",
        line: "每个角色都有自己的人设与经历，往事会整理成长期记忆。",
        stillAlt: "角色页截图：吟风的记忆时间线，记着约好周六下午去旧书店、你喝咖啡不加糖、小时候在海边住过一个夏天",
      },
      affection: {
        title: "从厌恶，到挚爱",
        line: "好感度随相处慢慢变化，七个阶段，一点点走近。",
        stillAlt: "角色页截图：好感度 41，处在朋友阶段，下面按天列着每次 +1、+2 的小变化和原因",
      },
      proactive: {
        title: "太久不理她，她会来找你",
        line: "依关系与互动主动开口，也能自己安排任务与定时。",
        stillAlt: "聊天截图：道过晚安后一整天没有消息，吟风接连主动发来两条",
      },
      channels: {
        title: "出门在外，也躲不掉",
        line: "Telegram、QQ、飞书都能接，到哪儿都是同一个她。",
        stillAlt: "聊天截图：打开角色的手机，QQ 群「周末读书会」里吟风替你回了大家的消息",
      },
      plugins: {
        title: "不只是陪你聊天",
        line: "文件、搜索、shell 帮你做事；故事模式、桌宠、生图按需开启。",
        stillAlt: "聊天截图：吟风的回复上方展开了 read_file、web_search 与 shell 三次工具调用",
      },
    } satisfies Record<ShowcaseClipId, ShowcaseFeatureCopy>,
  },
  /** The photo strip closing the showcase (content/gallery.ts). */
  photoStrip: {
    label: "吟风的 CG 相片",
  },
  /**
   * Alt text of 吟风's art, by its file name in `assets/art/`: the photo
   * strip's prints, the narrative's event CGs and the site's share picture
   * (cg-6) all describe the same pictures.
   */
  art: {
    "cg-2": "CG：侧躺在床上，蓝紫色柔光近景",
    "cg-3": "CG：趴在粉色电脑桌前兴奋地打字",
    "cg-4": "CG：窝在沙发上吃甜点的夜晚场景",
    "cg-5": "CG：阳光洒落的窗边侧脸特写",
    "cg-6": "CG：晚霞海边的全身立绘，黑色蝙蝠翼连衣裙",
    "cg-7": "CG：夜晚街头挽臂同行的温馨场景",
    "cg-8": "CG：夜色中坐在公园长椅上，以手托腮微笑，发间系着蝙蝠翼造型的发绳",
    "cg-9": "CG：倚在夜景窗边，外套披在肩头，回望镜头",
    "cg-10": "CG：从门后探身张望，身后是温暖的暖色房间",
    "topic-1": "吟风配图：倚在洒满阳光的窗边，居家休闲装扮",
    "topic-2": "吟风配图：坐在课桌前看手机，逆光的教室场景",
    "topic-3": "吟风配图：月夜窗边浅笑，黑色晚装缀有蝙蝠翼装饰",
  } satisfies Record<GalleryArt | NarrativeCgKey, string>,
};

/**
 * The shape every dictionary has: the Chinese one's keys, each a string.
 * Typing the English dictionary with it makes a missing or extra key a
 * type error (tests/dictionaries.test.ts checks the same at run time).
 */
export type SiteDictionary = typeof zh;
