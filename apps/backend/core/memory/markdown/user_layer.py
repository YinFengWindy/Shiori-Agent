"""用户层整理（#496）：用户本人段的提取提示词与产物落盘。

角色会话整理与旁听整理（#541）共用：用户本人的发言（含在群里说的话）提炼成
HISTORY 事件条目与 PENDING 候选，写入角色记忆目录，再交给记忆引擎。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from shiori_sdk.memory.events import ConsolidationCommitted

from .formatting import append_entries_to_journal

if TYPE_CHECKING:
    from bus.event_bus import EventBus
    from .runtime import MarkdownMemoryStore

logger = logging.getLogger("memory.markdown")


def build_user_layer_prompt(
    current_memory: str, recent_history_block: str, conversation: str
) -> str:
    """用户层提取提示词：在现有长期记忆与最近事件的参照下提取 ``conversation``。"""
    return f"""从对话中精确提取结构化信息，返回 JSON。

## 字段说明

### 1. "history_entries" → HISTORY.md（数组，每条对应一个独立主题）
按主题拆分，每个独立话题写一条对象，格式为 {{"summary":"...", "emotional_weight":0}}。
summary 仍然要求 1-2 句，以 [YYYY-MM-DD HH:MM] 开头，保留足够细节便于未来 grep 检索。
不同主题必须拆成独立条目，不得合并。若整段对话只有一个主题，返回只含一条的数组。

history_entries.emotional_weight 规则：
- 范围 0-10
- 普通技术讨论、普通事务记录、无明显情绪色彩 → 0
- 用户明确表达强烈喜欢/厌恶、明显受挫、关系冲突、情绪波动时按强度给 3-9
- 不确定时保守输出 0

**history_entries 提取规则（严格遵守）**：
1. 只提取 USER 明确表达的行动、经历、计划和状态；ASSISTANT 的建议、推荐、解释一律不写入，即使其中提到了地名、店名或活动。
2. 每条必须使用角色相对视角：当前角色是“我”，USER 是“你”，共同关系是“我们”；绝对不能包含 "USER:" 或 "ASSISTANT:" 等原始对话标记，不得复制粘贴原始对话文本。
3. 商家名称、地点、人名、数量、价格、型号等具体细节必须保留，不得用"某商店""某地方"概括。
4. 先判断当前 USER 内容的材料类型：是“用户此刻直接自述”，还是“用户正在展示一段外部聊天记录、截图 OCR、转贴 transcript 给助手看”。
5. 若 USER 内容属于外部聊天记录 / transcript，必须先做层级理解：
   - 外层：当前 USER 正在把一段材料发给助手看。
   - 内层：材料中可能有多个 speaker；这些 speaker 不自动等于当前 USER。
   - 只有当材料中某个 speaker 与当前 USER 的映射在当前会话里被明确确认时，才允许把该 speaker 的事实写入摘要。
6. 对 transcript 场景，默认认为 speaker 映射不明确；除非当前会话中有非常明确的显式说明，否则不要尝试判断材料里的某个昵称/说话人就是用户或对方。
7. 若 speaker 映射不明确，history_entries 只允许写 1 条高层 event，例如“你向我展示了一段与某人的聊天记录，内容涉及求职、学校、兴趣等话题”。
8. 对 transcript 场景，禁止输出任何未确认关系的句子，例如：
   - “用户向对方透露……”
   - “对方是……”
   - “双方确认……”
   - 把聊天记录里的具体事实直接写成用户个人经历
9. transcript 场景下，默认最多输出 1 条高层 history_entry；不要下钻成人物小传，不要替材料里的 speaker 自动补全身份关系，不要写任何昵称归属、学校归属、出生年份归属、爱好归属。

**transcript 场景示例（严格遵守）**：
- 错误：用户贴出一段聊天记录，speaker 归属未确认，却写成“用户向对方透露自己正在找暑期实习”。
- 错误：用户贴出一段聊天记录，直接写成“对方位于北京大兴区，就读于二外 MPAcc 专业”。
- 错误：用户贴出一段聊天记录，直接写成“对方昵称为‘一只快乐的小奶龙’”。
- 错误：用户贴出一段聊天记录，直接写成“用户曾为打 FGO 日服选修日语”。
- 正确：你向我展示了一段与匹配对象的聊天记录，聊天内容涉及学校背景、兴趣爱好和求职话题。

### 2. "pending_items" → PENDING.md 候选缓冲
只写用户的长期记忆候选，返回对象数组。每个对象格式：
{{"tag": "<tag>", "content": "<string>"}}

允许的 tag 只有 6 个：
- "identity"：稳定背景事实，如身份、学校/专业、长期技术方向、实习/工作经历、长期设备、长期维护项目
- "preference"：稳定偏好、禁忌、审美、游戏口味、价值取向
- "key_info"：用户明确允许保存的 key / token / id / 账号信息
- "health_long_term"：长期健康状态的一阶事实，只写长期状态，不写动态指标、基线、最近波动
- "requested_memory"：用户明确要求"长期记住"的关键内容，可比普通事实更连贯
- "correction"：对当前 MEMORY.md 现有事实的明确纠正

必须遵守：
- 只写跨对话仍有长期价值的内容
- 不写 agent 执行规则、SOP、工具调用顺序、流程规范
- 不写短期状态、近期计划、日程、课表、一次性操作
- 不写动态健康数据、实时指标、最近状态
- 不写对话过程总结
- 不写 self_insights、行为规律总结、关系演进感悟
- "requested_memory" 只能在用户明确表达"记住这个 / 写进长期记忆 / 以后要能聊到 / 希望你记住"时使用

进阶过滤（四条硬规则，任一触发即不提取）：

1. **网络运维细节不提取**
内网 IP、路由模式（如"CGNAT""桥接模式""NAT"）、运营商名称、MAC 地址等网络层配置属于瞬时运维信息，不提取。项目路径、配置文件名、环境变量名等与用户开发环境直接相关的信息可以提取。
✗ "家庭网络是联通宽带，光猫路由模式，内网 IP 192.168.1.x" → 不提取（网络层瞬时配置）
✓ "项目位于 /home/user/project，配置文件 config.toml" → 可提取（开发环境画像）

2. **临时状态不提取，规律习惯可提取**
带"最近""这周""目前""正在"等时间限定词的瞬时状态不提取。每周/每天持续的规律性行为模式可以提取为偏好或习惯标识。
✗ "用户最近加班频繁，靠咖啡撑着" → 不提取（瞬时状态，随时会变）
✓ "用户每周去健身房，主要做力量训练" → 可提取（规律性习惯，是长期生活方式）

3. **时效性数字和瞬时情绪不提取**
带有具体数值的动态指标（如 Star 数、增长率、评分）、瞬时情绪描述（如"失落""焦虑"）、正在进行中的短期状态。保留背后的价值判断，不提取数字和情绪本身。
✗ "项目刚突破 500 Star，但增速降到每天 2 个，用户为此很焦虑" → 不提取（数字过期、情绪瞬时）
✓ "用户长期维护某开源项目并重视社区增长" → 可提取（稳定身份信息）

4. **Agent 执行规则不放入 pending_items**
以"偏好"开头但语义上描述 agent 应如何执行的内容（如检索策略、元数据标注规范、输出格式要求等），属于 procedure，应由隐式提取路径写入向量库。
✗ "偏好搜索结果按来源可信度分层展示" → 不提取为 pending_item（agent 输出规范）
✗ "希望以后推荐前先查最新评测和社区反馈" → 不提取为 pending_item（agent 执行规则）

若没有合格条目，返回空数组 []。

---

## 当前长期记忆（用于查重）
{current_memory or "（空）"}

## 最近三次 consolidation event（仅用于主题延续参考）
使用原则（严格遵守）：
- 这些旧 event 只能帮助你理解“当前窗口大概在延续什么话题”，不能作为人物身份、说话人归属、关系判断或具体事实归属的直接证据。
- 若旧 event 与当前窗口原文在昵称、身份、关系、事实归属上存在冲突或不一致，必须以当前窗口原文为准。
- 不要因为旧 event 里出现了某个昵称、人设或关系描述，就在新的 history_entries 中继续沿用这些判断。
- 对 transcript / 聊天截图 / 转贴聊天场景，旧 event 绝不能用于推断“谁是当前用户、谁是对方、哪句话归谁”。
{recent_history_block or "（空）"},

## 待处理对话
标注“（在群「…」里）”的 USER 发言是 USER 本人在群聊里说的话，同样按 USER 的发言处理。
{conversation}

只返回合法 JSON，不要 markdown 代码块。"""


async def append_user_layer(
    store: "MarkdownMemoryStore",
    history_entry_payloads: list[tuple[str, int]],
    pending_items: str,
    source_ref: str,
    *,
    recent_context_text: str | None = None,
) -> None:
    """把用户层产物按 ``source_ref`` 幂等写入角色记忆目录。

    顺序是 HISTORY → PENDING → RECENT_CONTEXT → 日记，与角色会话整理一直以来的
    写入顺序一致。``recent_context_text`` 只有角色会话整理给出（整篇覆盖）；旁听
    整理（#541）传 None，不碰 RECENT_CONTEXT。
    """
    history_entries = [entry for entry, _ in history_entry_payloads]
    if history_entries:
        _ = await asyncio.to_thread(
            store.append_history_once,
            "\n".join(history_entries),
            source_ref=source_ref,
            kind="history_entry",
        )
    if pending_items:
        appended = await asyncio.to_thread(
            store.append_pending_once,
            pending_items,
            source_ref=source_ref,
            kind="pending_items",
        )
        if appended:
            logger.info(
                "Markdown memory: appended %d pending_items",
                len(pending_items.splitlines()),
            )
    if recent_context_text is not None:
        store.write_recent_context(recent_context_text)
    if history_entries:
        await asyncio.to_thread(
            append_entries_to_journal,
            store,
            history_entries,
            source_ref,
        )


async def publish_user_layer(
    event_bus: "EventBus | None",
    *,
    role_id: str,
    history_entry_payloads: list[tuple[str, int]],
    source_ref: str,
    conversation: str,
    scope_channel: str,
    scope_chat_id: str,
) -> None:
    """把已落盘的用户层产物交给记忆引擎（``ConsolidationCommitted``）。

    引擎只收用户本人段；``conversation`` 为空（窗口里没有用户本人的发言）时没有
    可交给引擎的内容，不发事件。
    """
    if not conversation or event_bus is None:
        return
    _ = await event_bus.emit(
        ConsolidationCommitted(
            history_entry_payloads=list(history_entry_payloads),
            source_ref=source_ref,
            scope_channel=scope_channel,
            scope_chat_id=scope_chat_id,
            conversation=conversation,
            role_id=role_id,
        )
    )
