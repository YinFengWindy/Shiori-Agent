import { BookmarkSimpleIcon } from "@phosphor-icons/react";
import { AbsoluteFill } from "remotion";
import { CHAT_SHOT, ChatMessages } from "../chatShot";
import { Pill, Pop } from "../overlay";
import { palette } from "../palette";
import { Screen, Shot, useSeconds } from "../screen";

/**
 * 角色与长期记忆: the conversation on chat.png plays out message by message;
 * when the user asks whether she remembers the travel book, a bookmark chip
 * — the memory she recalls — pops up beside her name before she answers.
 */
export function MemoryClip() {
  const s = useSeconds();
  return (
    <AbsoluteFill style={{ background: palette.neutral50 }}>
      <Screen origin="45% 40%">
        <Shot src={CHAT_SHOT} />
        <ChatMessages appearAt={[s(0.4), s(1.2), s(2.2), s(3.6), s(4.8), s(5.6)]} />
        <Pop at={s(2.8)} style={{ left: 380, top: 364 }}>
          <Pill icon={<BookmarkSimpleIcon size={20} weight="fill" color={palette.pink500} />}>
            想起：一起翻过的旅行随笔 · 海边灯塔那一页
          </Pill>
        </Pop>
      </Screen>
    </AbsoluteFill>
  );
}
