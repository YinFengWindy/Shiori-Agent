import type { ImageMetadata } from "astro";
import type { ScenePhase } from "../../../desktop/renderer/src/shared/scene/timeOfDay";
import sceneDay from "../../../desktop/renderer/src/shared/assets/scene/bg-day.webp";
import sceneDusk from "../../../desktop/renderer/src/shared/assets/scene/bg-dusk.webp";
import sceneNight from "../../../desktop/renderer/src/shared/assets/scene/bg-night.webp";
import titleLogo from "../../../desktop/renderer/public/assets/branding/shiori-title-logo.png";
import avatar from "../assets/art/avatar.webp";
import cg1 from "../assets/art/cg-1.webp";
import cg2 from "../assets/art/cg-2.webp";
import cg3 from "../assets/art/cg-3.webp";
import cg4 from "../assets/art/cg-4.webp";
import cg5 from "../assets/art/cg-5.webp";
import cg6 from "../assets/art/cg-6.webp";
import cg7 from "../assets/art/cg-7.webp";
import cg8 from "../assets/art/cg-8.webp";
import cg9 from "../assets/art/cg-9.webp";
import cg10 from "../assets/art/cg-10.webp";
import character1 from "../assets/art/character-1.webp";
import character2 from "../assets/art/character-2.webp";
import character3 from "../assets/art/character-3.webp";
import sprite1 from "../assets/art/sprite-1.webp";
import sprite2 from "../assets/art/sprite-2.webp";
import sprite3 from "../assets/art/sprite-3.webp";
import topic1 from "../assets/art/topic-1.webp";
import topic2 from "../assets/art/topic-2.webp";
import topic3 from "../assets/art/topic-3.webp";
import bgm from "../assets/audio/bgm.mp3";
import ogCover from "../assets/social/og-cover.jpg";

/** One site image: the build-time image metadata plus its accessible alt text. */
export interface SiteImage {
  readonly image: ImageMetadata;
  readonly alt: string;
}

/**
 * Every picture and sound of the site, grouped by the role each one plays.
 * Pages import art from here rather than reaching into `../assets/`, so
 * swapping a picture is a one-file change. `tests/assets.test.ts` parses the
 * `../assets/art/*.webp` imports above as text to confirm each file exists,
 * and owns the WebP size/metadata hygiene checks for that directory.
 *
 * The scene backgrounds and the title logo are the desktop's own files
 * (first-run guide / startup splash, story plugin) and are imported from
 * there instead of being copied.
 */

/** Time-of-day scene backgrounds (decorative; phase boundaries in desktop `timeOfDay.ts`). */
export const sceneBackgrounds: Record<ScenePhase, ImageMetadata> = {
  day: sceneDay,
  dusk: sceneDusk,
  night: sceneNight,
};

/** 「栞 / SHIORI」 title logo. */
export const titleLogoImage: ImageMetadata = titleLogo;

/** 吟风's cut-out standing sprites (transparent WebP), shown over the scene background. */
export const titleSprites: readonly SiteImage[] = [
  { image: sprite1, alt: "吟风立绘：黑色哥特连衣裙配过膝袜，背后展开蝙蝠翼，以手掩唇浅笑" },
  { image: sprite2, alt: "吟风立绘：白色水手服配红格短裙，双手背在身后微微前倾" },
  { image: sprite3, alt: "吟风立绘：白色露肩上衣配黑色短裙，双手轻提裙摆" },
];

/** Full-scene character art, one per outfit. */
export const characterArtwork: readonly SiteImage[] = [
  { image: character1, alt: "吟风人物立绘：身着水手服，走在秋日林荫道上" },
  { image: character2, alt: "吟风人物立绘：抱着笔记本，站在黄昏时分的小巷中" },
  { image: character3, alt: "吟风人物立绘：粉色双马尾，白色露肩上衣配黑色短裙，在门口伸手张望" },
];

/** Topic illustrations, shown as event CGs in place of the sprite. */
export const topicArtwork: readonly SiteImage[] = [
  { image: topic1, alt: "吟风配图：倚在洒满阳光的窗边，居家休闲装扮" },
  { image: topic2, alt: "吟风配图：坐在课桌前看手机，逆光的教室场景" },
  { image: topic3, alt: "吟风配图：月夜窗边浅笑，黑色晚装缀有蝙蝠翼装饰" },
];

/** Gallery CGs: landscape scenes, then the night portraits. */
export const galleryArtwork: readonly SiteImage[] = [
  { image: cg1, alt: "CG：睡前由人帮忙用吹风机吹干头发的温馨卧室场景" },
  { image: cg2, alt: "CG：侧躺在床上，蓝紫色柔光近景" },
  { image: cg3, alt: "CG：趴在粉色电脑桌前兴奋地打字" },
  { image: cg4, alt: "CG：窝在沙发上吃甜点的夜晚场景" },
  { image: cg5, alt: "CG：阳光洒落的窗边侧脸特写" },
  { image: cg6, alt: "CG：晚霞海边的全身立绘，黑色蝙蝠翼连衣裙" },
  { image: cg7, alt: "CG：夜晚街头挽臂同行的温馨场景" },
  { image: cg8, alt: "CG：夜色中坐在公园长椅上，以手托腮微笑，发间系着蝙蝠翼造型的发绳" },
  { image: cg9, alt: "CG：倚在夜景窗边，外套披在肩头，回望镜头" },
  { image: cg10, alt: "CG：从门后探身张望，身后是温暖的暖色房间" },
];

/** Small square avatar cropped from the character art's face. */
export const avatarImage: SiteImage = { image: avatar, alt: "吟风头像：面部特写" };

/**
 * Default social preview (OG / Twitter card): the seaside CG (cg-6)
 * cover-cropped to the 1200×630 card size, as JPEG because some link
 * previewers do not render WebP.
 */
export const socialPreviewImage: SiteImage = { image: ogCover, alt: galleryArtwork[5].alt };

/**
 * Background music: 「Sweet Everyday Moments」, owner-generated, cut at 2:43
 * (before the trailing silence) so the loop restarts without a gap, and
 * stripped of metadata. Meant to loop, muted until the visitor turns sound on.
 */
export const siteBgmUrl: string = bgm;
