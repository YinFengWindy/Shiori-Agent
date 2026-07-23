import { DesktopObservationController } from "../dist/observation/controller.js";

const states = [];

const controller = new DesktopObservationController({
  pet: {
    isRunning: true,
    publishObservation(payload) {
      states.push(payload);
    },
  },
  getRoleId: () => "smoke-role",
});

await controller.restore();
controller.acceptRoleObservationReply("smoke-role", "我在这里");
if (states.at(-1)?.status !== "observing" || states.at(-1)?.bubble !== "我在这里") {
  throw new Error("observation smoke did not publish a role bubble");
}

console.log("desktop observation bubble lifecycle ok");
