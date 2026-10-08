import { readStatusText } from "../shared/feedback/ReadStatus";

/** Status texts of the memory tab: page availability, the timeline and the document tabs. */
export const memoryStatusText = {
  ...readStatusText,
  pluginUnavailable: "记忆插件不可用",
  disabled: "语义记忆已停用",
  noItems: "暂无记忆",
  itemMissing: "记忆已不存在",
  documentEmpty: "文档为空",
  documentMissing: "文档缺失",
} as const;
