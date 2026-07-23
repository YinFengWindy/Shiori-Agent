import type { BridgeRequest, BridgeResponse } from "../shared.js";
import { isScreenshotObservationRequest, parseObservationResult } from "./result.js";
import type { CapturedObservationFrame, ObservationResult } from "./types.js";

const maximumScreenshotRefreshes = 1;

type ObservationRequestOptions = {
  bridge: {
    invoke(request: Omit<BridgeRequest, "id">): Promise<{
      payload: Record<string, unknown>;
      error: BridgeResponse["error"];
    }>;
  };
  roleId: string;
  captureFrame: () => Promise<CapturedObservationFrame>;
  previousResult: ObservationResult | null;
  recentBubbles: readonly string[];
  isCurrent: () => boolean;
};

/** Runs one bounded observation-model exchange and at most one requested refresh. */
export async function requestObservationResult(
  options: ObservationRequestOptions,
): Promise<ObservationResult | null> {
  let screenshotRefreshes = 0;
  while (true) {
    const frame = await options.captureFrame();
    if (!options.isCurrent()) return null;
    const response = await options.bridge.invoke({
      method: "observation.analyze",
      payload: {
        role_id: options.roleId,
        frame_id: frame.frameId,
        captured_at: frame.capturedAt,
        width: frame.width,
        height: frame.height,
        scale_factor: frame.scaleFactor,
        image_base64: frame.imageBase64,
        previous_observation: options.previousResult ? {
          captured_at: options.previousResult.capturedAt,
          interface_summary: options.previousResult.interfaceSummary,
          activity_key: options.previousResult.activityKey,
        } : null,
        recent_bubbles: options.recentBubbles,
      },
    });
    if (!options.isCurrent()) return null;
    if (response.error) throw new Error(response.error.message);
    if (isScreenshotObservationRequest(response.payload)) {
      if (screenshotRefreshes >= maximumScreenshotRefreshes) {
        throw new Error("观察模型重复请求截图");
      }
      screenshotRefreshes += 1;
      continue;
    }
    return parseObservationResult(response.payload, frame);
  }
}
