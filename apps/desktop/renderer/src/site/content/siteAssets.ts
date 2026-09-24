import avatarSrc from "../assets/avatar.webp";
import cg1 from "../assets/cg-1.webp";
import cg2 from "../assets/cg-2.webp";
import cg3 from "../assets/cg-3.webp";
import cg4 from "../assets/cg-4.webp";
import cg5 from "../assets/cg-5.webp";
import cg6 from "../assets/cg-6.webp";
import cg7 from "../assets/cg-7.webp";
import cg8 from "../assets/cg-8.webp";
import cg9 from "../assets/cg-9.webp";
import cg10 from "../assets/cg-10.webp";
import character1 from "../assets/character-1.webp";
import character2 from "../assets/character-2.webp";
import character3 from "../assets/character-3.webp";
import sprite1 from "../assets/sprite-1.webp";
import sprite2 from "../assets/sprite-2.webp";
import sprite3 from "../assets/sprite-3.webp";
import topic1 from "../assets/topic-1.webp";
import topic2 from "../assets/topic-2.webp";
import topic3 from "../assets/topic-3.webp";
import type { AdvEventCgKey, AdvSpriteKey } from "./advScript";

/** Shiori title logo, relative to the built site's output root (see vite.site.config.ts). */
export const SITE_LOGO_URL = "./assets/branding/shiori-title-logo.png";

/** One site image: the built asset URL plus its accessible alt text. */
export interface SiteImage {
  readonly src: string;
  readonly alt: string;
}

/**
 * Owner-picked, metadata-stripped art for the site, grouped by the role each
 * image plays. Components must import images from here rather than reaching
 * into `../assets/` directly, so swapping a picture is a one-file change.
 *
 * Every `../assets/*.webp` import above is also what
 * `apps/desktop/renderer/src/site/content/siteAssets.test.ts` parses (as plain
 * text, not by executing this module) to confirm each referenced file exists
 * on disk; that test also owns the WebP/size/metadata hygiene checks for
 * every file in `../assets/`.
 */

/**
 * 吟风's cut-out standing sprites (transparent WebP), shown over the scene
 * background: one at a time on the title screen (chosen by titleArt/), and
 * named by the ADV script's sprite segments.
 */
export const titleSprites: readonly SiteImage[] = [
  { src: sprite1, alt: "吟风立绘：黑色哥特连衣裙配过膝袜，背后展开蝙蝠翼，以手掩唇浅笑" },
  { src: sprite2, alt: "吟风立绘：白色水手服配红格短裙，双手背在身后微微前倾" },
  { src: sprite3, alt: "吟风立绘：白色露肩上衣配黑色短裙，双手轻提裙摆" },
];

/** 人物 screen standing art, one per selectable outfit (see characterProfile.ts). */
export const characterArtwork: readonly SiteImage[] = [
  { src: character1, alt: "吟风人物立绘：身着水手服，走在秋日林荫道上" },
  { src: character2, alt: "吟风人物立绘：抱着笔记本，站在黄昏时分的小巷中" },
  { src: character3, alt: "吟风人物立绘：粉色双马尾，白色露肩上衣配黑色短裙，在门口伸手张望" },
];

/** ADV topic illustrations, shown as event CGs in place of the sprite (see `advEventCgs`). */
export const topicArtwork: readonly SiteImage[] = [
  { src: topic1, alt: "吟风配图：倚在洒满阳光的窗边，居家休闲装扮" },
  { src: topic2, alt: "吟风配图：坐在课桌前看手机，逆光的教室场景" },
  { src: topic3, alt: "吟风配图：月夜窗边浅笑，黑色晚装缀有蝙蝠翼装饰" },
];

/** CG 鉴赏 art: landscape scenes, then the three night portraits. */
export const galleryArtwork: readonly SiteImage[] = [
  { src: cg1, alt: "CG：睡前由人帮忙用吹风机吹干头发的温馨卧室场景" },
  { src: cg2, alt: "CG：侧躺在床上，蓝紫色柔光近景" },
  { src: cg3, alt: "CG：趴在粉色电脑桌前兴奋地打字" },
  { src: cg4, alt: "CG：窝在沙发上吃甜点的夜晚场景" },
  { src: cg5, alt: "CG：阳光洒落的窗边侧脸特写" },
  { src: cg6, alt: "CG：晚霞海边的全身立绘，黑色蝙蝠翼连衣裙" },
  { src: cg7, alt: "CG：夜晚街头挽臂同行的温馨场景" },
  { src: cg8, alt: "CG：夜色中坐在公园长椅上，以手托腮微笑，发间系着蝙蝠翼造型的发绳" },
  { src: cg9, alt: "CG：倚在夜景窗边，外套披在肩头，回望镜头" },
  { src: cg10, alt: "CG：从门后探身张望，身后是温暖的暖色房间" },
];

/**
 * Every sprite / event CG slot the ADV dialogue script (`advScript.ts`) can
 * name. `Record`s so adding a slot to the script without an image here is a
 * type error.
 */
export const advSprites: Record<AdvSpriteKey, SiteImage> = {
  "sprite-1": titleSprites[0],
  "sprite-2": titleSprites[1],
  "sprite-3": titleSprites[2],
};

export const advEventCgs: Record<AdvEventCgKey, SiteImage> = {
  "topic-1": topicArtwork[0],
  "topic-2": topicArtwork[1],
  "topic-3": topicArtwork[2],
  "cg-8": galleryArtwork[7],
  "cg-10": galleryArtwork[9],
};

/** Small square ADV avatar cropped from the character art's face. */
export const avatarImage: SiteImage = {
  src: avatarSrc,
  alt: "吟风头像：面部特写",
};
