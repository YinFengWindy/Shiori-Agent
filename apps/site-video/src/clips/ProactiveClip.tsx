import { ClockIcon } from "@phosphor-icons/react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { CHAT_SHOT } from "../chatShot";
import { MessageNotice } from "../notice";
import { Pill, Pop } from "../overlay";
import { palette } from "../palette";
import { progress, Screen, Shot, useSeconds } from "../screen";

/**
 * 主动找你: the chat on chat.png goes quiet, hours pass, and 吟风 writes
 * first — her notices slide in at the corner of the screen, one after the
 * other, while the window behind dims a little.
 */
export function ProactiveClip() {
  const frame = useCurrentFrame();
  const s = useSeconds();
  const dim = progress(frame, s(0.8), s(0.8)) * 0.35;
  return (
    <AbsoluteFill style={{ background: palette.neutral50 }}>
      <Screen zoom={0.03} origin="100% 100%">
        <Shot src={CHAT_SHOT} style={{ filter: `saturate(${1 - dim * 0.6}) brightness(${1 - dim * 0.12})` }} />
        <Pop at={s(0.8)} outAt={s(4.6)} style={{ left: 0, right: 0, top: 120, display: "flex", justifyContent: "center" }}>
          <Pill icon={<ClockIcon size={20} weight="bold" color={palette.blueGrad} />}>三小时后</Pill>
        </Pop>
        <Pop at={s(1.9)} rise={40} style={{ right: 36, bottom: 168 }}>
          <MessageNotice source="Shiori · 刚刚" text="在忙吗？河边的银杏全黄了，想拉你出去走走。" />
        </Pop>
        <Pop at={s(3.6)} rise={40} style={{ right: 36, bottom: 48 }}>
          <MessageNotice source="Shiori · 刚刚" text="……不理我的话，我就自己去咯。" />
        </Pop>
      </Screen>
    </AbsoluteFill>
  );
}
