/** The fixed PCM contract expected by the first-version ASR adapter. */
export const VOICE_SAMPLE_RATE = 16_000;
export const VOICE_CHANNELS = 1;
export const VOICE_SAMPLE_WIDTH_BYTES = 2;

/**
 * Encodes signed 16-bit little-endian PCM samples as a mono WAV container.
 *
 * The function deliberately accepts samples rather than a raw Buffer so the
 * recorder boundary can validate channel mixing before data reaches ASR.
 */
export function encodeVoiceWav(samples: Int16Array): Uint8Array {
  const dataLength = samples.length * VOICE_SAMPLE_WIDTH_BYTES;
  const output = new Uint8Array(44 + dataLength);
  const view = new DataView(output.buffer);
  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + dataLength, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, VOICE_CHANNELS, true);
  view.setUint32(24, VOICE_SAMPLE_RATE, true);
  view.setUint32(28, VOICE_SAMPLE_RATE * VOICE_CHANNELS * VOICE_SAMPLE_WIDTH_BYTES, true);
  view.setUint16(32, VOICE_CHANNELS * VOICE_SAMPLE_WIDTH_BYTES, true);
  view.setUint16(34, VOICE_SAMPLE_WIDTH_BYTES * 8, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, dataLength, true);
  for (let index = 0; index < samples.length; index += 1) {
    view.setInt16(44 + index * VOICE_SAMPLE_WIDTH_BYTES, samples[index], true);
  }
  return output;
}

function writeAscii(view: DataView, offset: number, value: string): void {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}
