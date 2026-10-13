import { HeartIcon } from "@phosphor-icons/react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import roleSettingsShot from "../../../../assets/readme/role-settings.png";
import { affectionMax, affectionMin, affectionStages } from "../../../desktop/renderer/src/affection/affectionStages";
import { cardStyle, Pop } from "../overlay";
import { palette } from "../palette";
import { easeOutSoft, progress, Screen, Shot, useSeconds } from "../screen";

/** Where the value sits on the track, 0–1. */
function trackShare(value: number) {
  return (value - affectionMin) / (affectionMax - affectionMin);
}

/** The stage a value falls in (the app's fixed stages, affectionStages.ts). */
function stageOf(value: number) {
  const stage = affectionStages.find((candidate) => value >= candidate.lower && value <= candidate.upper);
  if (!stage) throw new Error(`no affection stage for ${value}`);
  return stage;
}

/** The moments the clip's affection changes: when (seconds) and by how much, with the reason shown. */
const CHANGES = [
  { at: 1.4, delta: 3, reason: "陪她去旧书店" },
  { at: 2.9, delta: 3, reason: "记得她喜欢的那本书" },
  { at: 4.4, delta: 3, reason: "说好一起去海边" },
] as const;
const START_VALUE = 34;
const TRACK_WIDTH = 900;

/**
 * 好感度: over the role page (role-settings.png), the affection card fills
 * up step by step — +3 a turn — along the app's seven stages, 厌恶 to 挚爱,
 * and the stage name turns from 熟悉 to 朋友 when the value crosses 40.
 */
export function AffectionClip() {
  const frame = useCurrentFrame();
  const s = useSeconds();
  let value = START_VALUE;
  for (const change of CHANGES) value += change.delta * progress(frame, s(change.at), s(0.6));
  const stage = stageOf(Math.round(value));
  const crossedAt = s(CHANGES[1].at + 0.3);
  const stagePulse = interpolate(frame, [crossedAt, crossedAt + s(0.25), crossedAt + s(0.6)], [1, 1.18, 1], {
    easing: easeOutSoft,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: palette.neutral50 }}>
      <Screen origin="50% 70%">
        <Shot src={roleSettingsShot} />
        <Pop at={s(0.3)} style={{ left: 323, top: 380, width: 1057 }}>
          <div style={{ ...cardStyle, padding: "28px 40px 32px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 22, fontWeight: 700 }}>
              <HeartIcon size={26} weight="fill" color={palette.pink500} />
              好感度
              <span style={{ marginLeft: "auto", display: "flex", alignItems: "baseline", gap: 14 }}>
                <span
                  style={{
                    display: "inline-block",
                    padding: "4px 16px",
                    borderRadius: 9999,
                    background: palette.accent,
                    fontSize: 20,
                    transform: `scale(${stagePulse})`,
                  }}
                >
                  {stage.name}
                </span>
                <span style={{ fontVariantNumeric: "tabular-nums", fontSize: 30, minWidth: "2.2ch", textAlign: "right" }}>
                  {Math.round(value)}
                </span>
              </span>
            </div>
            <div style={{ position: "relative", width: TRACK_WIDTH, margin: "30px auto 0" }}>
              <div style={{ height: 12, borderRadius: 9999, background: palette.lavender200, overflow: "hidden" }}>
                <div style={{ width: `${trackShare(value) * 100}%`, height: "100%", borderRadius: 9999, background: palette.accentMedium }} />
              </div>
              {affectionStages.slice(1).map((boundary) => (
                <div
                  key={boundary.name}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: trackShare(boundary.lower) * TRACK_WIDTH,
                    width: 2,
                    height: 12,
                    background: palette.neutral50,
                  }}
                />
              ))}
              <div style={{ position: "relative", height: 28, marginTop: 10 }}>
                {affectionStages.map((candidate) => {
                  const middle = trackShare((candidate.lower + candidate.upper) / 2) * TRACK_WIDTH;
                  const current = candidate.name === stage.name;
                  return (
                    <span
                      key={candidate.name}
                      style={{
                        position: "absolute",
                        left: middle,
                        transform: "translateX(-50%)",
                        fontSize: 17,
                        fontWeight: current ? 700 : 400,
                        color: current ? palette.pinkGrad : palette.neutral600,
                      }}
                    >
                      {candidate.name}
                    </span>
                  );
                })}
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 22 }}>
              {CHANGES.map((change) => (
                <Pop key={change.reason} at={s(change.at)} rise={10} style={{ position: "relative" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 18, color: palette.neutral700 }}>
                    <span>{change.reason}</span>
                    <span style={{ color: palette.pinkGrad, fontWeight: 700 }}>+{change.delta}</span>
                  </div>
                </Pop>
              ))}
            </div>
          </div>
        </Pop>
      </Screen>
    </AbsoluteFill>
  );
}
