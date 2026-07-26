/** Converts one captured Float32 chunk to signed 16-bit PCM samples. */
export function float32ToPcm16(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length);
  for (let index = 0; index < input.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, input[index] ?? 0));
    output[index] = sample < 0 ? Math.round(sample * 32768) : Math.round(sample * 32767);
  }
  return output;
}

function reflectSampleIndex(index: number, length: number) {
  if (length <= 1) return 0;
  const period = length * 2 - 2;
  const wrapped = ((index % period) + period) % period;
  return wrapped < length ? wrapped : period - wrapped;
}

function sinc(value: number) {
  return Math.abs(value) < Number.EPSILON ? 1 : Math.sin(Math.PI * value) / (Math.PI * value);
}

function resampleWithLowPass(input: Float32Array, ratio: number, outputLength: number) {
  const output = new Float32Array(outputLength);
  const radius = Math.ceil(ratio * 4);
  const cutoff = 1 / ratio;
  for (let index = 0; index < output.length; index += 1) {
    const sourcePosition = (index + 0.5) * ratio - 0.5;
    let weighted = 0;
    let weight = 0;
    for (let sampleIndex = Math.floor(sourcePosition - radius); sampleIndex <= Math.ceil(sourcePosition + radius); sampleIndex += 1) {
      const distance = sampleIndex - sourcePosition;
      const windowPosition = Math.abs(distance) / radius;
      if (windowPosition >= 1) continue;
      const window = 0.42 + 0.5 * Math.cos(Math.PI * windowPosition) + 0.08 * Math.cos(2 * Math.PI * windowPosition);
      const kernel = cutoff * sinc(cutoff * distance) * window;
      weighted += (input[reflectSampleIndex(sampleIndex, input.length)] ?? 0) * kernel;
      weight += kernel;
    }
    output[index] = weight ? weighted / weight : 0;
  }
  return output;
}

/** Resamples mono Float32 audio into the fixed 16kHz capture contract. */
export function resampleToVoiceRate(input: Float32Array, sourceRate: number): Float32Array {
  if (!Number.isFinite(sourceRate) || sourceRate <= 0) throw new Error("麦克风采样率无效");
  if (sourceRate === 16_000) return input.slice();
  const outputLength = Math.max(1, Math.round(input.length * 16_000 / sourceRate));
  const ratio = sourceRate / 16_000;
  if (sourceRate > 16_000) return resampleWithLowPass(input, ratio, outputLength);
  const output = new Float32Array(outputLength);
  for (let index = 0; index < output.length; index += 1) {
    const sourcePosition = index * ratio;
    const left = Math.min(input.length - 1, Math.floor(sourcePosition));
    const right = Math.min(input.length - 1, left + 1);
    const fraction = sourcePosition - left;
    output[index] = (input[left] ?? 0) * (1 - fraction) + (input[right] ?? 0) * fraction;
  }
  return output;
}

/** Concatenates renderer chunks before resampling to preserve phase and boundaries. */
export function capturedChunksToPcm16(chunks: Float32Array[], sourceRate: number): Int16Array {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const input = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    input.set(chunk, offset);
    offset += chunk.length;
  }
  return float32ToPcm16(resampleToVoiceRate(input, sourceRate));
}
