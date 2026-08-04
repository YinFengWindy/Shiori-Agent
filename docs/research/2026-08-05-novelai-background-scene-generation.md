# NovelAI 无角色场景图能力核验

> 核验日期：2026-08-05
>
> 范围：只核验 NovelAI 官方图像生成文档，回答 NovelAI 是否能生成不含角色的场景图，以及对 Shiori 场景 CG 的提示词建议。

## 结论

**可以。** NovelAI 当前的 V4.5 Full 和 V4.5 Curated 都支持在基础提示词最前面使用 `background dataset`。官方明确说明，该数据集用于生成风景、动物肖像、静物以及其他不含人物的图像，并且偏向摄影风格。

因此，NovelAI 可以生成无角色的场景图，但应注意两点：

- `background dataset` 是 V4.5 或更高版本的能力，并且会把结果往摄影风格推动；它不是一个专门的“空场景锁定”开关。
- 其他模型或普通场景提示词仍可能自行补出人物。需要稳定无人物时，应同时在提示词中明确场景主体，并在 Undesired Content 中加入需要排除的对象，再通过种子和多次生成筛选结果。

## 官方证据

NovelAI 官方[图像模型文档](https://docs.novelai.net/en/image/models)在 V4.5 Full 和 V4.5 Curated 的说明中都写明：`background dataset` 可放在提示词开头，用于生成 landscapes、animal portraits、still lifes 以及其他 without people 的图像，并且是 photographic style。

官方[Tagging 文档](https://docs.novelai.net/en/image/tags#dataset-tags)进一步规定：数据集标签应放在 base prompt 的最开头；`background dataset` 仅适用于 V4.5 或更高版本。

官方[Image Generation Basics 文档](https://docs.novelai.net/en/image/basics)说明，提示词前半段应放置图像的主要主体，支持 `landscape`、`wide angle` 等构图/取景描述，也允许使用自然语言描述，不要求所有内容都必须是已知标签。

官方[Undesired Content 文档](https://docs.novelai.net/en/image/undesiredcontent)说明，可以在 Undesired Content 中列出希望 AI 避免的内容，并且可以在生成后把新出现的不需要内容追加进去。

## 可直接试的提示词

### 无角色、偏摄影场景

```text
background dataset, landscape, wide angle, empty seaside town at dusk, quiet street, warm lights in windows, distant ocean, cinematic composition
```

### 无角色、偏二次元场景

```text
landscape, wide angle, empty seaside town at dusk, quiet street, warm lights in windows, distant ocean, anime background, cinematic composition
```

第二条不使用 `background dataset`，因此不强制摄影数据集；如果结果经常出现人物，改用 V4.5 并把 `background dataset` 放到最前面，再用 Undesired Content 排除人物相关对象。

可在 Undesired Content 里按需尝试：

```text
person, people, human, 1girl, 1boy, character
```

这组排除词是产品侧建议，不是 NovelAI 官方规定的固定模板，应根据生成结果逐步增删。

## 对 Shiori 场景 CG 的影响

如果目标是“角色说话时展示角色所在地点”，可以把无角色场景作为独立的视觉类型，使用场景主体和构图提示词生成；不需要为每张场景图虚构一个角色占位。

如果目标是 Galgame 菜单那种一侧留出 UI 安全区的背景，需要额外注意 V4.5 的部分 Undesired Content 预设本身包含 `negative space`。这可能和“右侧留白”诉求冲突，应使用无默认预设或自定义 Undesired Content，并实际检查生成结果。

## 官方来源

- NovelAI 图像模型：<https://docs.novelai.net/en/image/models>
- NovelAI Tagging / Dataset Tags：<https://docs.novelai.net/en/image/tags#dataset-tags>
- NovelAI Image Generation Basics：<https://docs.novelai.net/en/image/basics>
- NovelAI Undesired Content：<https://docs.novelai.net/en/image/undesiredcontent>
