import assert from "node:assert/strict";
import test from "node:test";
import { openVoiceInputStream } from "./captureController";

test("does not fall back to the default microphone when the configured device is missing", async () => {
  const calls: MediaStreamConstraints[] = [];
  const missingDevice = Object.assign(new Error("configured microphone is unavailable"), {
    name: "OverconstrainedError",
  });
  const mediaDevices = {
    getUserMedia: async (constraints: MediaStreamConstraints) => {
      calls.push(constraints);
      throw missingDevice;
    },
  };

  await assert.rejects(
    openVoiceInputStream(mediaDevices, "microphone-a"),
    (error: unknown) => error === missingDevice,
  );

  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0]?.audio, {
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
    deviceId: { exact: "microphone-a" },
  });
});
