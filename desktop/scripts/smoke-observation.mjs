import { DesktopObservationController } from "../dist/observation/controller.js";

let enabled = false;
const states = [];
const frame = {
  frameId: "smoke-frame",
  capturedAt: "2026-07-23T12:00:00Z",
  width: 1280,
  height: 720,
  scaleFactor: 1,
  imageBase64: "ephemeral-smoke-frame",
};

const controller = new DesktopObservationController({
  bridge: {
    async invoke(request) {
      if (request.method === "observation.remember") {
        return { payload: { item_id: "smoke-memory" }, error: null };
      }
      return {
        payload: {
          frame_id: frame.frameId,
          captured_at: frame.capturedAt,
          width: frame.width,
          height: frame.height,
          scale_factor: frame.scaleFactor,
          interface_summary: "桌面 smoke",
          activity_key: "smoke",
          targets: [],
          risks: [],
          bubble: "我在这里",
          experience_candidate: "",
        },
        error: null,
      };
    },
  },
  pet: {
    isRunning: true,
    publishObservation(payload) {
      states.push(payload);
    },
  },
  getRoleId: () => "smoke-role",
  getEnabled: () => enabled,
  saveEnabled: async (next) => {
    enabled = next;
  },
  captureFrame: async () => frame,
  getIdleSeconds: () => 60,
});

await controller.start();
await controller.requestObservation();
if (!states.some((payload) => payload.status === "reviewing")) {
  throw new Error("observation smoke never entered reviewing state");
}
if (states.at(-1)?.status !== "observing" || states.at(-1)?.bubble !== "我在这里") {
  throw new Error("observation smoke did not publish a safe observing bubble");
}

await controller.stop();
if (enabled || states.at(-1)?.status !== "off") {
  throw new Error("observation smoke did not revoke consent cleanly");
}

console.log("desktop observation lifecycle ok");
