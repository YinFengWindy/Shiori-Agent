import { characterArtwork, type SiteImage } from "./siteAssets";

/** One selectable outfit on the 人物 screen: a short label plus its standing art. */
export interface CharacterOutfit {
  readonly label: string;
  readonly art: SiteImage;
}

/** A labelled profile row (身份 / 属性 / …). */
export interface CharacterProfileField {
  readonly label: string;
  readonly value: string;
}

/**
 * 「人物」 screen copy for 吟风, Shiori's mascot. Keep it in her voice (see
 * `advScript.ts`: a teasing little devil who secretly hates being left
 * alone) and make no product claims here — those belong to the ADV script,
 * which is checked against README.md.
 */
export const CHARACTER_PROFILE = {
  name: "吟风",
  tagline: "嘴上不饶人的小恶魔看板娘，其实比谁都怕寂寞。",
  fields: [
    { label: "身份", value: "Shiori 的看板娘" },
    { label: "属性", value: "小恶魔" },
    { label: "喜欢", value: "甜点、被夸奖、捉弄访客" },
    { label: "讨厌", value: "被晾在一边" },
  ] satisfies readonly CharacterProfileField[],
  lines: [
    "盯着我看这么久……是看上我了吗？哼哼，眼光不错嘛。",
    "想看我换衣服？只此一次哦，下不为例。",
    "才、才不是特地在这里等你的！只是刚好路过而已。",
  ],
  outfits: [
    { label: "校服", art: characterArtwork[0] },
    { label: "抱书", art: characterArtwork[1] },
    { label: "私服", art: characterArtwork[2] },
  ] satisfies readonly CharacterOutfit[],
} as const;
