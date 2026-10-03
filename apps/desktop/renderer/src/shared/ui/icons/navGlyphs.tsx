import { Chats, GearSix, MagnifyingGlass, Users } from "@phosphor-icons/react";
import { navMotifs, withMotif } from "@yinfengwindy/shiori-sdk";

/** 搜索: a sparkle in the lens. */
export const SearchGlyph = withMotif(MagnifyingGlass, navMotifs.sparkle(88, 88, 30, { cx: 128, cy: 70, r: 7 }), "twinkle", "SearchGlyph");
/** 消息: a heart in the back bubble. */
export const ChatsGlyph = withMotif(Chats, navMotifs.heart(104, 94, 3.1), "beat", "ChatsGlyph");
/** 角色: a ribbon bow on the front head. */
export const RolesGlyph = withMotif(Users, navMotifs.ribbon(84, 58, 5.2), "wiggle", "RolesGlyph");
/** 设置: a sakura in the gear hole. */
export const SettingsGlyph = withMotif(GearSix, navMotifs.sakura(128, 128, 27), "spin", "SettingsGlyph");
