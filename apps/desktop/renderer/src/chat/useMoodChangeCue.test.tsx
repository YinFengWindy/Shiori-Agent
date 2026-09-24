/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { useMoodChangeCue } from "./useMoodChangeCue";

function Probe(props: { scope: string; mood: string; updatedAt: string }) {
  const cue = useMoodChangeCue(props);
  return <output>{cue ? `${cue.id}:${cue.tone}` : "none"}</output>;
}

const fresh = () => new Date(Date.now() + 1000).toISOString();

describe("useMoodChangeCue", () => {
  it("stays quiet on mount and on a role switch, cues a live change with its tone", async () => {
    const view = await mountTestComponent(<Probe scope="rin|role:rin" mood="平静" updatedAt="" />);
    const read = () => view.container.querySelector("output")?.textContent;
    try {
      assert.equal(read(), "none");
      await view.render(<Probe scope="rin|role:rin" mood="害羞" updatedAt={fresh()} />);
      assert.equal(read(), "1:shy");
      await view.render(<Probe scope="natsu|role:natsu" mood="开心" updatedAt={fresh()} />);
      assert.equal(read(), "1:shy");
      await view.render(<Probe scope="natsu|role:natsu" mood="生气" updatedAt={fresh()} />);
      assert.equal(read(), "2:angry");
    } finally {
      await view.cleanup();
    }
  });
});
