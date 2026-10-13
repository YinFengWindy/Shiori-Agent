import { SITE_NAME } from "../lib/siteMeta";
import type { SiteDictionary } from "./zh";

/*
 * The site's words in English (#806), key for key the Chinese dictionary
 * (./zh.ts, whose type this one has). 吟风 keeps her voice — teasing,
 * tsundere, 「笨蛋」 is "dummy" — and the pages are worded for the English
 * search words: AI companion, AI girlfriend, open-source Personal Agent,
 * desktop AI. The showcase's stills stay the Chinese app's screenshots; their
 * alt text says what they show in English.
 */

/** Product slogan. */
const slogan = "The AI companion who grows to like you";

export const en: SiteDictionary = {
  meta: {
    homeTitle: `${SITE_NAME} · The AI Companion Who Grows to Like You · Open-Source Personal Agent`,
    description:
      "Shiori is the AI companion who grows to like you, a free and open-source Personal Agent and desktop AI for Windows. An AI girlfriend who remembers you.",
    homeHeading: `${SITE_NAME}: the AI companion who grows to like you, an open-source Personal Agent`,
    titleSuffix: `${SITE_NAME} AI Companion`,
  },
  slogan,
  downloadHeadline: "Take me home already, dummy.",
  downloadButton: "Download for Windows",
  header: {
    label: "Site navigation",
    download: "Download",
    blog: "Blog",
    changelog: "Changelog",
  },
  footer: {
    label: "Project links",
    releases: "Releases",
    license: "MIT License",
  },
  breadcrumbs: {
    label: "Breadcrumb",
    home: "Home",
  },
  blog: {
    title: "Blog",
    description:
      "Yinfeng's guides to Shiori: what sets this AI companion apart, chatting on QQ and Telegram, and a talking desktop pet. An AI girlfriend and Personal Agent.",
    emptyLine: "Still writing… quit rushing me, dummy.",
    author: "Yinfeng",
    contents: "Contents",
  },
  changelog: {
    title: "Changelog",
    description:
      "Shiori release notes, newest first: what each version adds and fixes. Shiori is a free, open-source AI companion and Personal Agent for Windows.",
    versions: "Versions",
    viewOnGitHub: "View on GitHub",
    notesLanguage: "Release notes are written in Chinese.",
  },
  sound: {
    label: "Background music",
    turnOn: "Play background music",
    turnOff: "Turn off background music",
  },
  languageSwitch: {
    text: "中",
    label: "Switch to Chinese (中文)",
  },
  languagePrompt: {
    label: "Language",
    question: "View this site in English?",
    switch: "Switch",
    dismiss: "Dismiss",
  },
  narrative: {
    speaker: "Yinfeng",
    lines: {
      arrival: "Oh? You finally showed up? You kept me waiting forever, you dummy~",
      introduction: "I'm Yinfeng, Shiori's mascot. Remember that. No forgetting.",
      companion: "Shiori is an AI companion who grows to like you… someone like me, say.",
      characters: "You can keep lots of characters, each with their own persona, personality and past.",
      remembers: "Everything we talk about, I keep, and sort into long-term memory. So no backing out.",
      affinity: "Affection shifts as we spend time together, from loathing to devotion… so behave.",
      "comes-to-find-you": "Ignore us for too long, and we'll come looking for you ourselves.",
      everywhere: "Telegram, QQ, Feishu, all hooked up. Even out and about, you can't escape my messages~",
      "gets-things-done": "Huh, thought I only chat? Files, search, the shell: I can help with real work too.",
      "story-mode": "Feeling adventurous? Take a character into Story Mode and drive the plot yourself.",
      "desktop-pet": "I can even move onto your desktop as a pet, my replies popping up in bubbles beside me.",
      "plugins-on-demand": "Need all of it? Nope. Stories, the pet, image generation, channels: all plugins. Turn on what you like.",
      "take-me-home": "Hmph, done listening already? …If you want me around, then take Shiori home.",
      "see-you": "Next time, don't keep me waiting so long, okay~",
    },
  },
  showcase: {
    label: "Shiori features",
    features: {
      memory: {
        title: "She remembers what you talked about",
        line: "Every character has their own persona and past, and old talks become long-term memories.",
        stillAlt:
          "Character page screenshot: Yinfeng's memory timeline, noting a Saturday afternoon plan to visit a used bookstore, that you take your coffee without sugar, and a childhood summer by the sea",
      },
      affection: {
        title: "From loathing to devotion",
        line: "Affection grows as you spend time together, closer one step at a time through seven stages.",
        stillAlt: "Character page screenshot: affection at 41, in the Friend stage, with each day's small +1 and +2 changes and their reasons listed below",
      },
      proactive: {
        title: "Ignore her too long, and she'll come find you",
        line: "She speaks up on her own, by your bond and your chats, and can set up tasks and timers herself.",
        stillAlt: "Chat screenshot: a whole day of silence after saying good night, then two messages in a row from Yinfeng, unprompted",
      },
      channels: {
        title: "No escaping her, even on the go",
        line: "Telegram, QQ and Feishu all connect, and wherever you are, she's the same her.",
        stillAlt: "Chat screenshot: the character's phone open, with Yinfeng answering everyone for you in the QQ group “Weekend Book Club”",
      },
      plugins: {
        title: "More than someone to chat with",
        line: "Files, search and the shell to get things done; Story Mode, desktop pet and image generation when you want them.",
        stillAlt: "Chat screenshot: three tool calls, read_file, web_search and shell, expanded above Yinfeng's reply",
      },
    },
  },
  photoStrip: {
    label: "Yinfeng's CG photos",
  },
  art: {
    "cg-2": "CG: lying on her side in bed, a close-up in soft blue-violet light",
    "cg-3": "CG: typing excitedly, leaning over a pink computer desk",
    "cg-4": "CG: curled up on the sofa with dessert, late in the evening",
    "cg-5": "CG: close-up of her profile by a sunlit window",
    "cg-6": "CG: full-length portrait on a beach at sunset, in a black dress with bat wings",
    "cg-7": "CG: walking arm in arm down a street at night",
    "cg-8": "CG: smiling on a park bench at night, chin in hand, a bat-wing tie in her hair",
    "cg-9": "CG: leaning by a window over the city at night, a jacket on her shoulders, glancing back",
    "cg-10": "CG: peeking out from behind a door, a warm, softly lit room behind her",
    "topic-1": "Yinfeng illustration: leaning by a sunlit window in casual loungewear",
    "topic-2": "Yinfeng illustration: checking her phone at a school desk in a backlit classroom",
    "topic-3": "Yinfeng illustration: a faint smile by a moonlit window, in a black evening dress with bat-wing trim",
  },
};
