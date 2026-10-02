"""Public stage copy and existing diagnostic redaction for manual context work."""

from core.common.error_summary import summarize_exception_for_user
from core.compaction import NO_COMPLETE_TURNS, CompactionResult

_FAILURE_MESSAGES = {
    "memory": "记忆整理未完成，请稍后重试",
    "consumers": "记忆后续更新未完成，请稍后重试",
    "summary": "工作摘要生成失败，请稍后重试",
    "validation": "压缩结果校验失败，请稍后重试",
    "window": "上下文已变化，请重试",
    "no_turns": NO_COMPLETE_TURNS,
    "budget": "压缩后仍超出模型预算，请调整模型配置后重试",
    "busy": "上下文正在压缩，请稍后重试",
    "preparation": "上下文准备失败，请稍后重试",
    "minimal_preparation": "最小请求准备失败，请稍后重试",
    "minimal_budget": "当前输入及必要结果仍超出模型预算，请调整模型配置后重试",
    "provider": "模型请求失败，请稍后重试",
    "response": "模型未返回有效回复，请稍后重试",
}


def compaction_feedback(
    result: CompactionResult, error: BaseException | None = None
) -> dict:
    """Keep committed-memory facts while moving technical causes into details."""
    payload = result.dump()
    if not result.committed:
        payload["error"] = _FAILURE_MESSAGES.get(
            result.failure_stage, "上下文压缩未完成，请稍后重试"
        )
        payload["detail"] = summarize_exception_for_user(
            error or RuntimeError(result.error)
        )
    return payload
