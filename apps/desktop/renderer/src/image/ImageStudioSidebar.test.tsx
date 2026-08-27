import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { ImageStudioSidebar } from "./ImageStudioSidebar";

describe("ImageStudioSidebar", () => {
  it("uses the shared secondary sidebar background", () => {
    const markup = renderToStaticMarkup(
      <ImageStudioSidebar
        bridgeReady
        collapsed={false}
        animating={false}
        width={280}
        form={{
          roleId: "",
          prompt: "",
          negativePrompt: "",
          mode: "txt2img",
          baseImagePath: "",
          strength: 0.7,
          noise: 0,
          sizePreset: "square",
          customWidth: "1024",
          customHeight: "1024",
          model: "",
        }}
        nsfwEnabled={false}
        addQualityTags={false}
        undesiredContentPreset={0}
        roleItems={[]}
        submitting={false}
        validationError=""
        onBackToChat={() => undefined}
        onBeginResize={() => undefined}
        onChange={() => undefined}
        onPickBaseImage={() => undefined}
        onSubmit={() => undefined}
        onToggleNsfwEnabled={() => undefined}
        onToggleAddQualityTags={() => undefined}
        onChangeUndesiredContentPreset={() => undefined}
      />,
    );

    assert.match(markup, /bg-\[#EFF4F9\]/);
    assert.doesNotMatch(markup, /bg-\[#EEF1F5\]/);
  });
});
