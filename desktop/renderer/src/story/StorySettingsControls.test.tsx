/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { SpeakerHigh } from "@phosphor-icons/react";
import { StorySegmentedControl, StoryToggle, StoryVolumeControl } from "./StorySettingsControls";

describe("StorySettingsControls", () => {
  it("renders option, switch, and slider controls with accessible state", () => {
    const segmentedMarkup = renderToStaticMarkup(
      <StorySegmentedControl
        value="normal"
        options={[{ value: "slow", label: "慢" }, { value: "normal", label: "标准" }, { value: "fast", label: "快" }]}
        ariaLabel="文字速度"
        onChange={() => undefined}
      />,
    );
    const toggleMarkup = renderToStaticMarkup(<StoryToggle checked onChange={() => undefined} label="立即显示全文" />);
    const volumeMarkup = renderToStaticMarkup(<StoryVolumeControl id="story-voice-volume" label="语音" icon={<SpeakerHigh />} value={70} onChange={() => undefined} />);

    assert.match(segmentedMarkup, /role="group"/);
    assert.match(segmentedMarkup, /aria-label="文字速度"/);
    assert.match(segmentedMarkup, /aria-pressed="true"/);
    assert.match(toggleMarkup, /role="switch"/);
    assert.match(toggleMarkup, /aria-checked="true"/);
    assert.match(volumeMarkup, /type="range"/);
    assert.match(volumeMarkup, /aria-label="语音"/);
    assert.match(volumeMarkup, />70%<\/output>/);
  });
});
