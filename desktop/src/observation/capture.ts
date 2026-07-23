import { randomUUID } from "node:crypto";
import { desktopCapturer, screen } from "electron";
import { selectPrimaryDisplaySource } from "./primaryDisplay.js";
import { PrimaryDisplayUnavailableError, type CapturedObservationFrame } from "./types.js";

type PrimaryDisplayCaptureOptions = {
  screenLocked?: boolean;
};

/** Captures the current Windows primary display as an ephemeral PNG frame. */
export async function capturePrimaryDisplay(
  options: PrimaryDisplayCaptureOptions = {},
): Promise<CapturedObservationFrame> {
  if (options.screenLocked) {
    throw new PrimaryDisplayUnavailableError("Windows 已锁定，无法捕获主屏幕");
  }
  const primary = screen.getPrimaryDisplay();
  const thumbnailSize = {
    width: Math.max(1, Math.round(primary.size.width * primary.scaleFactor)),
    height: Math.max(1, Math.round(primary.size.height * primary.scaleFactor)),
  };
  const sources = await desktopCapturer.getSources({
    types: ["screen"],
    thumbnailSize,
    fetchWindowIcons: false,
  });
  const source = selectPrimaryDisplaySource(primary.id, sources);
  const png = source.thumbnail.toPNG();
  if (!png.length) throw new PrimaryDisplayUnavailableError("Windows 主屏幕捕获返回空帧");
  const actualSize = source.thumbnail.getSize();
  return {
    frameId: randomUUID(),
    capturedAt: new Date().toISOString(),
    width: actualSize.width,
    height: actualSize.height,
    scaleFactor: primary.scaleFactor,
    imageBase64: png.toString("base64"),
  };
}
