import { BookOpenText, Chats, GearSix, MagnifyingGlass, Users } from "@phosphor-icons/react";
import { navMotifs, withMotif } from "@shiori/plugin-sdk";

/*
 * The nav glyph builder (`withMotif`, `navMotifs`) is owned by
 * `@shiori/plugin-sdk` (#440) and re-exported here; the glyphs are built below.
 */
export { navMotifs, withMotif, type NavGlyphMotion } from "@shiori/plugin-sdk";

/** 搜索: a sparkle in the lens. */
export const SearchGlyph = withMotif(MagnifyingGlass, navMotifs.sparkle(88, 88, 30, { cx: 128, cy: 70, r: 7 }), "twinkle", "SearchGlyph");
/** 消息: a heart in the back bubble. */
export const ChatsGlyph = withMotif(Chats, navMotifs.heart(104, 94, 3.1), "beat", "ChatsGlyph");
/** 角色: a ribbon bow on the front head. */
export const RolesGlyph = withMotif(Users, navMotifs.ribbon(84, 58, 5.2), "wiggle", "RolesGlyph");
/** 设置: a sakura in the gear hole. */
export const SettingsGlyph = withMotif(GearSix, navMotifs.sakura(128, 128, 27), "spin", "SettingsGlyph");
/** 故事 (story plugin): a bookmark on the left page. Story-only; moves into the story plugin with #507. */
export const StoryGlyph = withMotif(BookOpenText, navMotifs.bookmark(52, 36, 30, 96), "flutter", "StoryGlyph");
