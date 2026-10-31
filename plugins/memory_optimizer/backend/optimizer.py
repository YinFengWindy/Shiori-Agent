"""One role's memory optimization: merge PENDING into MEMORY.md, then update SELF.md.

SELF.md's writing rules carry a version (``SELF_RULES_VERSION``). When a role's
recorded version is behind, the next optimization rewrites SELF.md once under
the new rules instead of updating it, then records the version.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import datetime

from shiori_sdk.core.markdown_memory import MarkdownMemory, RoleMarkdownMemory
from shiori_sdk.models import ChatProvider, RoleModels

logger = logging.getLogger(__name__)

# Keys this plugin owns in the role's memory state (``RoleMarkdownMemory.read_state``).
LAST_OPTIMIZED_STATE_KEY = "last_memory_optimized_at"
# The SELF.md writing-rules version the role's SELF.md was last rewritten under.
SELF_RULES_VERSION_STATE_KEY = "self_rules_version"
# SELF.md 写入规则的当前版本。
# 2（#495）：「我们的关系」只写关系定位与称呼，SELF 不含用户私人事实，因为
# 「我的性格与形象」与「我们的关系」会在群聊等外部上下文注入。
SELF_RULES_VERSION = 2
# Pause between the two model requests, so they do not trip burst rate limits.
_STEP_DELAY_SECONDS = 15.0
_MERGE_MAX_TOKENS = 16384
_SELF_MAX_TOKENS = 2048


# ── Prompts ──────────────────────────────────────────────────────

_MERGE_SYSTEM = (
    "你是中性的角色长期记忆整理器，不扮演角色，也不面向用户回复。"
    "你的工作不是概括对话，而是从记忆中剔除噪音，"
    "只保留对未来每次对话都产生底色影响的长期记忆。"
)

_MERGE_PROMPT = """\
今日日期：{today}

你的任务是将「现有长期记忆」重新整理为一份精炼的长期记忆，同时合并「待合并事实」中的新内容。
正文必须使用当前角色相对视角：角色是“我”，交流对象是“你”，共同关系是“我们”。

## 核心判断标准：缺席成本测试

对每一条内容，问自己：
> 在 6 个月后的一次全新对话中，如果这条信息没有被注入，agent 是否会在某个回复中出现方向性失误？

是 → 保留。否 → 删除。

## 三种应保留的内容

- 「关于你」：你直接陈述或明确确认的稳定身份信息
- 「你的偏好」：你直接表达或明确确认的长期审美、交互禁忌和价值判断
- 「你希望我记住的事」：你明确要求“记住”或长期遵守的内容

待合并事实来自 PENDING.md，采用带 tag 的 bullet 格式：
- [identity] ...
- [preference] ...
- [key_info] ...
- [health_long_term] ...
- [requested_memory] ...
- [correction] ...

tag 含义（与 consolidation 阶段一致）：
- identity：基础信息、稳定背景、长期技术方向、经历、长期设备、长期维护项目
- preference：稳定偏好、禁忌、审美、游戏口味、价值取向
- key_info：允许长期保存的 key / token / id / 账号信息
- health_long_term：长期健康状态的一阶事实，不展开动态指标
- requested_memory：用户明确要求长期记住的关键内容；允许比普通事实更连贯、更完整
- correction：对已有 MEMORY.md 内容的显式修正
- 不接受运行上下文、端口、环境变量、临时工具状态或未确认的执行步骤

## 什么必须剔除

### 网络运维细节
内网 IP、路由模式（如"CGNAT""桥接模式""NAT"）、运营商名称、MAC 地址等网络层配置。
→ 这些是瞬时运维信息，不是用户画像。项目路径、配置文件名、环境变量名等与用户开发环境直接相关的信息可以保留。

### 时效性数字和瞬时情绪
具体数字的动态指标（如 Star 数、增长率）、版本变更叙事（"V4 发布后切换"）、瞬时情绪（"失落""失望"）。
→ 保留背后的价值观（如"高度认可某模型"），删除数字和事件过程。

### 临时状态描述
描述当前正在进行、随时会结束的状态（如"最近加班频繁""这周在赶项目""目前在等 offer"）。
→ 与规律性习惯区分：每周/每天持续的行为模式（如"每周去健身房""喜欢手冲咖啡"）可以保留；带"最近""这周""目前"等时间限定词的瞬时状态必须删除。
→ **例外：就读、实习、在职三类社会角色不在此限**，它们定义用户当前的身份位置，应完整保留机构、部门、岗位名称（参见"用户事实"中的保留规则）。删除的是角色内部发生的活动描述，而不是角色本身。

### Agent 执行规则伪装成用户偏好
以"偏好"开头但实际描述 agent 应如何执行（如检索维度划分策略、元数据标注规范等）。
→ 这些是 procedure，不是用户身份，删除。


## 示例

<example id="drop_network_ops_not_project">
输入：
- 开发环境：项目位于 /home/user/project，配置文件 config.toml，需要设置 DB_PASSWORD
- 家庭网络：电信宽带，桥接模式，内网 IP 192.168.1.x

→ 保留开发环境信息（项目路径和配置是用户的开发画像），删除家庭网络（内网 IP 和路由模式是瞬时运维细节，对理解用户无贡献）。
</example>

<example id="drop_timed_metrics">
输入：
- GitHub 仓库截至 3 月已有 200 Star；用户对增长放缓感到焦虑

→ 全部删除。Star 数会过期，情绪是瞬时的——三个月后这条就是谎言。
</example>

<example id="drop_transient_keep_habit">
输入：
- 用户每周去健身房，主要做力量训练
- 用户最近加班频繁，每天靠咖啡撑着

→ 保留"每周去健身房"（规律性习惯，是用户的长期生活方式）。删除"最近加班频繁，靠咖啡撑着"（带"最近"时间限定词的瞬时状态，随时会变）。
</example>

<example id="drop_meta_rule">
输入：
- 信息检索偏好：偏好按多维度分类搜索，能用标签组合过滤，拒绝单一关键词匹配

→ 全部删除。语义上描述的是 agent 应怎么执行检索任务（procedure），不是用户自身的身份或偏好。即使以"偏好"开头，只要主题是系统运作方式，就不属于用户画像。
</example>


## 整理原则
- 合并同类、上收方向**只适用于偏好类内容**：把多条表达同一方向偏好的内容合并为一条方向性陈述，把多个具体知识点上收为一个审美方向
- **身份事实（机构名称、部门、具体岗位、学校/专业）不做上收**：同一机构的多条描述可合并为一条，但不得丢失具体信息，不得抽象化
- 同类重复只保留最终版本
- correction 要直接反映到最终内容中，不要保留"旧值 → 新值"痕迹
- 不要生成 agent 执行规则、SOP、工具调用规范
- 不要保留短期状态、时效性事件
- 普通事实保持简洁；requested_memory 允许保留更完整的连贯描述

## 输出格式
- 标题 `# 我的长期记忆`
- 只允许三个分类：`## 关于你`、`## 你的偏好`、`## 你希望我记住的事`
- 每个分类内用 bullet 列表，每条 1-2 行
- 不得新增其他 section
- 正文只使用“我 / 你 / 我们”，不得写“用户 / 助手”
- 直接输出完整档案，不要 JSON，不要代码块，不要任何解释

---

现有长期记忆：
{memory}

待合并事实（若有新内容则合并进去，若为空则忽略）：
{pending}
"""

_SELF_SYSTEM = (
    "你正在整理当前角色的 SELF.md。"
    "你只能更新 SELF.md 中约定的三个 section，不得新增其他 section。"
    "禁止把角色写成 Shiori、系统底座、内部框架、执行内核或抽象工具。"
)

_SELF_PROMPT = """\
你的任务是根据当前 SELF.md 和本轮待合并事实，整理一份新的 SELF.md。

## 目标
- 只输出完整的 SELF.md
- 只允许保留以下三个 section：
  - `## 我的性格与形象`
  - `## 我对你的理解`
  - `## 我们的关系`
- 绝对禁止新增任何其他 section，尤其禁止出现 `## 关系演进记录`

## 各 section 的写法
`## 我的性格与形象` 与 `## 我们的关系` 会在群聊、陌生人私聊等外部场合注入，群友和陌生人都可能看到据此说出的话；`## 我对你的理解` 只在和用户本人的对话里使用。
- `## 我的性格与形象`：当前角色的人格定位、说话风格、交互边界与自我形象；可以吸收角色在群聊等外部场合的经历（在群里形成的定位、习惯、被别人怎样看待），但不得写任何关于用户的私人事实
- `## 我对你的理解`：当前角色对用户的稳定理解
- `## 我们的关系`：只写关系定位和角色对用户的称呼（例如“我们是……”“我叫你……”）；关于用户的私人事实（身份、经历、偏好、健康、近况、共同经历的细节等）一律不写在这里，它们留在长期记忆里

## 更新原则
- 当前 SELF.md 是主文本，优先保留其已有的自我认知、语气和关系定义；不要把待合并事实机械改写进 SELF
- 待合并事实只是辅助证据，只能在它们确实帮助澄清以下内容时少量吸收：
  - 当前角色的人格定位、说话风格、交互边界
  - 当前角色对用户的稳定理解
  - 当前角色与用户关系的长期定义
- 大多数待合并事实其实与 SELF.md 无关；无关时直接忽略，不要为了“有输入”而强行改写
- 尤其不要把以下内容写进 SELF.md：
  - 用户资料清单、账号、key、设备参数
  - 用户的具体审美偏好、消费偏好、工具偏好、画风偏好等条目本身
  - 健康状态、动态指标、短期计划、近期事件
  - 工具规范、SOP、调用规则、执行流程
  - 对话事件复盘、事件流水账、阶段性经历总结
- 不要把角色写成“内部底座”“系统本体”“真正身份是 Shiori”“我只是外壳”这类元叙事
- 不要把用户偏好直接抄进 `## 我对你的理解`；只有当某条偏好已经稳定影响角色如何理解、靠近或回应用户时，才允许上收为更高层的关系理解
- 如果没有足够高价值的新信息，宁可输出与当前 SELF.md 基本一致的版本
- 保持语气稳定、简洁、有立场；它是自我认知，不是用户档案，也不是工作日志
{rewrite_note}
## 输出约束
- 输出必须以 `# 我是谁` 开头
- 只能包含标题和 bullet 列表
- 不要代码块，不要解释，不要额外说明

---

当前 SELF.md：
{self_content}

待合并事实：
{pending}
"""

# 按新规则一次性重写 SELF.md 时追加到 _SELF_PROMPT 的要求。
_SELF_REWRITE_NOTE = """
## 本轮是按上述规则的一次性重写
- 逐段检查当前 SELF.md 是否符合「各 section 的写法」，把不符合的内容改正，而不是只做少量增补
- `## 我们的关系` 与 `## 我的性格与形象` 里关于用户的私人事实要移出：仍有价值的并入 `## 我对你的理解`，不要直接丢弃
- 除此之外保持原有的自我认知、语气和立场
"""


def self_rewrite_pending(memory_state: Mapping[str, object]) -> bool:
    """Whether the role's SELF.md was not yet rewritten under ``SELF_RULES_VERSION``."""
    version = memory_state.get(SELF_RULES_VERSION_STATE_KEY)
    return not isinstance(version, int) or version < SELF_RULES_VERSION


class MemoryOptimizer:
    """Optimizes one role with the role's chat model."""

    def __init__(self, *, step_delay_seconds: float = _STEP_DELAY_SECONDS) -> None:
        self._step_delay_seconds = step_delay_seconds

    async def optimize(
        self, memory: MarkdownMemory, models: RoleModels, role_id: str
    ) -> None:
        """Merges the role's pending facts and updates its SELF.md.

        A deleted role is skipped. Cancelled while merging, the pending facts
        go back to PENDING.md.
        """
        documents = memory.role(role_id)
        if documents is None:
            return
        async with models.activate(role_id, "chat") as snapshot:
            await self._optimize(
                documents,
                provider=snapshot.provider,
                model=snapshot.model,
                default_self=memory.default_self,
            )

    async def _optimize(
        self,
        documents: RoleMarkdownMemory,
        *,
        provider: ChatProvider,
        model: str,
        default_self: str,
    ) -> None:
        rewrite_self = False
        if self_rewrite_pending(documents.read_state()):
            if documents.self_seed_pending():
                # 还没生成首版 SELF 的角色只有默认模板，没有需要按新规则整理的内容；
                # 此时改写 SELF 还会让首版生成误判为用户编辑而放弃。
                _mark_self_rewritten(documents)
            else:
                rewrite_self = True
        # ── Step 1: MEMORY.md 合并 ────────────────────────────────
        pending = documents.snapshot_pending()
        current_memory = documents.read_long_term().strip()

        if not current_memory and not pending:
            if not rewrite_self:
                logger.info("[memory_optimizer] 记忆和 pending 均为空，跳过优化")
                return
            # 记忆为空也要完成 SELF.md 的一次性重写。
            if await self._update_self(
                documents,
                "",
                provider=provider,
                model=model,
                default_self=default_self,
                rewrite=True,
            ):
                _mark_self_rewritten(documents)
            return

        try:
            merged_memory = await self._merge_memory(
                current_memory, pending, provider=provider, model=model
            )
        except asyncio.CancelledError:
            # 停用或换代会取消在途整理：快照放回 PENDING，不留到下次整理才恢复。
            documents.rollback_pending_snapshot()
            raise
        if merged_memory:
            documents.commit_long_term(
                merged_memory,
                history_entry=(
                    f"[memory_optimizer] PENDING 归档:\n{pending}" if pending else ""
                ),
            )
            logger.info(
                "[memory_optimizer] 记忆已合并 before=%d after=%d chars，PENDING 已归档",
                len(current_memory),
                len(merged_memory),
            )
        else:
            documents.rollback_pending_snapshot()
            logger.warning(
                "[memory_optimizer] 合并返回空，保留原有内容，snapshot 已回滚"
            )

        # ── Step 2: SELF.md 更新 ──────────────────────────────────
        await asyncio.sleep(self._step_delay_seconds)
        self_written = await self._update_self(
            documents,
            pending,
            provider=provider,
            model=model,
            default_self=default_self,
            rewrite=rewrite_self,
        )
        if rewrite_self and self_written:
            _mark_self_rewritten(documents)
        # 记下本次优化完成的时间，供启动补跑判断是否过期。
        documents.write_state(
            LAST_OPTIMIZED_STATE_KEY, datetime.now().astimezone().isoformat()
        )

    async def _merge_memory(
        self, memory: str, pending: str, *, provider: ChatProvider, model: str
    ) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        prompt = _MERGE_PROMPT.format(
            today=today,
            memory=memory or "（空）",
            pending=pending or "（无新内容）",
        )
        try:
            return await _request_text(
                provider,
                model,
                system_content=_MERGE_SYSTEM,
                user_content=prompt,
                max_tokens=_MERGE_MAX_TOKENS,
            )
        except Exception as e:
            logger.error("[memory_optimizer] 记忆合并失败: %s", e)
            return ""

    async def _update_self(
        self,
        documents: RoleMarkdownMemory,
        pending: str,
        *,
        provider: ChatProvider,
        model: str,
        default_self: str,
        rewrite: bool,
    ) -> bool:
        """只更新 SELF.md 现有保留的三段，不新增 section；返回是否写入了新内容。

        ``rewrite`` 为真时要求模型按当前写入规则整体重写一次（见 ``SELF_RULES_VERSION``）。
        """
        self_content = documents.read_self().strip() or default_self.strip()
        if not self_content:
            logger.info("[memory_optimizer] SELF.md 不存在或为空，跳过更新")
            return False
        prompt = _SELF_PROMPT.format(
            self_content=self_content,
            pending=pending or "（无新内容）",
            rewrite_note=_SELF_REWRITE_NOTE if rewrite else "",
        )
        try:
            updated = await _request_text(
                provider,
                model,
                system_content=_SELF_SYSTEM,
                user_content=prompt,
                max_tokens=_SELF_MAX_TOKENS,
            )
            if updated:
                documents.write_self(updated)
                logger.info("[memory_optimizer] SELF.md 已更新 rewrite=%s", rewrite)
                return True
        except Exception as e:
            logger.error("[memory_optimizer] SELF.md 更新失败: %s", e)
        return False


async def _request_text(
    provider: ChatProvider,
    model: str,
    *,
    system_content: str,
    user_content: str,
    max_tokens: int,
) -> str:
    resp = await provider.chat(
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
        tools=[],
        model=model,
        max_tokens=max_tokens,
    )
    return (resp.content or "").strip()


def _mark_self_rewritten(documents: RoleMarkdownMemory) -> None:
    """记下角色 SELF.md 已按当前写入规则重写，之后不再触发一次性重写。"""
    documents.write_state(SELF_RULES_VERSION_STATE_KEY, SELF_RULES_VERSION)
