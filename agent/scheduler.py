"""
Scheduler: 定时任务核心模块

组件：
  LatencyTracker     — 自适应 P90 延迟估算（软实时预触发）
  parse_duration     — "30s" / "5m" / "2h" 等时长解析
  parse_when_at      — "14:30" / ISO datetime 解析
  is_cron_expr       — 判断是否是 cron 表达式
  compute_fire_at    — 计算首次触发时间（含 request_time 延迟补偿）
  compute_actual_trigger — 计算实际触发时间（SOFT 提前 P90）
  ScheduledJob       — 任务数据类
  JobStore           — JSON 持久化
  SchedulerService   — 主调度服务（asyncio tick 循环）
"""

import asyncio
import logging
import re
import statistics
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.common.timekit import parse_iso as _parse_iso
from infra.persistence.json_store import atomic_save_json, load_json
from agent.scheduler_cron import is_cron_expr, next_cron_fire

logger = logging.getLogger(__name__)

DEFAULT_SCHEDULE_TIMEZONE = "Asia/Shanghai"


# ── LatencyTracker ───────────────────────────────────────────────


class LatencyTracker:
    """滑动窗口 P90 延迟追踪，用于 SOFT tier 预触发偏移量自适应。"""

    def __init__(self, default: float = 25.0, window: int = 20) -> None:
        self._samples: deque[float] = deque(maxlen=window)
        self.default = default

    def record(self, elapsed: float) -> None:
        self._samples.append(elapsed)

    @property
    def lead(self) -> float:
        """返回 P90 估算值；样本不足 3 个时返回 default。"""
        if len(self._samples) < 3:
            return self.default
        return statistics.quantiles(list(self._samples), n=10)[8]


# ── Time Parsing ─────────────────────────────────────────────────

_DURATION_RE = re.compile(r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")


def parse_duration(s: str) -> timedelta:
    """解析时长字符串，如 '30s', '5m', '2h', '1h30m', '1d2h'。"""
    s = s.strip()
    m = _DURATION_RE.match(s)
    if not m or not any(m.groups()):
        raise ValueError(f"无效的时间间隔: {s!r}，示例: '30s', '5m', '2h', '1h30m'")
    days, hours, minutes, seconds = (int(x or 0) for x in m.groups())
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def parse_when_at(
    s: str,
    tz: str = DEFAULT_SCHEDULE_TIMEZONE,
    _now_fn: Callable[[], datetime] | None = None,
) -> datetime:
    """解析 'at' 时间：HH:MM（自动判断今天/明天）或 ISO datetime。"""
    tzinfo = ZoneInfo(tz)
    now_fn = _now_fn or (lambda: datetime.now(tzinfo))
    s = s.strip()

    # HH:MM 格式
    if re.match(r"^\d{1,2}:\d{2}$", s):
        now = now_fn()
        t = datetime.strptime(s, "%H:%M").time()
        dt = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if dt <= now:
            dt += timedelta(days=1)
        return dt

    # ISO datetime 格式
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tzinfo)
        return dt
    except ValueError:
        pass

    raise ValueError(f"无法解析时间: {s!r}，示例: '14:30', '2025-06-01T09:00'")


# ── fire_at Computation ──────────────────────────────────────────


def compute_fire_at(
    trigger: str,
    when: str,
    tz: str = DEFAULT_SCHEDULE_TIMEZONE,
    request_time: str | None = None,
    _now_fn: Callable[[], datetime] | None = None,
) -> datetime:
    """
    计算首次触发时间。

    after 模式：以 request_time（用户消息到达时间）为基准，
                补偿 AI 推理延迟，确保 fire_at 从用户视角算起。
    """
    tzinfo = ZoneInfo(tz)
    now_fn = _now_fn or (lambda: datetime.now(tzinfo))

    if trigger == "at":
        return parse_when_at(when, tz, _now_fn)

    if trigger == "after":
        duration = parse_duration(when)
        if request_time:
            base = datetime.fromisoformat(request_time)
            if base.tzinfo is None:
                base = base.replace(tzinfo=tzinfo)
        else:
            base = now_fn()
        return base + duration

    if trigger == "every":
        if is_cron_expr(when):
            return next_cron_fire(when, tz, now_fn())
        interval = parse_duration(when)
        return now_fn() + interval

    raise ValueError(f"未知触发类型: {trigger!r}，须为 at/after/every")


def compute_actual_trigger(
    fire_at: datetime,
    tier: str,
    tracker: LatencyTracker,
) -> datetime:
    """
    计算实际触发时刻。

    INSTANT: 等于 fire_at（直接推送，无 AI 延迟）
    SOFT:    fire_at - P90（提前触发 AI，让 AI 在 fire_at 前完成处理）
    """
    if tier == "instant":
        return fire_at
    return fire_at - timedelta(seconds=tracker.lead)


# ── ScheduledJob ─────────────────────────────────────────────────


@dataclass
class ScheduledJob:
    trigger: str  # "at" | "after" | "every"
    tier: str  # "instant" | "soft"
    fire_at: datetime  # 下次名义触发时间（UTC-aware）
    channel: str
    chat_id: str
    role_id: str = ""
    role_config_version: str = ""
    thread_id: str = ""
    delivery_key: str = ""

    interval_seconds: int | None = None  # every + interval 模式
    cron_expr: str | None = None  # every + cron 模式

    message: str | None = None  # instant tier
    prompt: str | None = None  # soft tier

    name: str | None = None
    timezone: str = DEFAULT_SCHEDULE_TIMEZONE
    when: str = ""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    run_count: int = 0
    enabled: bool = True
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


# ── JobStore ─────────────────────────────────────────────────────


class JobStore:
    """JSON 文件持久化，读写 ScheduledJob 列表。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[ScheduledJob]:
        # 1. 读取原始列表
        raw = load_json(self.path, default=[], domain="job_store")
        if not isinstance(raw, list):
            raise ValueError("任务清单格式无效：根节点必须是数组")

        # 2. 反序列化
        try:
            return [self._from_dict(d) for d in raw]
        except Exception as e:
            logger.error("[job_store] 反序列化失败: %s", e)
            raise

    def save(self, jobs: dict[str, ScheduledJob]) -> None:
        data = [self._to_dict(j) for j in jobs.values()]
        atomic_save_json(self.path, data, domain="job_store")

    # ── private ──

    def _to_dict(self, job: ScheduledJob) -> dict[str, Any]:
        d = asdict(job)
        d["fire_at"] = job.fire_at.isoformat()
        d["created_at"] = job.created_at.isoformat()
        return d

    def _from_dict(self, d: dict[str, Any]) -> ScheduledJob:
        d = dict(d)
        channel = str(d.get("channel") or "").strip()
        chat_id = str(d.get("chat_id") or "").strip()
        if (
            not str(d.get("role_id") or "").strip()
            and channel == "desktop"
            and chat_id.startswith("role:")
        ):
            d["role_id"] = chat_id.removeprefix("role:").strip()
        d["fire_at"] = self._parse_dt(d["fire_at"])
        d["created_at"] = self._parse_dt(d["created_at"])
        return ScheduledJob(**d)

    @staticmethod
    def _parse_dt(s: str) -> datetime:
        return _parse_iso(s) or datetime.now(timezone.utc)


# ── SchedulerService ─────────────────────────────────────────────


class SchedulerService:
    """
    asyncio 定时任务服务。

    - 每秒 tick 一次，检查 actual_trigger <= now 的 job
    - INSTANT: 直接 message_push
    - SOFT: process_direct + 记录延迟 + push 响应
    - 持久化到 JSON，重启后自动恢复
    """

    GRACE_SECONDS = 300  # 5分钟内的 misfire 仍执行

    def __init__(
        self,
        store_path: Path,
        push_tool: Any,
        agent_loop: Any = None,
        agent_loop_provider: Callable[[], Any] | None = None,
        tracker: LatencyTracker | None = None,
        _now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = JobStore(store_path)
        self.push_tool = push_tool
        self.agent_loop = agent_loop
        self._agent_loop_provider = agent_loop_provider
        self.tracker = tracker or LatencyTracker()
        self._now = _now_fn or (lambda: datetime.now(timezone.utc))
        self._jobs: dict[str, ScheduledJob] = {}
        self._in_flight: set[str] = set()
        self._active_tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False

    # ── Public API ───────────────────────────────────────────────

    async def run(self) -> None:
        self.load_and_recover()
        self._running = True
        logger.info("SchedulerService started")
        while self._running:
            await asyncio.sleep(1)
            await self._tick()

    def stop(self) -> None:
        self._running = False
        for job_id, task in list(self._active_tasks.items()):
            task.cancel()
            self._active_tasks.pop(job_id, None)

    def add_job(self, job: ScheduledJob) -> None:
        # Ensure fire_at is UTC-aware
        if job.fire_at.tzinfo is None:
            job.fire_at = job.fire_at.replace(tzinfo=timezone.utc)
        next_jobs = {**self._jobs, job.id: job}
        self._replace_jobs(next_jobs)
        logger.info(
            f"Job added: {job.id[:8]} tier={job.tier} trigger={job.trigger} "
            f"fire_at={job.fire_at.isoformat()}"
        )

    def create_job(
        self,
        *,
        name: str,
        tier: str,
        trigger: str,
        when: str,
        content: str,
        timezone_name: str,
        channel: str,
        chat_id: str,
        role_id: str = "",
        role_config_version: str = "",
        thread_id: str = "",
        delivery_key: str = "",
        request_time: str | None = None,
    ) -> ScheduledJob:
        """Validates, persists, and registers one new scheduled job atomically."""
        job = self._build_job(
            name=name,
            tier=tier,
            trigger=trigger,
            when=when,
            content=content,
            timezone_name=timezone_name,
            channel=channel,
            chat_id=chat_id,
            role_id=role_id,
            role_config_version=role_config_version,
            thread_id=thread_id,
            delivery_key=delivery_key,
            request_time=request_time,
        )
        self.add_job(job)
        return job

    def update_job(
        self,
        job_id: str,
        *,
        role_id: str,
        name: str,
        tier: str,
        trigger: str,
        when: str,
        content: str,
        timezone_name: str,
    ) -> ScheduledJob:
        """Replaces an idle role-owned job after validating the complete update."""
        current = self._jobs.get(job_id)
        if current is None or current.role_id != role_id:
            raise KeyError("角色任务不存在")
        if self.is_job_active(job_id) or job_id in self._in_flight:
            raise RuntimeError("正在运行的计划任务不能编辑")

        updated = self._build_job(
            name=name,
            tier=tier,
            trigger=trigger,
            when=when,
            content=content,
            timezone_name=timezone_name,
            channel=current.channel,
            chat_id=current.chat_id,
            role_id=current.role_id,
            role_config_version=current.role_config_version,
            thread_id=current.thread_id,
            delivery_key=current.delivery_key,
            existing=current,
        )
        next_jobs = {**self._jobs, job_id: updated}
        self._replace_jobs(next_jobs)
        logger.info(
            "Job updated: %s tier=%s trigger=%s fire_at=%s",
            job_id[:8],
            updated.tier,
            updated.trigger,
            updated.fire_at.isoformat(),
        )
        return updated

    def cancel_job(self, job_id: str) -> bool:
        if job_id not in self._jobs:
            return False
        next_jobs = {key: job for key, job in self._jobs.items() if key != job_id}
        self._replace_jobs(next_jobs)
        active_task = self._active_tasks.pop(job_id, None)
        if active_task is not None:
            active_task.cancel()
        return True

    def is_job_active(self, job_id: str) -> bool:
        """Returns whether a scheduled job currently has running work."""
        task = self._active_tasks.get(job_id)
        return task is not None and not task.done()

    def cancel_job_by_name(self, name: str) -> list[str]:
        cancelled = [jid for jid, j in self._jobs.items() if j.name == name]
        if cancelled:
            cancelled_ids = set(cancelled)
            self._replace_jobs(
                {
                    job_id: job
                    for job_id, job in self._jobs.items()
                    if job_id not in cancelled_ids
                }
            )
        return cancelled

    def list_jobs(self) -> list[ScheduledJob]:
        return list(self._jobs.values())

    def load_and_recover(self) -> None:
        """启动时加载持久化 jobs，处理 misfire。"""
        now = self._now()
        jobs = self.store.load()
        count_loaded = 0
        jobs_changed = False

        for job in jobs:
            if not job.enabled:
                continue

            if job.fire_at.tzinfo is None:
                job.fire_at = job.fire_at.replace(tzinfo=timezone.utc)
                jobs_changed = True

            if job.trigger == "every" and job.cron_expr and job.fire_at > now:
                normalized_fire_at = next_cron_fire(job.cron_expr, job.timezone, now)
                if normalized_fire_at != job.fire_at:
                    job.fire_at = normalized_fire_at
                    jobs_changed = True

            if job.fire_at <= now:
                age = (now - job.fire_at).total_seconds()
                if job.trigger == "every":
                    # 推进到下一个未来时间
                    job.fire_at = self._advance_every(job, now)
                    jobs_changed = True
                    self._jobs[job.id] = job
                    count_loaded += 1
                elif age <= self.GRACE_SECONDS:
                    # 在宽限期内，保留（下次 tick 会执行）
                    self._jobs[job.id] = job
                    count_loaded += 1
                else:
                    logger.info(
                        f"Job {job.id[:8]} ({job.name or 'unnamed'}) expired "
                        f"{age:.0f}s ago, beyond grace period — discarded"
                    )
                    jobs_changed = True
            else:
                self._jobs[job.id] = job
                count_loaded += 1

        if jobs_changed:
            self.store.save(self._jobs)
        logger.info(f"SchedulerService recovered {count_loaded} jobs")

    def _build_job(
        self,
        *,
        name: str,
        tier: str,
        trigger: str,
        when: str,
        content: str,
        timezone_name: str,
        channel: str,
        chat_id: str,
        role_id: str,
        role_config_version: str,
        thread_id: str,
        delivery_key: str,
        request_time: str | None = None,
        existing: ScheduledJob | None = None,
    ) -> ScheduledJob:
        normalized_name = name.strip()
        normalized_when = when.strip()
        normalized_content = content.strip()
        normalized_timezone = timezone_name.strip()
        if not normalized_name:
            raise ValueError("任务名称不能为空")
        if tier not in ("instant", "soft"):
            raise ValueError("执行模式须为 instant 或 soft")
        if trigger not in ("at", "after", "every"):
            raise ValueError("触发方式须为 at、after 或 every")
        if not normalized_when:
            raise ValueError("执行时间不能为空")
        if not normalized_content:
            raise ValueError("执行内容不能为空")
        if not channel.strip() or not chat_id.strip():
            raise ValueError("channel 和 chat_id 不能为空")
        try:
            tzinfo = ZoneInfo(normalized_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"无效的时区 {normalized_timezone!r}") from exc

        fire_at = compute_fire_at(
            trigger,
            normalized_when,
            normalized_timezone,
            request_time,
            _now_fn=lambda: self._now().astimezone(tzinfo),
        )
        interval_seconds = None
        cron_expr = None
        if trigger == "every":
            if is_cron_expr(normalized_when):
                cron_expr = normalized_when
            else:
                interval_seconds = int(parse_duration(normalized_when).total_seconds())

        return ScheduledJob(
            trigger=trigger,
            tier=tier,
            fire_at=fire_at,
            channel=channel.strip(),
            chat_id=chat_id.strip(),
            role_id=role_id.strip(),
            role_config_version=role_config_version.strip(),
            thread_id=thread_id.strip(),
            delivery_key=delivery_key.strip(),
            interval_seconds=interval_seconds,
            cron_expr=cron_expr,
            message=normalized_content if tier == "instant" else None,
            prompt=normalized_content if tier == "soft" else None,
            name=normalized_name,
            timezone=normalized_timezone,
            when=normalized_when,
            created_at=existing.created_at if existing else self._now(),
            run_count=existing.run_count if existing else 0,
            enabled=existing.enabled if existing else True,
            id=existing.id if existing else str(uuid.uuid4()),
        )

    def _replace_jobs(self, jobs: dict[str, ScheduledJob]) -> None:
        self.store.save(jobs)
        self._jobs = jobs

    # ── Internal ────────────────────────────────────────────────

    async def _tick(self) -> None:
        now = self._now()
        for job in list(self._jobs.values()):
            if not job.enabled or job.id in self._in_flight:
                continue
            actual_trigger = compute_actual_trigger(job.fire_at, job.tier, self.tracker)
            if actual_trigger <= now:
                label = job.name or job.id[:8]
                logger.info(
                    f"[scheduler] 触发任务 {label!r}  tier={job.tier}  channel={job.channel}:{job.chat_id}"
                )
                self._in_flight.add(job.id)
                task = asyncio.create_task(
                    self._execute_and_reschedule(job),
                    name=f"scheduler:{job.id}",
                )
                self._active_tasks[job.id] = task
                task.add_done_callback(
                    lambda done, job_id=job.id: self._on_job_task_done(job_id, done)
                )

    async def _execute_and_reschedule(self, job: ScheduledJob) -> None:
        cancelled = False
        try:
            await self._execute(job)
            job.run_count += 1
        except asyncio.CancelledError:
            cancelled = True
            logger.info("Job %s cancelled during shutdown", job.id[:8])
            raise
        except Exception as e:
            logger.error(f"Job {job.id[:8]} execution failed: {e}", exc_info=True)
        finally:
            self._in_flight.discard(job.id)
            if cancelled:
                return
            now = self._now()
            if job.trigger == "every":
                # SOFT recurring jobs may execute before nominal fire_at.
                # Reschedule strictly after the later of "now" and the nominal
                # boundary, otherwise cron jobs can re-fire the same occurrence
                # repeatedly until wall clock passes fire_at.
                reschedule_after = max(now, job.fire_at) + timedelta(microseconds=1)
                job.fire_at = self._advance_every(job, reschedule_after)
                self._jobs[job.id] = job
            else:
                self._jobs.pop(job.id, None)
            self.store.save(self._jobs)

    def _on_job_task_done(self, job_id: str, task: asyncio.Task[None]) -> None:
        if self._active_tasks.get(job_id) is task:
            self._active_tasks.pop(job_id, None)

    async def _execute(self, job: ScheduledJob) -> None:
        label = job.name or job.id[:8]
        if job.tier == "instant":
            result = await self._run_role_scoped(
                job,
                lambda: self.push_tool.execute(
                    channel=job.channel,
                    chat_id=job.chat_id,
                    message=job.message,
                    **({"role_id": job.role_id} if job.role_id else {}),
                ),
            )
            logger.info(f"[scheduler] instant 推送完成 {label!r}: {result}")
        else:
            loop = self._get_agent_loop()
            t0 = time.monotonic()
            content = await loop.process_direct(
                content=job.prompt,
                channel=job.channel,
                chat_id=job.chat_id,
                session_key=f"scheduler:{job.id}",
                omit_user_turn=True,
                skip_post_memory=True,
                skip_memory_retrieval=True,
                disabled_tools=[
                    "message_push",
                    "recall_memory",
                    "memorize",
                    "forget_memory",
                ],
                metadata=self._job_role_metadata(job),
            )
            elapsed = time.monotonic() - t0
            self.tracker.record(elapsed)
            logger.info(
                f"[scheduler] soft AI 完成 {label!r}  耗时={elapsed:.1f}s  P90={self.tracker.lead:.1f}s"
            )
            if content:
                result = await self._run_role_scoped(
                    job,
                    lambda: self.push_tool.execute(
                        channel=job.channel,
                        chat_id=job.chat_id,
                        message=content,
                        **({"role_id": job.role_id} if job.role_id else {}),
                    ),
                )
                logger.info(f"[scheduler] soft 推送完成 {label!r}: {result}")
            else:
                logger.warning(f"[scheduler] soft AI 返回空内容 {label!r}，跳过推送")

    def _get_agent_loop(self) -> Any:
        loop = (
            self._agent_loop_provider()
            if self._agent_loop_provider
            else self.agent_loop
        )
        if loop is None:
            raise RuntimeError("scheduler soft job requires agent_loop")
        return loop

    def _job_role_metadata(self, job: ScheduledJob) -> dict[str, str]:
        if not job.role_id:
            return {}
        return {
            "role_id": job.role_id,
            "role_config_version": job.role_config_version,
            "thread_id": job.thread_id or f"thread:{job.role_id}:scheduler:{job.id}",
            "delivery_key": job.delivery_key or job.id,
            "transport_channel": job.channel,
            "transport_chat_id": job.chat_id,
            "role_source": "scheduler",
            "role_work_kind": "scheduled_job",
            "request_id": job.id,
            "role_context_created_at": job.created_at.isoformat(),
        }

    async def _run_role_scoped(self, job: ScheduledJob, operation):
        if not job.role_id:
            return await operation()
        loop = self._get_agent_loop()
        return await loop.run_role_operation(
            self._job_role_metadata(job),
            operation,
        )

    def _advance_every(self, job: ScheduledJob, after: datetime) -> datetime:
        """将 every job 的 fire_at 推进到 after 之后的下一个触发时间。"""
        if job.cron_expr:
            return next_cron_fire(job.cron_expr, job.timezone, after)
        interval = timedelta(seconds=job.interval_seconds or 3600)
        next_fire = job.fire_at + interval
        while next_fire <= after:
            next_fire += interval
        return next_fire
