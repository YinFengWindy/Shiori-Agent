import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { SettingsSidebar } from "./SettingsSidebar";

describe("SettingsSidebar", () => {
  it("uses the settings navigation background", () => {
    const markup = renderToStaticMarkup(
      <SettingsSidebar
        activeSection="models"
        dirty={false}
        collapsed={false}
        animating={false}
        width={240}
        onBackToChat={() => undefined}
        onOpenSection={() => undefined}
        onSearchChange={() => undefined}
        onBeginResize={() => undefined}
        search=""
      />,
    );

    assert.match(markup, /bg-\[#EFF4F9\]/);
    assert.doesNotMatch(markup, /bg-\[#EEF1F5\]/);
  });
});
