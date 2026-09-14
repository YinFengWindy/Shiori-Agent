import React from "react";

/** Default UI contribution uses the host React instance. */
export default {
  pluginId: "external_demo",
  navPage: {
    label: "External demo",
    component: () => <div className="external-demo">External package ready</div>,
  },
};
