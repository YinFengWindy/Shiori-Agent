import { BookOpenText } from "@phosphor-icons/react";
import { navMotifs, withMotif } from "@yinfengwindy/shiori-sdk";

/** 故事 nav glyph: a bookmark on the left page of the open book. */
export const StoryGlyph = withMotif(BookOpenText, navMotifs.bookmark(52, 36, 30, 96), "flutter", "StoryGlyph");
