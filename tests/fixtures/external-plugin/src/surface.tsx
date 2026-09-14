import React from "react";

/** Default surface contribution follows the same injected-props ABI. */
export default {
  pluginId: "external_demo",
  surface: { component: () => <div className="external-demo">External surface</div> },
};
