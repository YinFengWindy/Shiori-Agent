"""Read only structured, current-run stage reports; terminal text is never evidence."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import CodingTask, now

type Stage = Literal[
    "preparing", "analysis", "implementation", "validation", "pull_request"
]


class ProgressReport(BaseModel):
    """One complete JSONL record written by the coding agent for this run."""

    model_config = ConfigDict(extra="forbid", strict=True)
    task_id: str
    run_id: str
    sequence: int = Field(ge=1)
    stage: Stage
    detail: str = Field(default="", max_length=2000)


def record_stage(
    task: CodingTask,
    stage: Stage,
    detail: str,
    *,
    source: str = "host",
    sequence: int = 0,
) -> None:
    """Record an observed stage, including legitimate returns to implementation."""
    observed_at = now()
    task.stage = stage
    task.progress_events.append(
        {
            "run_id": task.run_id,
            "sequence": sequence,
            "stage": stage,
            "detail": detail,
            "source": source,
            "observed_at": observed_at,
        }
    )
    del task.progress_events[:-100]


def read_progress(task: CodingTask) -> bool:
    """Consume bounded, complete lines; partial, duplicate and old-run lines do not advance."""
    path = task.progress_path
    try:
        with path.open("rb") as stream:
            data = stream.read(262145)
        if len(data) > 262144:
            task.progress_notice = "阶段报告超过读取上限，保留最后已确认阶段"
            return False
        content = data.decode("utf-8")
    except FileNotFoundError:
        return False
    except (OSError, UnicodeError) as error:
        task.progress_notice = f"阶段报告暂不可读：{error}"
        return False
    changed = False
    for line in content.splitlines(keepends=True)[-200:]:
        if not line.endswith("\n"):
            continue  # An in-progress append is not a complete report.
        try:
            report = ProgressReport.model_validate(json.loads(line))
        except (ValueError, ValidationError):
            task.progress_notice = "阶段报告格式无效，保留最后已确认阶段"
            continue
        if (
            report.task_id != task.id
            or report.run_id != task.run_id
            or report.sequence <= task.progress_sequence
        ):
            continue
        task.progress_sequence = report.sequence
        task.progress_notice = ""
        record_stage(
            task, report.stage, report.detail, source="agent", sequence=report.sequence
        )
        changed = True
    return changed


def progress_instructions(task: CodingTask) -> str:
    """Ask for stage reports in the current task artifact directory, without fake percentages."""
    example = {
        "task_id": task.id,
        "run_id": task.run_id,
        "sequence": 1,
        "stage": "analysis",
        "detail": "正在确认相关模块与验收条件",
    }
    return (
        f"阶段报告路径：{task.progress_path}\n"
        "开始工作及实际阶段切换时，在该 UTF-8 JSONL 文件追加一条完整 JSON 并换行。"
        "每回合 sequence 从1递增；stage 可选 preparing/analysis/implementation/validation/pull_request。"
        "验证失败回到实现时应报告 implementation；detail 简述正在进行的真实活动。"
        "不得预先报告未执行阶段，不写百分比或预计完成时间，终端回显不算阶段报告。"
        "文件不超过256KiB，每条detail不超过2000字符。报告格式：\n"
        + json.dumps(example, ensure_ascii=False)
        + "\n\n"
    )
