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

/** Placeholder sub-screen copy until #348/#350 fill in the real screens. */
export const SITE_PLACEHOLDER_COPY: Record<Exclude<SiteScreenId, "title">, { title: string; body: string }> = {
  adv: { title: "开始", body: "准备中" },
  character: { title: "人物", body: "准备中" },
  gallery: { title: "CG 鉴赏", body: "准备中" },
};

export const SITE_BACK_LABEL = "返回标题";
export const SITE_GITHUB_LABEL = "在 GitHub 查看 Shiori";
export const SITE_SETTINGS_TITLE = "设置";
export const SITE_SETTINGS_PLACEHOLDER = "准备中";
export const SITE_SETTINGS_CLOSE_LABEL = "关闭设置";
