import type { PluginBackgroundSettled, PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { isRecord } from "../provider/guards";
import { readPresentationIdentity, type PetBinding, type PetGesture, type PetPresentationRequest, type PetProviderReport } from "../provider";

type Pending = { request: PetPresentationRequest; expected: PetProviderReport["kind"]; resolve: (report: PetProviderReport) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> };
/** Pending completion belongs to desktop_pet; service acceptance is not renderer readiness. */
export class PetPresentationTransport {
  private readonly pending = new Map<string, Pending>();
  private disposed = false;
  constructor(private readonly services: PluginRpcClient["services"], private readonly onReport: (report: PetProviderReport) => void, private readonly timeoutMs = 15_000) {}

  /** Registers completion before sending, including providers that report synchronously. */
  request(binding: PetBinding, leaseId: string, op: "prepare" | "show" | "hide" | "close", details: Partial<Pick<PetPresentationRequest, "state" | "position">> = {}): Promise<PetProviderReport> {
    if (this.disposed) return Promise.reject(new Error("桌宠已停用"));
    const request = this.command(binding, leaseId, op, details);
    const expected = op === "prepare" ? "ready" : op === "show" ? "shown" : op === "hide" ? "hidden" : "closed";
    const result = new Promise<PetProviderReport>((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(request.request_id); reject(new Error("桌宠形象响应超时")); }, this.timeoutMs);
      this.pending.set(request.request_id, { request, expected, resolve, reject, timer });
    });
    void this.send(binding, request).catch((error: unknown) => this.fail(request.request_id, error));
    return result;
  }

  /** State and actions are accepted as short service operations. */
  async update(binding: PetBinding, leaseId: string, op: "update" | "action", details: Partial<Pick<PetPresentationRequest, "state" | "command">>) {
    if (this.disposed) return;
    await this.send(binding, this.command(binding, leaseId, op, details));
  }

  /** Consumes only matching identities, so late results cannot complete a new selection. */
  report(value: unknown) {
    const identity = readPresentationIdentity(value);
    if (!identity || !isRecord(value)) throw new Error("形象回报身份无效");
    const kinds = ["ready", "shown", "hidden", "closed", "settled", "gesture", "failed", "lost"] as const;
    const kind = kinds.find((candidate) => candidate === value.kind);
    if (!kind) throw new Error("形象回报类型无效");
    const report: PetProviderReport = { ...identity, kind };
    if (typeof value.error === "string") report.error = value.error;
    if (value.placement !== undefined) report.placement = readPlacement(value.placement);
    if (value.gesture !== undefined) report.gesture = readGesture(value.gesture);
    const pending = this.pending.get(identity.request_id);
    if (pending && sameIdentity(pending.request, identity)) {
      if (kind === "failed" || kind === "lost") this.fail(identity.request_id, new Error(report.error || "桌宠形象加载失败"));
      else if (kind === pending.expected) { this.pending.delete(identity.request_id); clearTimeout(pending.timer); pending.resolve(report); }
    }
    this.onReport(report);
  }

  /** Cancels waiting requests immediately, leaving explicit close to the owner. */
  cancel(leaseId: string) {
    for (const [id, pending] of this.pending) if (pending.request.lease_id === leaseId) this.fail(id, new Error("桌宠呈现实例已撤销"));
  }

  /** Revokes every pending callback on background shutdown. */
  dispose() { this.disposed = true; for (const id of this.pending.keys()) this.fail(id, new Error("桌宠已停用")); }

  private command(binding: PetBinding, leaseId: string, op: PetPresentationRequest["op"], details: Partial<PetPresentationRequest>): PetPresentationRequest {
    return { ...details, request_id: crypto.randomUUID(), lease_id: leaseId, role_id: binding.role_id, model_id: binding.model.id, op };
  }
  private async send(binding: PetBinding, request: PetPresentationRequest) {
    await this.services.call(binding.provider, "present", request);
  }
  private fail(id: string, error: unknown) {
    const pending = this.pending.get(id);
    if (!pending) return;
    this.pending.delete(id); clearTimeout(pending.timer);
    pending.reject(error instanceof Error ? error : new Error(String(error)));
  }
}

function sameIdentity(a: PetPresentationRequest, b: Pick<PetPresentationRequest, "lease_id" | "role_id" | "model_id">) {
  return a.lease_id === b.lease_id && a.role_id === b.role_id && a.model_id === b.model_id;
}

function readGesture(value: unknown): PetGesture {
  if (isRecord(value)) {
    if (value.kind === "hide" || value.kind === "voice.stop" || value.kind === "bubble.dismiss") return { kind: value.kind };
    const gesture = (["press", "move", "release", "cancel"] as const).find((item) => item === value.gesture);
    if (value.kind === "voice.gesture" && gesture) return { kind: value.kind, gesture };
  }
  throw new Error("形象交互回报无效");
}

function readPlacement(value: unknown): PluginBackgroundSettled {
  if (!isRecord(value) || typeof value.displayId !== "string" || !isRecord(value.placement)) throw new Error("形象位置回报无效");
  const reason = (["create", "position", "extension", "drag", "momentum", "move", "ready"] as const).find((item) => item === value.reason);
  const { anchor, bodyOffset, workArea } = value.placement;
  if (!reason || !isRecord(anchor) || !isRecord(bodyOffset) || !isRecord(workArea)) throw new Error("形象位置回报无效");
  const number = (candidate: unknown) => { if (typeof candidate !== "number" || !Number.isFinite(candidate)) throw new Error("形象位置回报无效"); return candidate; };
  return { displayId: value.displayId, reason, placement: {
    anchor: { x: number(anchor.x), y: number(anchor.y) },
    bodyOffset: { x: number(bodyOffset.x), y: number(bodyOffset.y) },
    workArea: { x: number(workArea.x), y: number(workArea.y), width: number(workArea.width), height: number(workArea.height) },
  } };
}
