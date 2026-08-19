# Role Interview 角色创建方案调研

调研日期：2026-08-17

## 结论

截至本次调研，没有找到一个公开产品或开源项目完整实现以下组合：

> 对话式访谈 + 网络检索作品资料 + 从检索出的叙事节点让用户选择还原状态 + 用户补充信息 + 结构化人格/行为编译 + 可长期运行的内部状态。

但已经有一个非常接近的开源项目 **World-Forge**，以及若干覆盖关键子问题的项目和论文。现有生态更像拼图：

- World-Forge：最接近“访谈式编排、结构化产物、多轮验证和角色卡导出”。
- Character Skill Producer：最接近“输入作品角色名后检索、交叉验证、行为蒸馏和质量检查”。
- Yorishiro：最接近“从影视/小说等原始作品抽取角色灵魂、知识边界和长期记忆”。
- PersonaForge：最接近“四层人格结构 + 动态状态 + 漂移验证”。
- CharacterGPT：最接近“按原作叙事章节重建、随剧情阶段变化的人格”。
- RoleRAG：解决运行时角色知识检索和认知边界，不负责创建访谈。
- SillyTavern / Character Card V2 / Character.AI：提供角色卡字段和运行时生态，但主要是手工创作与打包。

因此，Shiori 的差异化不应宣称“发明了角色卡生成”，而应明确为：**把作品检索、叙事节点选择和原创/作品角色访谈统一到一个自由对话创建流程，并将结果编译成可长期运行的角色状态。**

### Character Skill Producer：作品角色检索和行为蒸馏

来源：[GitHub repository](https://github.com/qian-gugugaga/Character_Skill_Producer)

该仓库的 README 将流程定义为：输入角色名和作品名，完成资料检索、交叉验证、行为蒸馏和质量检查，输出带来源边界和更新时间信息的 `SKILL.md`。它明确强调从“性格标签”转向“情境中的行为逻辑”，与 Shiori 需要的触发条件、反应机制和行为规则非常接近。

边界：它的入口是命令式角色 Skill 生成，不是面向用户的连续访谈；没有发现让用户从检索出的叙事节点中选择还原状态，也没有把原创角色和作品角色统一进一个对话式创建流程。

判断：**它是作品角色路线的重要直接参考，但不是本方案的端到端等价实现。**

## 最接近的实现

### World-Forge：对话访谈和多阶段角色卡流水线

来源：

- [README](https://github.com/AndreiNicu/World-Forge/blob/main/README.md)
- [Interviewer agent](https://github.com/AndreiNicu/World-Forge/blob/main/agent_roles/00_The_Interviewer.md)
- [World Seed template](https://github.com/AndreiNicu/World-Forge/blob/main/templates/World_Seed_Template.md)

README 明确描述了一个由多个专门 Agent 组成的流水线。Phase 0 的 Interviewer 会交互式询问 World Seed、对薄弱或矛盾的设定提出反问，并记录风格契约和测试场景；后续 Refiner、Architect、Editor、Voice Auditor、Arc Transition Auditor 和 Compiler 负责结构化、生成、审计和导出。

它的输出包括 SillyTavern V3 角色卡、分层 Lorebook、Chat Completion Preset 和审计报告。三层 lorebook 将永久世界事实、角色资料和当前剧情状态分离，用于长篇 RP 的连续性。

边界：

- Interviewer 面向用户已有的世界设定，不是“输入作品名后自动检索 Canon”。
- 没有发现让用户从检索出的原作叙事节点中选择还原状态的功能。
- 它是由 IDE Agent 执行的 Markdown 规范流水线，不是独立的桌面角色创建产品。

判断：**访谈编排和验证方式是强参考，但 Canon 检索/时间线快照仍是 Shiori 可补上的空白。**

### Yorishiro：作品素材到角色灵魂文档

来源：

- [README](https://github.com/swordfeng/yorishiro/blob/vibe/README.md)
- [Requirements](https://github.com/swordfeng/yorishiro/blob/vibe/docs/REQUIREMENTS.md)
- [Design](https://github.com/swordfeng/yorishiro/blob/vibe/docs/DESIGN.md)

Yorishiro 的目标是从电影、小说、设定集和访谈中抽取角色信息，生成 `SOUL.md`，其中包含核心身份、价值观/动机/恐惧/认知模式、语言风格、关系、行为模式、负面约束、角色弧线以及角色知道/不知道的知识边界。其架构包含素材抽取、索引、跨来源对齐、SOUL 合成和一致性检查，并使用静态 SOUL.md 加运行时 RAG 的双层记忆。

边界：

- 目前是素材驱动的批处理/流水线，不是面向用户的自然语言访谈。
- README 没有显示网络检索和用户从时间线节点选择的交互。
- 项目状态仍是 Draft/WIP，不能把设计目标等同于成熟产品能力。

判断：**它验证了“作品素材 → 结构化角色灵魂 → 运行时知识边界/长期记忆”这条方向，适合作为 Shiori 的 Canon ingestion 和角色 profile 参考。**

### PersonaForge：心理学结构和动态状态

来源：

- [Official repository](https://github.com/fQwQf/PersonaForge)
- [Schema documentation](https://github.com/fQwQf/PersonaForge/blob/main/schemas/README.md)
- [ACL 2026 paper metadata](https://github.com/fQwQf/PersonaForge#citation)

PersonaForge 将人格分成 Core Traits、Speaking Style 和 Dynamic State 三层。Core Traits 包括 Big Five 和 Vaillant 防御机制；Speaking Style 建模句法、词汇、语气和情绪表达；Dynamic State 跟踪 mood、energy、relationships 等变化。仓库还描述了从 raw text/wiki 自动抽取人格 JSON、生成初始动态状态、使用 JSON Schema 验证，以及 selective Think-then-Speak 内部过程。README 报告了 50 轮漂移评估结果。

边界：

- 不负责对用户进行创建访谈。
- 不负责联网检索、Canon 时间线整理或让用户选择叙事节点。
- 其输入通常需要用户自己准备的文本/wiki 素材。

判断：**最适合借鉴 Shiori 的四层结构落盘、内部动态状态和验证指标；不应直接照搬 Big Five 数值到最终 System Prompt。**

### CharacterGPT：随原作叙事阶段重建角色

来源：

- [arXiv 论文](https://arxiv.org/abs/2405.19778)
- [Official repository](https://github.com/Jeiyoon/charactergpt)

CharacterGPT 的论文方案以逐章小说摘要为输入，逐章抽取角色特质并动态重建 persona，特别关注 backstory 和 interpersonal relations 的保留，并进行 Big Five 与创意质量评估。它接近“按故事阶段生成角色快照”，但不是让用户从检索出的阶段中选择，也不是访谈式产品。

判断：**可参考其“叙事阶段 → persona 快照/演化”的数据模型，用来实现 CanonSnapshot。**

### RoleRAG：运行时知识边界

来源：[arXiv 论文](https://arxiv.org/abs/2505.18541)

RoleRAG 使用实体消歧、边界感知检索器和结构化知识图谱增强角色扮演，重点处理角色背景召回、角色认知边界和幻觉问题。它是运行时增强方案，不是创建流程。

判断：**可用于 Shiori 在 RP 过程中限制角色只能使用还原节点之前的知识，但不能替代创建期访谈。**

## 角色卡和手工创作生态

### SillyTavern / Character Card V2

来源：

- [SillyTavern character design 文档](https://docs.sillytavern.app/usage/characters/characterdesign/)
- [Character Card V2 specification](https://github.com/malfoyslastname/character-card-spec-v2/blob/main/spec_v2.md)

SillyTavern 将 description、personality、scenario、first message、example dialogue、system prompt、post-history instructions 和 lorebook 等字段组合到运行时 Prompt。Character Card V2 进一步把这些字段标准化，并支持 alternate greetings、character book 和 extensions。

边界：这是角色卡格式和运行时生态，不是自动访谈或 Canon 创建器。World-Forge 选择它作为导出目标，说明它是事实上的适配层之一，但不能视为已解决角色建模问题。

### Character.AI

来源：

- [Definition](https://book.character.ai/character-guide/character-attributes/definition)
- [Advanced Creation](https://book.character.ai/character-guide/advanced-creation)
- [Greeting](https://book.character.ai/character-guide/character-attributes/greeting)

Character.AI 提供自由文本 Definition（官方文档写明可包含示例对话）和 Greeting；官方强调首条消息会影响角色的风格和场景。Advanced Creation 仍然是灵活的手工定义，并非结构化 specification。官方文档还明确说明外链不会被系统自动加载，因此不能当作网络检索式角色创建。

判断：**验证了“背景/示例对话/首条消息”对 RP 风格的重要性，但不是本方案的竞品级端到端实现。**

## 研究工作作为方法参考

### RPLA survey

来源：[Role-Playing Language Agents survey](https://arxiv.org/abs/2404.18231)

该综述将 persona 相关信息区分为 demographic、character 和 individualized 等类别，并从数据来源、Agent 构建和评测方式总结 Role-Playing Language Agents。它支持把“作品事实”“角色人格”“用户关系/个性化设置”分成不同来源，再统一进入构建和评估流水线。

## 能力对比

| 项目 | 对话访谈 | 作品/文本抽取 | 网络 Canon 检索 | 叙事阶段/时间快照 | 行为/人格结构 | 长期动态状态 | 角色卡/Prompt 导出 |
|---|---:|---:|---:|---:|---:|---:|---:|
| World-Forge | 有 | 用户设定 | 无 | 有限（arc/world state） | 有 | 有（lorebook/state） | 有 |
| Yorishiro | 无 | 有 | 未证实 | 有限（character arc） | 有 | 有（SOUL + RAG） | SOUL.md |
| PersonaForge | 无 | 有 | 无 | 无 | 强 | 强 | Persona schema |
| CharacterGPT | 无 | 有 | 无 | 强 | 有 | 随章节更新 | 研究输出 |
| RoleRAG | 无 | 运行时 | 无 | 运行时边界 | 运行时检索 | 非创建职责 | 无 |
| SillyTavern/CC V2 | 无 | 手工 | 无 | 手工 scenario | 字段承载 | Lorebook 承载 | 强 |
| Character.AI | 无 | 用户手工 | 无（外链不加载） | 无 | 手工 Definition | 平台内部未公开 | 平台内部 |

## 对 Shiori 的直接启示

1. **最接近的产品交互应参考 World-Forge 的 Interviewer，但改成独立的运行时对话。** 每轮访谈更新结构化草稿，并只追问当前最影响一致性的一个问题。
2. **作品角色必须先做 CanonSnapshot。** 先检索并按事件/关系/心理状态生成少量可读节点，再让用户选择；用户不需要知道第几集或正式时间线名称。
3. **来源和推断必须分层。** 至少区分 `canon_fact`、`source_claim`、`user_choice`、`inference`、`generated_detail`，并保留来源和日期。
4. **`background` 只是事实/叙事载体。** 需要额外编译表达规则、触发-反应行为规则、硬限制和 `memory_init_state`，否则无法保证长期 RP 一致性。
5. **运行时要保留知识边界和动态状态。** CharacterGPT 的阶段快照、PersonaForge 的 Dynamic State、RoleRAG 的边界感知检索可以组合成 Shiori 的长期运行模型。
6. **MVP 不必复制完整世界构建器。** 先实现“访谈 → 草稿 → 用户确认 → `background`/`system_prompt`/`memory_init_state`”和一个作品角色 CanonSnapshot 路由；多源视频抽取、复杂 Lorebook 和自动审计可后置。

## 未确认项目

本次没有把 “Fic2Bot” 作为已确认的一手项目引用：按精确标题查询未能定位到可靠的官方论文或仓库，后续若拿到具体链接再补充。避免将二手文章中的项目名当作事实依据。
