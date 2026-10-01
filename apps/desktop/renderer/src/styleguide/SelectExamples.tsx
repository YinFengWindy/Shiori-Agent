import { useState } from "react";
import { Select } from "@shiori/sdk";

const deviceOptions = [
  { value: "", label: "系统默认设备" },
  { value: "microphone", label: "桌面麦克风" },
  { value: "offline", label: "离线设备", disabled: true },
];
const longOptions = Array.from({ length: 40 }, (_, index) => ({
  value: String(index),
  label: `设备 ${index + 1} · ${index === 5 ? "ExternalMicrophoneWithAnExtremelyLongUnbrokenDeviceName" : "会议室麦克风"}`,
}));

/** Live shared-select samples for pointer, keyboard and clipped-container verification. */
export function SelectExamples() {
  const [device, setDevice] = useState("");
  const [longValue, setLongValue] = useState("0");
  return (
    <section className="mb-10" aria-labelledby="select-examples-title">
      <h2 id="select-examples-title" className="mb-4 font-display text-headline text-ink">下拉选择</h2>
      <div className="grid items-start gap-4 sm:grid-cols-2">
        <label className="grid gap-2 text-xs text-ink-secondary">麦克风设备
          <Select aria-label="麦克风设备示例" value={device} onValueChange={setDevice} options={deviceOptions} />
        </label>
        <label className="grid gap-2 text-xs text-ink-secondary">禁用设备
          <Select aria-label="禁用设备示例" value="" onValueChange={setDevice} options={deviceOptions} disabled />
        </label>
        <div className="h-24 overflow-hidden border-y border-line-soft py-2">
          <label className="grid gap-2 text-xs text-ink-secondary">音频输入
            <Select aria-label="长列表示例" value={longValue} onValueChange={setLongValue} options={longOptions} />
          </label>
        </div>
        <label className="grid gap-2 text-xs text-ink-secondary">无可用设备
          <Select aria-label="空列表示例" value="" onValueChange={setDevice} options={[]} />
        </label>
      </div>
    </section>
  );
}
