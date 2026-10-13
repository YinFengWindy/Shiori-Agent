import { Img } from "remotion";
import avatar from "../../site/src/assets/art/avatar.webp";
import { cardStyle } from "./overlay";

/**
 * A message notice from 吟风 (her avatar, name, where it came from, the
 * text), as the overlays of the proactive and channel clips draw it.
 */
export function MessageNotice({ source, text, width = 420 }: { source: string; text: string; width?: number }) {
  return (
    <div style={{ ...cardStyle, width, display: "flex", gap: 14, padding: "16px 18px" }}>
      <Img src={avatar} style={{ width: 52, height: 52, borderRadius: 9999, flex: "none" }} />
      <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <span style={{ fontSize: 18, fontWeight: 700 }}>吟风</span>
          <span style={{ fontSize: 14, color: "var(--clip-meta-ink)" }}>{source}</span>
        </div>
        <div style={{ fontSize: 18, lineHeight: 1.5, color: "var(--clip-body-ink)" }}>{text}</div>
      </div>
    </div>
  );
}
