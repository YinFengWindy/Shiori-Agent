import { readStatusText } from "../shared/feedback/ReadStatus";

/** Status texts of the memory tab: page availability, the timeline and the document tabs. */
export const memoryStatusText = {
  ...readStatusText,
  closed: "记忆已关闭",
  disabled: "语义记忆已停用",
  noItems: "暂无记忆",
  itemMissing: "记忆已不存在",
  documentEmpty: "文档为空",
  documentMissing: "文档缺失",
} as const;
