import avatarSrc from "../assets/avatar.webp";
import cg1 from "../assets/cg-1.webp";
import cg2 from "../assets/cg-2.webp";
import cg3 from "../assets/cg-3.webp";
import cg4 from "../assets/cg-4.webp";
import cg5 from "../assets/cg-5.webp";
import cg6 from "../assets/cg-6.webp";
import cg7 from "../assets/cg-7.webp";
import character1 from "../assets/character-1.webp";
import character2 from "../assets/character-2.webp";
import character3 from "../assets/character-3.webp";
import title1 from "../assets/title-1.webp";
import title2 from "../assets/title-2.webp";
import title3 from "../assets/title-3.webp";
import topic1 from "../assets/topic-1.webp";
import topic2 from "../assets/topic-2.webp";
import topic3 from "../assets/topic-3.webp";

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

/** Title screen standing art, shown one at a time, chosen by titleArt/. */
export const titleArtwork: readonly SiteImage[] = [
  { src: title1, alt: "吟风夜色立绘：坐在公园长椅上，以手托腮微笑，发间系着蝙蝠翼造型的发绳" },
  { src: title2, alt: "吟风夜色立绘：倚在夜景窗边，外套披在肩头，回望镜头" },
  { src: title3, alt: "吟风夜色立绘：从门后探身张望，身后是温暖的暖色房间" },
];

/** Character screen standing art (#350 consumes these). */
export const characterArtwork: readonly SiteImage[] = [
  { src: character1, alt: "吟风人物立绘：身着水手服，走在秋日林荫道上" },
  { src: character2, alt: "吟风人物立绘：抱着笔记本，站在黄昏时分的小巷中" },
  { src: character3, alt: "吟风人物立绘：白色连衣裙，双臂交叠靠在窗台上" },
];

/** ADV dialogue topic illustrations (#348 consumes these). */
export const topicArtwork: readonly SiteImage[] = [
  { src: topic1, alt: "吟风配图：倚在洒满阳光的窗边，居家休闲装扮" },
  { src: topic2, alt: "吟风配图：坐在课桌前看手机，逆光的教室场景" },
  { src: topic3, alt: "吟风配图：月夜窗边浅笑，黑色晚装缀有蝙蝠翼装饰" },
];

/** CG gallery landscape art (#350 consumes these). */
export const galleryArtwork: readonly SiteImage[] = [
  { src: cg1, alt: "CG：睡前由人帮忙用吹风机吹干头发的温馨卧室场景" },
  { src: cg2, alt: "CG：侧躺在床上，蓝紫色柔光近景" },
  { src: cg3, alt: "CG：趴在粉色电脑桌前兴奋地打字" },
  { src: cg4, alt: "CG：窝在沙发上吃甜点的夜晚场景" },
  { src: cg5, alt: "CG：阳光洒落的窗边侧脸特写" },
  { src: cg6, alt: "CG：晚霞海边的全身立绘，黑色蝙蝠翼连衣裙" },
  { src: cg7, alt: "CG：夜晚街头挽臂同行的温馨场景" },
];

/** Small square ADV avatar cropped from the character art's face. */
export const avatarImage: SiteImage = {
  src: avatarSrc,
  alt: "吟风头像：面部特写",
};
