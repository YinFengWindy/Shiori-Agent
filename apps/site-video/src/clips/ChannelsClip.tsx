import { ChatsCircleIcon, ChatTeardropTextIcon, TelegramLogoIcon } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { AbsoluteFill, Img, useCurrentFrame } from "remotion";
import avatar from "../../../site/src/assets/art/avatar.webp";
import { CHAT_SHOT } from "../chatShot";
import { cardStyle, Pop } from "../overlay";
import { progress, Screen, Shot, useSeconds } from "../screen";

/** One channel window: its name, where it sits, when it arrives and 吟风's message in it. */
interface ChannelWindow {
  readonly name: string;
  readonly kind: string;
  readonly icon: ReactNode;
  readonly left: number;
  readonly top: number;
  readonly at: number;
  readonly text: string;
}

const iconProps = { size: 24, weight: "fill", color: "var(--clip-icon)" } as const;

const WINDOWS: readonly ChannelWindow[] = [
  { name: "Telegram", kind: "私聊", icon: <TelegramLogoIcon {...iconProps} />, left: 96, top: 210, at: 0.5, text: "到家了吗？今天风有点大，记得关窗。" },
  { name: "QQ", kind: "群聊", icon: <ChatsCircleIcon {...iconProps} />, left: 530, top: 280, at: 1.7, text: "@你 刚才说的那家书店，我也想去！" },
  { name: "飞书", kind: "私聊", icon: <ChatTeardropTextIcon {...iconProps} />, left: 964, top: 230, at: 2.9, text: "下午三点的会别忘了，要点我整理好了。" },
];

const WINDOW_WIDTH = 380;

/** Three typing dots, bouncing in turn. */
function TypingDots({ frame }: { frame: number }) {
  return (
    <div style={{ display: "flex", gap: 6, padding: "6px 2px" }}>
      {[0, 1, 2].map((dot) => (
        <span
          key={dot}
          style={{
            width: 9,
            height: 9,
            borderRadius: 9999,
            background: "var(--clip-meta-ink)",
            opacity: 0.4 + 0.6 * Math.max(0, Math.sin((frame - dot * 5) / 5)),
          }}
        />
      ))}
    </div>
  );
}

/**
 * 多渠道: behind a soft-focus Shiori window, Telegram, QQ and 飞书 chats
 * open one after another, and the same 吟风 types into each.
 */
export function ChannelsClip() {
  const frame = useCurrentFrame();
  const s = useSeconds();
  return (
    <AbsoluteFill style={{ background: "var(--clip-paper)" }}>
      <Screen zoom={0.03}>
        <Shot src={CHAT_SHOT} style={{ filter: "blur(10px) saturate(0.85)", transform: "scale(1.04)" }} />
        <AbsoluteFill style={{ background: "var(--clip-veil)" }} />
        {WINDOWS.map((window) => {
          const typedAt = s(window.at + 0.9);
          const typed = progress(frame, typedAt, s(0.3));
          return (
            <Pop key={window.name} at={s(window.at)} rise={36} style={{ left: window.left, top: window.top, width: WINDOW_WIDTH }}>
              <div style={{ ...cardStyle, overflow: "hidden" }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "14px 18px",
                    borderBottom: "1px solid var(--clip-edge)",
                    fontSize: 20,
                    fontWeight: 700,
                  }}
                >
                  {window.icon}
                  {window.name}
                  <span style={{ marginLeft: "auto", fontSize: 15, fontWeight: 400, color: "var(--clip-meta-ink)" }}>{window.kind}</span>
                </div>
                <div style={{ display: "flex", gap: 12, padding: "20px 18px 26px", minHeight: 150, background: "var(--clip-window-body)" }}>
                  <Img src={avatar} style={{ width: 44, height: 44, borderRadius: 9999, flex: "none" }} />
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span style={{ fontSize: 14, color: "var(--clip-meta-ink)" }}>吟风</span>
                    <div
                      style={{
                        padding: "10px 14px",
                        borderRadius: "var(--radius-md)",
                        background: "var(--clip-paper)",
                        boxShadow: "var(--clip-bubble-shadow)",
                        fontSize: 18,
                        lineHeight: 1.5,
                        color: "var(--clip-body-ink)",
                      }}
                    >
                      {typed > 0 ? <span style={{ opacity: typed }}>{window.text}</span> : <TypingDots frame={frame} />}
                    </div>
                  </div>
                </div>
              </div>
            </Pop>
          );
        })}
      </Screen>
    </AbsoluteFill>
  );
}
