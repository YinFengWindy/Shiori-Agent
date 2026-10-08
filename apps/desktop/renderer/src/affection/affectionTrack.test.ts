import assert from "node:assert/strict";
import { it } from "node:test";
import { affectionTrack, affectionTrackPercent } from "./affectionTrack";

it("places a value on the whole -100–100 range, not within its stage", () => {
  assert.equal(affectionTrackPercent(95), 97.5);
  assert.equal(affectionTrackPercent(0), 50);
  assert.equal(affectionTrackPercent(-30), 35);
  assert.equal(affectionTrackPercent(-100), 0);
  assert.equal(affectionTrackPercent(130), 100);
});

it("splits the track into the 7 stages, highlighting the current one, with the floor marked instead of its tick", () => {
  const track = affectionTrack({ value: 95, stage: "挚爱", progress: 0.75, floor: 80 });
  assert.deepEqual(track.bands.map(({ stage, start, width }) => [stage, start, width]), [
    ["厌恶", 0, 25.5],
    ["冷淡", 25.5, 24.5],
    ["陌生", 50, 10],
    ["熟悉", 60, 10],
    ["朋友", 70, 10],
    ["亲密", 80, 10],
    ["挚爱", 90, 10],
  ]);
  assert.deepEqual(track.bands.filter((band) => band.current).map((band) => band.stage), ["挚爱"]);
  assert.deepEqual(track.bands.filter((band) => band.negative).map((band) => band.stage), ["厌恶", "冷淡"]);
  assert.equal(track.zero, 50);
  assert.equal(track.marker, 97.5);
  assert.equal(track.floor, 90);
  assert.deepEqual(track.ticks, [25.5, 60, 70, 80]);
});

it("has no floor marker while there is no floor", () => {
  const track = affectionTrack({ value: -30, stage: "冷淡", progress: 19 / 48, floor: null });
  assert.equal(track.floor, null);
  assert.equal(track.marker, 35);
  assert.deepEqual(track.ticks, [25.5, 60, 70, 80, 90]);
  assert.deepEqual(track.bands.filter((band) => band.current).map((band) => band.stage), ["冷淡"]);
});
