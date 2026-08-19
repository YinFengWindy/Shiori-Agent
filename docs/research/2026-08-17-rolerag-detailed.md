# RoleRAG：图引导的角色知识检索与动态认知边界判断

调研日期：2026-08-17
论文版本：arXiv v1，2025-05-24
论文：[RoleRAG: Enhancing LLM Role-Playing via Graph Guided Retrieval](https://arxiv.org/abs/2505.18541)（Yongjie Wang、Jonathan Leung、Zhiqi Shen）
作者关联源码：[AnonymousSub123/RoleRAG](https://github.com/AnonymousSub123/RoleRAG)（论文 LaTeX 源码曾直接写出该地址）

## 一句话结论

RoleRAG 是一个无需微调生成模型的角色专用 Graph RAG：离线从角色语料抽取实体和关系、合并别名并构建知识图谱；在线先让 LLM 推测问题可能涉及的实体，再判断每个实体是否属于角色认知范围以及属于“具体实体”还是“一般概念”，据此选择具体实体检索、角色一跳邻居检索或越界提示。实验表明它通常能提高角色知识暴露、降低知识幻觉并提高越界问题拒答率。

但论文所谓“boundary-aware”是**查询时的 LLM 动态相关性判断**，不是按章节、时间点或事实建立的硬性知识可见性规则。它适合作为 Shiori 的运行时检索路由器，不能单独替代 CharacterGPT 式叙事阶段快照或可审计的 `knowledge_cutoff`。

## 论文要解决的问题

作者把角色扮演中的知识错误归因于两类问题（论文 pp. 1-2）：

1. **实体歧义**：同一角色可能有多个名字，例如 Anakin Skywalker、Darth Vader、Lord Vader。若索引时不合并，查询会漏掉分散在不同名字下的事实。
2. **角色认知边界缺失**：生成模型拥有远超角色的参数知识，可能让古代人物详细讨论登月、让某作品角色回答另一个世界观中的事件，并把这种“模型知道、角色不应知道”的内容说出来。

Figure 1 的前置观察使用 GPT-4o-mini 扮演 7 名《哈利·波特》角色，每人回答 10 个一般问题和 10 个角色细节问题。人工评分显示，角色专属细节问题更难，低频角色尤其容易知识暴露不足或产生幻觉。这是动机实验，不是 RoleRAG 的正式主结果。

## 方法详解

### 1. 从长角色语料构建实体关系图

输入语料来自角色相关的 Wikipedia、百度百科和小说。论文将语料切成重叠 chunk，并让 LLM 对每个 chunk 抽取（§3.1）：

```text
entity = {name, type, description}
relation = {source, target, description, strength}
```

实体的名称和描述再由 embedding 模型编码，写入向量库；实体与关系同时汇入全局数据库。关系 `strength` 表示实体间关系强度。经过实体归一化后，重复实体和关系的描述由 LLM 合并摘要，最终形成：

```text
G_hat = {N_hat, R_hat}
```

其中节点可表示角色、地点、对象、事件等，边保存两实体之间的文本关系。它不是预定义 schema 的本体图，实体类型、描述和关系主要由 LLM 从文本开放抽取。

### 2. 实体归一化 / 别名消歧

论文算法 1 对每个抽取实体执行（§3.2）：

1. 用 embedding 从已建立的实体向量库取语义最相近的 top-k 候选。
2. 把候选双方的名称和局部描述交给 LLM，判断是否为同一实体。
3. 判断相同则在临时“实体等价图”中连边。
4. 对全部连通分量分别调用 LLM，选出统一 canonical name。
5. 建立原名到 canonical name 的映射，并重写实体、关系数据库。

论文声称，相比对 `|N|` 个实体做全量两两 LLM 比较，该方案把 LLM 调用量降低约 `|N| / k` 倍。这里给出的是复杂度层面的调用量比较，没有报告实体归一化准确率、precision/recall、错误合并率或真实成本曲线。

公开源码实现进一步显示：候选 top-k 固定为 3，先要求实体类型相同，再用 GPT-4o-mini prompt 返回 `yes/no`；等价边的连通分量由 NetworkX 计算，最后让 LLM 从已有名称中选“Most Popular Name”。因此一次错误的等价边可能通过传递闭包扩大到整个连通分量，源码没有置信度阈值复核或人工审核流程（源码 commit `6eae9a11`，`rolerag/operate.py`）。

### 3. 查询理解：HyDE 式假设答案 + 实体分类

收到用户问题后，RoleRAG 先让 LLM推测“可能怎样回答这个问题”，再从原问题和假设回答中抽取潜在实体。每个实体返回（§3.4、附录 prompt）：

```text
{entity_type, entity_name, analysis, familiarity: Yes|No,
 level: specific|general}
```

- `analysis`：为什么目标角色应当或不应当知道该实体。
- `familiarity`：该实体是否处于角色认知范围。
- `level`：具体实体，或兴趣、爱好等一般概念。

prompt 明确让判断器参考角色与实体之间的**时间、地点、关系和文化差异**。论文将这一步称为认知边界感知，但没有训练专用分类器，也没有从图中计算一个确定的边界；边界分类本身仍依赖通用 LLM 的提示推理。

### 4. 三路检索策略

根据上述分类，系统选择三条路径（§3.4）：

- **越界实体**：不检索相关事实，而是把“不相关实体 + 判断理由”放进上下文，显式劝阻最终生成模型编造答案。
- **具体实体**：先按实体名 embedding 取相似节点，再取实体详细描述、原始文本 chunk，以及这些实体与目标角色之间的关系。
- **一般概念**：从目标角色节点的一跳邻域中，按一般实体的类型过滤，按关系强度选择 top-k 节点及关系。

公开源码默认 `QueryParam.top_k=10`；具体实体向量检索使用相似度阈值 0.55、top-3；一般概念检索按一跳关系 `weight` 降序取 top-k。源码会把越界实体及理由格式化进生成上下文，但没有硬拦截生成调用，最终是否拒答仍由生成模型遵循提示决定。

## “知识边界”实际是什么，不是什么

RoleRAG 实际实现的是：

```text
query + hypothetical answer
  -> LLM 判断实体对当前角色是否 familiar
  -> Yes: 检索图中内容
  -> No: 注入越界理由，提示最终模型拒答
```

它**不是**以下机制：

- 没有 `chapter <= current_chapter`、`effective_at <= snapshot_time` 一类硬过滤。
- 没有逐事实的 `known_by(character)`、可见性 ACL 或正式知识边界表。
- 没有证明角色只会看到某个叙事阶段以前的事实；语料若包含全篇剧情，图也会包含全篇信息。
- 没有阻止生成模型使用参数知识；论文限制部分还明确承认，模型会与检索内容矛盾。
- 没有把“不知道”和“不相关”区分成稳定、可审计的领域状态；两者是单次 prompt 的输出。

因此，论文证明的是“动态 relevance 判断和拒答理由能够提高测试集上的越界拒答率”，不能推出“系统建立了可靠、完备、时间一致的角色知识边界”。

## 数据集与评估

### 数据集

| 数据集 | 角色数 | 范围内问题 | 越界问题 | 说明 |
| --- | ---: | ---: | ---: | --- |
| Harry Potter | 7 | 140 | 0 | 自建；每角色 10 个一般问题 + 10 个具体经历/关系问题 |
| RoleBench-zh | 5 | 240 | 117 | 共 357 题，含向古代人物询问 Apollo 11 等问题 |
| Character-LLM | 9 | 814 | 45 | 共 859 题，含范围内与越界问题 |

作者刻意选取知名角色和作品，方便人工查证。附录称，人工核查一次 RoleBench-zh 的 357 个回答约需 3 小时；用 GPT-4 评价一次 Character-LLM 生成约 5 美元。论文没有发布自建 Harry Potter 问题集或实验用完整角色语料。

### 生成模型与实现参数

- 开源通用模型：Mistral-Small 22B、Llama 3.1 8B、Qwen 2.5 14B、Llama 3.3 70B。
- 闭源通用模型：GPT-4o-mini。
- 角色专用模型：Doubao Pro 32K。
- 图构建：论文称 600-token chunk、100-token overlap；GPT-4o-mini 负责实体/关系抽取、归一化和重复描述合并。
- embedding：`text-embedding-3-large`，3072 维，cosine distance。

值得注意的是，公开源码的默认 `chunk_token_size` 是 **1200**，不是论文实验的 600；overlap 仍为 100。若直接按 README 运行默认配置，不能视为复现论文设置。

### 基线

1. `Vanilla`：只有角色扮演任务提示。
2. `RAG`：按问题与文本 chunk 的语义相似度检索。
3. `Character/User profile`：用 GPT-4 将 Wikipedia/百度百科传记总结为短角色简介并前置到问题。
4. `GraphRAG`：从实体关系知识图中检索相关信息。

RAG 和 RoleRAG 的检索库均来自 Wikipedia、百度百科和小说；论文没有给出每个角色的具体页面、小说版本、语料快照或 chunk 数量。

### 指标与评价过程

- `KE`（Knowledge Exposure，1-10，越高越好）：回答暴露角色背景、行为、知识和经历的程度。
- `KH`（Knowledge Hallucination，1-10，越低越好）：角色事实错误、误导、越界知识的严重程度。
- `UQR`（Unknown Question Rejection，0/1，越高越好）：回答是否识别并明确拒绝超出角色认知范围的问题。

GPT-4o 先给分析再评分，temperature=0.2；人工评价者查看其分析并可修改分数。论文没有报告评价人数、标注者间一致性、修改比例或显著性检验。Character-LLM 因人工核查耗时过长，只取两次 GPT-4o 评分的平均值，主表脚注明确不等同于完整人工校正。

## 主要实验结果

下表列出每个生成模型使用 RoleRAG 时的精确主表结果：

| 模型 | Harry Potter KE / KH | RoleBench-zh KE / KH / UQR | Character-LLM KE / KH / UQR |
| --- | --- | --- | --- |
| Mistral-Small 22B | 7.550 / 2.150 | 5.585 / 3.961 / 0.678 | 9.057 / 1.404 / 0.959 |
| Llama 3.1 8B | 7.750 / 2.352 | 5.608 / 4.126 / 0.661 | 8.653 / 1.961 / 0.908 |
| Qwen 2.5 14B | 7.986 / 2.071 | 6.798 / 2.538 / 0.832 | 9.238 / 1.231 / 0.974 |
| Llama 3.3 70B | 8.564 / 1.743 | 6.723 / 2.622 / 0.837 | 9.270 / 1.265 / 0.974 |
| GPT-4o-mini | 8.821 / 1.571 | 6.994 / 2.697 / 0.857 | 9.138 / 1.211 / 0.978 |
| Doubao Pro 32K | 8.221 / 1.564 | 7.733 / 1.689 / 0.952 | 8.970 / 1.313 / 0.956 |

以 GPT-4o-mini 为例，RoleRAG 相比 GraphRAG：

| 数据集 | GraphRAG | RoleRAG |
| --- | --- | --- |
| Harry Potter | KE 8.729 / KH 1.776 | KE 8.821 / KH 1.571 |
| RoleBench-zh | KE 6.445 / KH 3.429 / UQR 0.717 | KE 6.994 / KH 2.697 / UQR 0.857 |
| Character-LLM | KE 9.136 / KH 1.308 / UQR 0.958 | KE 9.138 / KH 1.211 / UQR 0.978 |

结果并非所有模型、所有指标都单调优于各基线。例如：

- Harry Potter 上，Mistral 的普通 RAG KE 7.786，高于 RoleRAG 的 7.550。
- Llama 3.1 的 Vanilla KH 2.200，低于 RoleRAG 的 2.352。
- RoleBench-zh 上，Mistral 的 User profile UQR 0.711，高于 RoleRAG 的 0.678；Llama 3.1 的 GraphRAG UQR 0.678，高于 RoleRAG 的 0.661。
- Character-LLM 上，Llama 3.3 的 GraphRAG KE 9.302，高于 RoleRAG 的 9.270。

所以更准确的结论是：RoleRAG 在主表中**整体、通常**更好，尤其在较强模型和越界拒答上表现稳定；不能表述为每个单元格都胜出。作者也承认 GPT-4o judge 常给普通正确答案 8-9 分、给低幻觉分，导致天花板效应和差距看起来较小。

## 消融与分组结果

### 实体归一化 × 检索策略

RoleBench-zh、GPT-4o-mini 的消融结果：

| 实体归一化 | 检索 | KE | KH | UQR |
| --- | --- | ---: | ---: | ---: |
| 无 | GraphRAG local search | 6.006 | 4.126 | 0.745 |
| 有 | GraphRAG local search | 6.431 | 3.409 | 0.770 |
| 无 | RoleRAG retrieval | 6.154 | 3.454 | 0.762 |
| 有 | RoleRAG retrieval | 6.994 | 2.697 | 0.857 |

归一化和新检索策略单独启用都有改善，二者组合最好。不过这不是严格的单变量检索消融：所谓 local search 采用 GraphRAG 从相似节点出发扩展邻居和 community；论文没有分别消融 HyDE、specific/general 分类、越界理由或一跳类型过滤。

### 一般问题与具体问题

在 Harry Potter 数据集上，RoleRAG 对强模型的一般问题和具体问题提升更明显。例如 GPT-4o-mini：

- 一般问题：KE `7.671 -> 8.957`，KH `1.371 -> 1.157`。
- 具体问题：KE `7.314 -> 8.686`，KH `2.871 -> 1.986`。

小模型并非总能利用检索上下文：Mistral 的具体问题 KH 从 2.600 变差到 2.814，Llama 3.1 从 3.058 轻微变差到 3.070。论文据此指出，较小 LLM 对检索知识的吸收能力较弱。

### 低频角色

以不同模型结果汇总的角色频率表中，低频角色收益较大：Ludovic Bagman 的 KE `7.08 -> 8.18`、KH `2.46 -> 1.68`；Padma Patil 的 KE `7.14 -> 8.40`、KH `2.21 -> 1.34`。但热门角色并非所有指标都改善：Harry Potter 的 KH `1.69 -> 1.97`，Voldemort 的 KH `1.85 -> 1.98`。

## 论文案例

附录以 Beethoven 的问题 “What was the nature of your relationship with Haydn and Mozart?” 展示检索过程：系统抽取 Beethoven、Joseph Haydn、Wolfgang Amadeus Mozart，均判断为 Beethoven 熟悉的 specific 实体；随后检索三者的节点描述，以及 Beethoven-Haydn、Beethoven-Mozart 的关系描述，再聚合为上下文。这个案例证明了输出格式和路由流程，但没有展示对应最终回答、与基线的并排比较或事实级正确率。

## 与 CharacterGPT 组合到 Shiori 的方式

两篇论文解决的是不同层次：

```text
CharacterGPT
原作章节 -> 阶段 persona / snapshot

RoleRAG
当前问题 -> 实体识别与边界判断 -> 图检索 / 越界提示
```

对 Shiori 更可靠的组合应是：

1. CharacterGPT 式流程生成不可变 `CanonSnapshot`，记录角色在某章/事件后的 persona、关系、经历和知识截止点。
2. 图中的每个事实保留 `source`、`chapter/event`、`effective_at`、`known_by` 和抽取证据，而不只保存一段 LLM 摘要。
3. 查询时先用**硬条件**按 snapshot 过滤不可见事实，再借鉴 RoleRAG 的实体归一化、specific/general 路由和一跳关系检索。
4. 动态 LLM boundary judgment 只能作为补充信号，用于识别问题中的跨时代/跨世界观概念和生成自然拒答理由；不能推翻硬 cutoff。
5. 最终生成上下文应同时包含阶段 persona、允许检索到的事实、明确未知项和来源证据。

对应到当前 Shiori 语义，CharacterGPT 的 epoch 更像原作阶段版本；正式运行历史仍由 `StoryBeat` 表示，`StoryTurn` 是一次生成边界。RoleRAG 更适合位于 snapshot 选择之后、生成之前的检索层，而不是替代正式历史或角色状态模型。

## 不能从论文直接推出什么

- 不能推出 RoleRAG 能自动从原作全文建立准确的章节时间线；其图构建没有章节排序机制。
- 不能推出它能防止角色剧透；全篇语料建立的图可能包含未来事实。
- 不能推出越界判断稳定或可审计；判断是 prompt 输出，没有边界分类准确率。
- 不能推出实体归一化可靠；论文没有别名消歧的独立标注集和精度。
- 不能推出它适用于多轮长期角色交互；实验明确只做单轮。
- 不能推出它解决记忆写回、用户补充设定、正典/非正典冲突或事实来源优先级。
- 不能推出图检索结果一定会被遵循；论文观察到 LLM 可能与检索内容矛盾。
- 不能把自建 Harry Potter 前置观察或主实验外推为所有作品、冷门角色或开放世界的普遍结论。

## 论文明确限制与额外风险

论文 Limitations 明确列出：

1. LLM judge 过度自信，评分区分度不足；人工评估需要对角色和作品有深入知识。
2. 如何让 LLM 真正理解角色知识极限仍是待研究问题。
3. 只评估单轮对话；多轮中的人格一致性、历史管理和事实累积尚未解决。
4. 生成模型如何使用检索知识并不清楚，且会出现与检索内容矛盾的实例。

此外，从方法和材料还能确认：没有显著性检验；没有报告图规模、构建成本、延迟、token/API 成本；没有对知识图谱抽取质量、边界分类和实体归一化做独立评估；角色语料来自多种来源，但没有讨论来源冲突、版权、版本差异和正典优先级。

## 官方源码与可复现性状态

论文 Ethics 写的是“将公开代码”。当前确有一个作者关联的匿名仓库：论文 arXiv LaTeX 源码中注释掉的代码链接正是 `https://github.com/AnonymousSub123/RoleRAG`。仓库创建于 2025-02-11，最后代码提交为 2025-02-16 的 `6eae9a11`；截至 2026-08-17，包含 Python 包、NetworkX/JSON/DataFrame/NanoVectorDB 存储、OpenAI/Ollama 接口和一份 Beethoven 语料。

可复现性仍然有限：

- 未发布三个评测数据集的实验快照、自建 Harry Potter 问题、各角色完整语料、图产物、主表运行脚本或评分结果。
- README 只有建图和查询示例，没有实验配置、随机种子、模型版本锁定、成本或端到端复现命令。
- `requirements.txt` 未锁版本；仓库没有 `LICENSE` 文件，尽管 `setup.py` classifier 声称 MIT。
- README 和 `test_query.py` 以两个参数调用 `rag.query(character, question)`，但当前实现签名是 `query(character, source, question, param=...)`，示例会因缺少参数失败。
- 默认 `QueryParam.only_need_context=True`，即默认只返回上下文，不生成最终角色回答；这也与 README 的表面语义不一致。
- 论文实验 chunk=600，而源码默认 chunk=1200；源码必须显式覆盖配置才接近论文设置。
- 仓库只有脚本式 `test_*.py`，没有可自动验证论文结果的测试套件。

因此，源码足以核对核心管线和 prompt 思路，但不足以独立复现论文主表。最稳妥的状态描述是“核心原型已公开，完整实验不可复现”。

## 参考来源

1. Wang, Yongjie; Leung, Jonathan; Shen, Zhiqi. *RoleRAG: Enhancing LLM Role-Playing via Graph Guided Retrieval*. arXiv:2505.18541v1, 2025-05-24. [PDF](https://arxiv.org/pdf/2505.18541)。问题与贡献见 pp. 1-2；方法见 pp. 3-4；实验与主表见 pp. 4-8；限制见 p. 9；数据统计、评价流程、案例和 prompts 见 pp. 10-17。
2. [arXiv 源码包](https://export.arxiv.org/e-print/2505.18541)，`main.tex` 中注释的官方匿名仓库地址，以及 `content/Methodology.tex`、`Experiment.tex`、`appendix.tex`、`Limitation.tex`（访问日期：2026-08-17）。
3. [AnonymousSub123/RoleRAG](https://github.com/AnonymousSub123/RoleRAG)，commit [`6eae9a11`](https://github.com/AnonymousSub123/RoleRAG/commit/6eae9a11496c87d78746d5ad853ad78af22dcf97)（访问日期：2026-08-17）。核心实现见 `rolerag/operate.py`、`rolerag/rolerag.py`、`rolerag/prompt.py`、`rolerag/base.py`；运行说明见 README。
