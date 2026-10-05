import { useState } from "react";
import { FileCode, ImageSquare } from "@phosphor-icons/react";
import { cx } from "@yinfengwindy/shiori-sdk";
import type { RoleCardExportFormat, RoleCardExportPreview as ExportPreview } from "../../../src/bridge/roleCardExportContract";

/** The actual exported cover/gallery, or a text-only JSON file preview. */
export function RoleCardExportPreview({ preview, format, loading }: {
  preview: ExportPreview | null;
  format: RoleCardExportFormat;
  loading: boolean;
}) {
  const [selected, setSelected] = useState(0);
  const image = preview?.assets[selected];
  return <section aria-label="导出预览" className="mx-auto grid w-full max-w-[200px] gap-3 sm:max-w-[280px]">
    <div className="relative flex aspect-[4/5] min-w-0 items-center justify-center overflow-hidden rounded-md border border-line-soft bg-gradient-accent-soft shadow-soft">
      {loading ? <div role="status" className="grid justify-items-center gap-3 text-body text-ink-muted">
        <ImageSquare className="h-10 w-10 opacity-40" aria-hidden="true" /><span>正在准备预览…</span>
      </div> : format === "json" ? <div className="grid w-full justify-items-center gap-5 px-6 text-center">
        <div className="grid h-20 w-20 place-items-center rounded-md border border-line-soft bg-surface shadow-soft"><FileCode className="h-10 w-10 text-accent-text" aria-hidden="true" /></div>
        <div className="grid min-w-0 gap-2"><span className="break-words text-body font-medium text-ink [overflow-wrap:anywhere]">{preview ? `${preview.name}.json` : "JSON"}</span><span className="text-caption text-ink-muted">角色资料</span></div>
      </div> : image ? <img src={image.preview_url} alt={image.labels.join("、")} className="h-full w-full object-contain" /> :
        <div className="grid justify-items-center gap-3 text-ink-muted"><ImageSquare className="h-12 w-12 opacity-50" aria-hidden="true" /><span className="text-body">无图片素材</span></div>}
    </div>
    {image && !loading ? <p className="text-center text-caption text-ink-secondary">{image.labels.join(" · ")}</p> : null}
    {format === "charx" && preview && preview.assets.length > 1 ? <div aria-label="导出图片" className="grid grid-cols-5 gap-2">
      {preview.assets.map((asset, index) => <button type="button" key={index} aria-label={`预览 ${asset.labels.join("、")}`} aria-pressed={index === selected}
        className={cx("aspect-square overflow-hidden rounded-md border bg-surface-soft p-0.5", index === selected ? "border-line-accent ring-1 ring-accent" : "border-line-soft")}
        onClick={() => setSelected(index)}><img src={asset.preview_url} alt="" className="h-full w-full rounded-md object-contain" /></button>)}
    </div> : null}
  </section>;
}
