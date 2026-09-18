import React, { useEffect, useState } from "react";
import type { FixtureClient } from "./contract";

if (__RENDERER_FAILURE__) throw new Error("external fixture intentional UI initialization failure");

/** Exercise host React, backend RPC, plugin events and background communication. */
function FixturePage({ client }: { client: FixtureClient }) {
  const [result, setResult] = useState("");
  const [events, setEvents] = useState(0);
  useEffect(() => {
    let released = false;
    let dispose: (() => void) | undefined;
    void client.events.on("pulse", () => setEvents((value) => value + 1)).then((unsubscribe) => {
      if (released) unsubscribe(); else dispose = unsubscribe;
    });
    return () => { released = true; dispose?.(); };
  }, [client]);
  const inspect = async () => {
    const [backend, background] = await Promise.all([client.call("inspect"), client.background.call("inspect")]);
    setResult(JSON.stringify({ backend, background }));
  };
  return <section className="external-demo">
    <h1>External fixture {__FIXTURE_VERSION__}</h1>
    <button onClick={() => void inspect()}>Inspect all entries</button>
    <button onClick={() => void client.call("save", { value: "retained-user-value" }).then(inspect)}>Save retained data</button>
    <button onClick={() => void client.call("pulse").then(inspect)}>Send plugin event</button>
    <p data-testid="fixture-events">UI events {events}</p>
    <pre data-testid="fixture-result">{result}</pre>
  </section>;
}

/** Independently bundled contribution using the host's shared React instance. */
export default { pluginId: "external_demo", navPage: { label: "External lifecycle", component: FixturePage } };
