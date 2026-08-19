# CharacterGPT：按叙事章节重建角色人格

调研日期：2026-08-17  
论文版本：arXiv v5，2025-02-23  
论文：[CharacterGPT: A Persona Reconstruction Framework for Role-Playing Agents](https://arxiv.org/abs/2405.19778)（Jeiyoon Park、Chanjun Park、Heuiseok Lim）  
官方仓库：[Jeiyoon/charactergpt](https://github.com/Jeiyoon/charactergpt)

## 一句话结论

CharacterGPT 不是一个训练新的语言模型，而是一个围绕 Assistants API 的**人格文档重建流水线**：先把角色的静态信息整理成初始化人格，再按小说章节摘要逐章抽取八类特质；其中内在特质会被泛化/压缩，外部叙事事实按时间顺序累积。每个章节（论文称 epoch）都保存一个阶段版本，所以可以在“故事进行到某一章”时与角色交互。它与 Shiori 所说的叙事阶段快照相似，但论文的快照是离线生成的 persona 文档，不是用户选择的 Canon 节点，也没有运行时知识边界控制。

## 论文要解决的问题

作者观察到，直接把 Wiki 或其他角色文档交给 Assistants API 会出现信息抽取不稳定：回答可能遗漏背景、关系等关键内容，导致角色不一致（论文第 1 页 Figure 1、第 1 节）。目标是把散乱文档重组为可检索、可按叙事阶段演化的结构化 persona，而不是让模型每次从碎片文档自行寻找事实。

## 方法详解

### 1. 八类角色特质

论文第 2 节定义八类字段：

1. `Personality`：勇敢、内向、机智等核心性格。
2. `Physical Description`：外貌。
3. `Motivations`：目标和欲望。
4. `Backstory`：塑造性格和动机的历史背景。
5. `Emotions`：影响回应的情绪范围。
6. `Relationships`：与其他角色的关系。
7. `Growth and Change`：叙事中的发展。
8. `Conflict`：内在或外在冲突。

作者明确要求逐项更新，不能把各次抽取合并成一段无结构摘要；这样既保留角色特质，也保留章节顺序（第 2 页）。附录 D 的实际推理 prompt 还把 `Voice and Speech Patterns` 作为可选字段，但论文承认样本中的对白太少，未能充分验证它（第 3 页、第 8 页 Limitations）。

### 2. Persona Initialization：故事开始前的基线

初始化阶段假设“叙事尚未推进”，删除与后续剧情绑定的内容，只保留五类静态字段：

```text
D_init = {D_personality, D_physical, D_motivations,
          D_backstory, D_relationships}
```

`Emotions`、`Growth and Change`、`Conflict` 被排除，因为它们依赖剧情推进，应在 CPT 阶段生成（公式 (2)，第 2.2 节）。这一步是阶段快照的基线：初始化角色不能知道后续章节发生的事。需要注意，论文没有把“角色知道什么”单独建模为权限/边界字段，而是通过不把后续章节放入该版本 persona 来间接实现。

### 3. Character Persona Training（CPT）：逐章增量重建

作者把八类特质分成两种更新策略：

- **Type A 内在属性**：`Personality`、`Physical Description`、`Motivations`。每章抽取后交给泛化函数 `h`，用于提炼角色的稳定核心属性。
- **Type B 外部/交互属性**：`Backstory`、`Emotions`、`Relationships`、`Growth and Change`、`Conflict`。每章抽取结果直接追加到 persona，积累角色经历和关系知识。

对第 `i` 个章节摘要 `D_i` 和特质 `t`，论文公式 (3) 给出：

```text
T_t^i = h(g(D_i, P_g), P_h),  if t is Type A
        g(D_i, P_g),          otherwise
```

其中 `g` 是用抽取 prompt `P_g` 调用 Assistants API，`h` 是用泛化 prompt `P_h` 调用 LLM。附录 D 的泛化 prompt 要求“minimizing information loss”，并要求新特质保持追加内容的 chronological order；若目标信息未找到或只找到部分信息，返回 `Flag: 0`，否则 `Flag: 1`（第 16 页 Figure 10）。

### 4. 阶段 persona 的组成和推理

最终输入文档由初始化、训练和语气/说话模式组成：

```text
D_r = D_init + D_train + T_v                 (公式 4)
```

`D_train` 是截至某个章节的 CPT 结果，`T_v` 是可选的 Voice/Speech Pattern。论文使用 Assistants API 读取 `D_r`，再根据 inference prompt 生成回答（第 2.4 节、附录 D）。推理 prompt 先要求模型优先考虑角色语气，再判断用户是在请求信息还是普通聊天，随后选择相关 persona 字段回答（第 16 页 Figure 10）。

论文的“每章快照”是实现层面的多个版本：Megumin 的小说被切成 16 章，因此生成 16 个 epoch 版本；用户可在不同 epoch 询问同一个问题，得到随故事推进而变化的观点和情绪（第 7 页 §3.5、附录 C Figure 5）。这不是每轮对话实时重写人格，而是离线逐章构建后，在推理时选择某个版本。

## 数据、模型和实验设置

- 角色：Megumin（16 章）、Anya Forger（30 章）、Frieren（11 章）、Hitori Gotoh（12 章）。来源是 Namuwiki 的角色资料、对白和小说章节摘要；原始数据为韩文，论文示例翻译成英文（第 2 节、Table 1）。
- 规模：训练摘要 token 数分别为 31,917、52,207、32,328、24,039；角色信息和对白规模见 Table 1（第 3 页）。
- 模型：主要是 GPT-4 Turbo `gpt-4-1106-preview` + Assistants API；兼容性/消融使用 `gpt-3.5-turbo-1106`（第 3.1 节）。
- 人格评估：Big Five Inventory，5 个维度、每维 24 题，共 120 题；把回答转换为 facet 值，与人工预测比较。报告 `# Wins`（与人类最接近的 facet 数）和绝对差总和 `Σ|d|`（第 5 页 §3.3）。
- 创作评估：提示角色“根据给定文本想象未来一集，写约 2000 字小说”；4 个角色、每种设置 4 篇，共 32 篇，由 7 名 crowd-workers 按 Grammar、Coherence、Likability、Relevance、Complexity、Creativity 六项 5 点量表评分（第 5-7 页 §3.2-3.4、Table 6）。

## 结果和可复现的数字

- Big Five：Figure 3/4 显示加入 CharacterGPT 后，四个角色的 `# Wins` 总数都提高、`Σ|d|` 总差距都下降。例如 Megumin 的总差距从 GPT-4 的 621 降到 339，Anya 从 573 降到 235，Frieren 从 558 降到 222，Hitori 从 538 降到 320（第 6 页 Figure 3/4）。
- 故事生成：GPT-4 平均分从 Grammar 4.18、Coherence 3.89、Likability 3.39、Relevance 4.03、Complexity 3.36、Creativity 3.46 变为 4.26、4.09、3.76、4.13、3.72、3.74；提升最明显的是 Likability、Complexity、Creativity（第 7 页 Table 6）。论文正文称这些提升是 human preference 提升，但没有给显著性检验或置信区间。
- 案例：初始化的 Hitori 不认识 Ikuyo Kita；训练到 epoch 12 后能将其识别为同校同学、第一位学校朋友和乐队成员。Frieren 从“对人类情感漠不关心”逐渐表现出旅途中形成的同理心（第 15 页 Figure 9）。Megumin 在 epoch 0、8、16 对“最近最困难的事”的回答分别对应不同剧情经历（第 6 页 Figure 5）。

## 对 Shiori“叙事阶段快照”的直接启示

1. **快照应是不可变版本，而不是覆盖当前人格。** 可以把 `CanonSnapshot` 设计成 `(source, chapter_or_event, persona_traits, knowledge_cutoff)`；上一阶段仍可回放。CharacterGPT 的 `D_init + D_train` 和每 epoch 文档提供了最直接的数据模型。
2. **静态人格与剧情增量分开。** `Personality/Physical/Motivations` 更接近长期核心；关系、情绪、冲突和成长属于随 `StoryBeat` 累积的阶段状态。不要把所有章节重新总结为一段会丢失时间顺序的 `background`。
3. **知识边界是隐含的，需在 Shiori 中显式化。** CharacterGPT 通过“只加载截至第 N 章的文档”避免后见之明，但没有单独的检索过滤器、事实来源级别或越界拒答策略。若结合 RoleRAG，应把 snapshot cutoff 作为检索硬条件。
4. **它不是用户交互式创建流程。** 论文输入是预先整理好的章节摘要，不包含联网检索、用户选择还原节点、用户补充设定或访谈；因此只能借鉴“章节 → persona 版本”的内部编译，不应宣称论文已经解决 Canon 选择体验。
5. **Type A 的泛化有信息损失风险。** 论文希望用 `h` 压缩内在属性，但没有报告抽取准确率、跨章节冲突处理、版本回滚或事实溯源。Shiori 若实现，应保留每章原始证据和推断/泛化结果，允许重建。
6. **与当前 Story 模型的对应关系。** 当前 Shiori 的正式历史是已提交的 `StoryBeat`，而 `StoryTurn` 是一次玩家输入触发的生成边界；CharacterGPT 的 epoch 更像“按原作章节构建的角色状态版本”，不是一次运行时 `StoryTurn`。可将 `StoryBeat` 作为阶段状态的证据来源，将 snapshot 作为只读派生物，而非替代正式历史。

## 论文明确的限制

论文第 8 页列出三类限制：

- **特质集合未经正式验证。** 文化/社会语境等字段可能重要；对白数据少，无法充分评估 Voice/Speech Pattern。
- **推理能力未充分研究。** 未来情节写作虽在 Likability、Complexity、Creativity 上超过基线，但分数没有超过 4，深层决策能力仍不足。
- **角色幻觉缺乏基准。** 虚构世界的“事实”与现实事实不同，逐部小说构造高成本评测集困难；论文没有解决角色知识错误或越界知识的系统检测。

此外，实验样本只有四个角色、7 名评价者，基线主要是同一 Assistants API 中的 GPT-3.5/GPT-4；结果说明“结构化 persona 文档”有效，但不能直接外推到现代模型或长周期在线 RP。

## 官方实现状态

截至本次调研，官方仓库 README 只有：`Official repository ... Code coming soon!`，没有训练脚本、数据文件或运行时实现。因此论文中的公式、prompt 截图和 PDF 案例是当前唯一的一手实现证据；不能把仓库链接当作已有可运行代码。

## 参考来源

1. Park, Jeiyoon; Park, Chanjun; Lim, Heuiseok. *CharacterGPT: A Persona Reconstruction Framework for Role-Playing Agents*. arXiv:2405.19778v5, 2025-02-23. [PDF](https://arxiv.org/pdf/2405.19778)；方法见 pp. 1-3，实验见 pp. 5-8，提示词/案例见 pp. 12-17。
2. [官方 GitHub 仓库](https://github.com/Jeiyoon/charactergpt)，README（访问日期：2026-08-17）。
