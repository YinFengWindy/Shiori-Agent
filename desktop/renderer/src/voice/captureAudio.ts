/** Converts one captured Float32 chunk to signed 16-bit PCM samples. */
export function float32ToPcm16(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length);
  for (let index = 0; index < input.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, input[index] ?? 0));
    output[index] = sample < 0 ? Math.round(sample * 32768) : Math.round(sample * 32767);
  }
  return output;
}

/** Resamples mono Float32 audio into the fixed 16kHz capture contract. */
export function resampleToVoiceRate(input: Float32Array, sourceRate: number): Float32Array {
  if (!Number.isFinite(sourceRate) || sourceRate <= 0) throw new Error("麦克风采样率无效");
  if (sourceRate === 16_000) return input.slice();
  const outputLength = Math.max(1, Math.round(input.length * 16_000 / sourceRate));
  const output = new Float32Array(outputLength);
  const ratio = sourceRate / 16_000;
  for (let index = 0; index < output.length; index += 1) {
    const sourcePosition = index * ratio;
    const left = Math.min(input.length - 1, Math.floor(sourcePosition));
    const right = Math.min(input.length - 1, left + 1);
    const fraction = sourcePosition - left;
    output[index] = (input[left] ?? 0) * (1 - fraction) + (input[right] ?? 0) * fraction;
  }
  return output;
}
