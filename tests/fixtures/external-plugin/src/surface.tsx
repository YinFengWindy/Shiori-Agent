import React, { useEffect, useState } from "react";
import type { FixtureClient } from "./contract";

/** Visible surface uses the same backend through its injected client. */
function FixtureSurface({ surface, client }: { surface: { ready(): void }; client: FixtureClient }) {
  const [reply, setReply] = useState("");
  useEffect(() => { surface.ready(); }, [surface]);
  return <section className="external-demo">
    <h1>External surface {__FIXTURE_VERSION__}</h1>
    <button onClick={() => void client.call("inspect").then((result) => setReply(String(result.tool)))}>Surface RPC</button>
    <p>{reply}</p>
  </section>;
}

export default { pluginId: "external_demo", surface: { component: FixtureSurface } };
