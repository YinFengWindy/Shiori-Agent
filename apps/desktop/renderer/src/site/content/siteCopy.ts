/**
 * All site copy (menu labels, external links) in one data module, so a
 * wording change or future i18n split never touches component code.
 */

/** The four sub-screens a visitor can be on, plus the title screen itself. */
export type SiteScreenId = "title" | "adv" | "character" | "gallery";

interface SiteMenuAction {
  readonly id: Exclude<SiteScreenId, "title">;
  readonly label: string;
  /** "screen" swaps the title for a sub-screen; "external" opens a new tab. */
  readonly kind: "screen";
}

interface SiteMenuExternal {
  readonly id: "download";
  readonly label: string;
  readonly kind: "external";
  readonly href: string;
}

interface SiteMenuModal {
  readonly id: "settings";
  readonly label: string;
  readonly kind: "modal";
}

export type SiteMenuItem = SiteMenuAction | SiteMenuExternal | SiteMenuModal;

export const SITE_LINKS = {
  github: "https://github.com/YinFengWindy/Shiori-Agent",
  releasesLatest: "https://github.com/YinFengWindy/Shiori-Agent/releases/latest",
} as const;

/** Vertical galgame title menu, top to bottom. */
export const SITE_MENU_ITEMS: readonly SiteMenuItem[] = [
  { id: "adv", label: "开始", kind: "screen" },
  { id: "character", label: "人物", kind: "screen" },
  { id: "gallery", label: "CG 鉴赏", kind: "screen" },
  { id: "download", label: "下载", kind: "external", href: SITE_LINKS.releasesLatest },
  { id: "settings", label: "设置", kind: "modal" },
];

/** Placeholder sub-screen copy until #350 fills in the real screens. */
export const SITE_PLACEHOLDER_COPY: Record<Exclude<SiteScreenId, "title" | "adv">, { title: string; body: string }> = {
  character: { title: "人物", body: "准备中" },
  gallery: { title: "CG 鉴赏", body: "准备中" },
};

export const SITE_BACK_LABEL = "返回标题";
export const SITE_GITHUB_LABEL = "在 GitHub 查看 Shiori";
/** Speaker toggle: fixed accessible name (on/off is aria-pressed) + hover tooltips. */
export const SITE_SOUND_COPY = { label: "声音", enableTitle: "开启声音", disableTitle: "关闭声音" } as const;
export const SITE_SETTINGS_TITLE = "设置";
export const SITE_SETTINGS_CLOSE_LABEL = "关闭设置";

/** Settings modal labels; values are stored by `prefs/sitePrefs.ts`. */
export const SITE_SETTINGS_COPY = {
  bgmVolume: "BGM 音量",
  sfxVolume: "音效音量",
  textSpeed: "文字速度",
  textSpeedOptions: { slow: "慢", normal: "中", fast: "快" },
  textSpeedPreview: "文字会以这样的速度出现哦～",
} as const;

/** ADV dialogue box chrome (the dialogue itself lives in advScript.ts). */
export const SITE_ADV_COPY = {
  screenLabel: "吟风的对话",
  advance: "继续",
  auto: "自动",
  skip: "跳过",
  backlog: "记录",
  settings: "设置",
  title: "标题",
  titleLabel: "返回标题",
  choicesLabel: "选项",
  visited: "已读",
  backlogTitle: "对话记录",
  backlogClose: "关闭记录",
  backlogChoice: "你选择了",
} as const;
