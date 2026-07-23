import re


# 安全拦截时递减历史窗口的倍率序列：全量 → 减半 → 清空
_SAFETY_RETRY_RATIOS = (1.0, 0.5, 0.0)
# 单条工具结果的字符上限，防止大文件/长网页撑爆当轮上下文
_MAX_TOOL_RESULT_CHARS = 100_000
_TOOL_LOOP_REPEAT_LIMIT = 3  # 连续同签名工具调用达到该次数时判定循环
_SUMMARY_MAX_TOKENS = 512
_RETRIEVE_TRACE_SUMMARY_MAX = 240
_FLOW_TRIGGER_WORDS = (
    "步骤",
    "流程",
    "下次",
    "按这个逻辑",
)
_FLOW_SEQUENCE_PATTERN = re.compile(r"先.{0,20}再")

_INCOMPLETE_SUMMARY_PROMPT = """当前任务未在预算内完成，请直接输出给用户的中文收尾说明（不要提及系统/工具内部细节）。
必须包含三点：
1) 已完成到哪一步（基于当前上下文的事实）；
2) 目前还缺什么信息或步骤；
3) 下一步你会怎么继续。
禁止输出“已达到最大迭代次数”这类模板句；不要输出 JSON。"""
