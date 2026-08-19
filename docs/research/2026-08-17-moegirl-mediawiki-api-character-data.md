# 萌娘百科 MediaWiki API 角色资料能力调研

调研日期：2026-08-17

## 结论

萌娘百科的 MediaWiki API 可以作为作品角色创建的**候选定位和参考资料源**，但不能直接当成完整的 Canon 角色数据库。

当前匿名 API 实测可获取：

- 页面候选、标题和 URL；
- 页面 ID、长度、最后修订 ID、更新时间；
- 导语或完整纯文本摘要；
- 分类、内部链接、模板名称、图片文件名；
- 页面主图缩略图和原图 URL；
- 外部链接、正向和反向重定向、消歧义标记。

当前匿名 API 实测不可获取：

- `list=search` 的全文搜索结果与片段；
- revision 历史或当前 revision 的原始 wikitext；
- `action=parse` 提供的结构化章节、解析 HTML 和模板展开结果；
- `imageinfo` 的文件尺寸、MIME、作者、时间戳和扩展元数据；
- `allpages`、`list=prefixsearch`、`paraminfo` 等枚举/发现接口；但
  `generator=prefixsearch` 当前可以匿名使用。

因此，当前可行的链路是：

```text
opensearch 找页面候选
  -> 必要时用 generator=prefixsearch 同时取得候选导语
  -> query + redirects 确认规范标题
  -> info/extracts/pageprops/pageimages 取得正文概览和主图
  -> categories/links/templates/images/extlinks 补充特征与关联项
  -> 本地从 plaintext extract 识别标题和候选经历段
  -> 由 Agent 做来源降权、Canon 交叉验证和用户访谈
```

不能把萌百分类或正文陈述直接等价为官方 Canon。萌百是协作编辑百科，且当前允许的 API 响应无法保留每条陈述对应的引用、原作章节和“官方/编辑推断/梗”边界。

此外，萌百当前 `robots.txt` 和 `llms.txt` 对 AI 使用有明确约束：允许有限片段的非商业研究、教育、分析和高层摘要，要求署名并链接原文；禁止商业 AI 训练、转售或货币化 AI 服务、完整条目复刻，以及“信息框等价结构化数据集”。这不是单纯的技术限流问题，若 Shiori 用于商业或货币化场景，需要先取得许可或选择其他数据源。

## 入口与站点能力

API 入口：[`https://zh.moegirl.org.cn/api.php`](https://zh.moegirl.org.cn/api.php)

`meta=siteinfo` 实测返回：

- MediaWiki `1.43.3`；
- `TextExtracts`；
- `PageImages`；
- `Disambiguator`；
- `CirrusSearch`；
- 自定义 `MoegirlAPIRestriction`。

基础请求：

```http
GET /api.php?action=query&meta=siteinfo&siprop=general|extensions&format=json&formatversion=2
```

2026-08-17 匿名请求返回 HTTP 200。无自定义 User-Agent 的单次请求同样返回 200，但生产代码仍应按 MediaWiki API 礼仪提供可识别的 User-Agent。

站点安装了标准 MediaWiki 搜索和解析能力，不代表这些模块对匿名 API 开放。`MoegirlAPIRestriction` 会对部分只读请求返回：

```json
{
  "error": {
    "code": "action-notallowed",
    "info": "Unauthorized API call"
  }
}
```

HTTP 状态仍为 `200 OK`，响应头包含 `mediawiki-api-error: action-notallowed`。调用方不能只按 HTTP 状态判断成功，必须检查 JSON `error`。

## 搜索与页面定位

### `list=search`：当前不可用

标准 MediaWiki 的 [`list=search`](https://www.mediawiki.org/wiki/API:Search) 理论上可返回标题、命中片段、字数、大小和时间戳。萌百匿名请求实测返回 `action-notallowed`：

```http
GET /api.php?action=query&list=search&srsearch=御坂美琴&srlimit=5&format=json&formatversion=2
```

### `action=opensearch`：当前可用

推荐用 [`action=opensearch`](https://www.mediawiki.org/wiki/API:Opensearch) 做标题候选发现：

```http
GET /api.php?action=opensearch&search=御坂美琴&limit=8&namespace=0&format=json
```

实测“御坂美琴”返回包括：

- `御坂美琴`
- `御坂美琴(蔚蓝档案)`
- `御坂美琴(蔚蓝档案)/MomoTalk`
- `御坂美铃`

它只返回查询词、标题候选、空描述和 URL，没有全文命中片段。把“角色名 + 作品名”直接作为搜索字符串时，三个样本都没有结果：

- `御坂美琴 魔法禁书目录`
- `芙莉莲 葬送的芙莉莲`
- `后藤一里 孤独摇滚`

因此产品侧应先按角色名取候选，再用候选页面的导语、分类和内部链接核对作品；不能假设站内搜索支持自然语言组合查询。

昵称可以返回重定向页，例如“炮姐”和“波奇酱”，但仍需用 `redirects=1` 解析为规范标题。

### `generator=prefixsearch`：当前可用

虽然 `list=prefixsearch` 当前会返回 `action-notallowed`，但通过
`generator=prefixsearch` 驱动页面查询可以匿名使用，并能在一次请求中组合
`extracts` 等页面属性：

```http
GET /api.php
  ?action=query
  &generator=prefixsearch
  &gpssearch=芙莉莲
  &gpslimit=10
  &prop=extracts
  &exintro=1
  &explaintext=1
  &format=json
  &formatversion=2
```

实测会返回“芙莉莲”“芙莉莲(坎公骑冠剑)”等候选及其导语。相比
`opensearch`，它更适合直接取得候选页面的身份说明；调用方仍需结合用户给出的
作品名做二次匹配。

## 页面查询与重定向

标准 [`action=query`](https://www.mediawiki.org/wiki/API:Query) 可按 `titles` 查询多个页面，并组合多个开放的 `prop`：

```http
GET /api.php
  ?action=query
  &titles=炮姐|波奇酱|芙莉莲
  &redirects=1
  &converttitles=1
  &prop=info|extracts|pageprops|pageimages
  &exintro=1
  &explaintext=1
  &piprop=thumbnail|original
  &pithumbsize=300
  &format=json
  &formatversion=2
```

实测正向重定向：

- `炮姐 -> 御坂美琴`
- `波奇酱 -> 后藤一里`

[`prop=redirects`](https://www.mediawiki.org/wiki/API:Redirects) 可反查指向角色页的别名。后藤一里样本返回了“后藤独”“後藤ひとり”“波奇酱”“小波奇”“小孤独”等 5 个重定向标题，可用于别名识别。

不存在的标题会返回 `missing: true`，调用方应保留该状态，不能把空数据当成真实角色。

## 摘要与完整纯文本

萌百安装并开放 [`prop=extracts`](https://www.mediawiki.org/wiki/Extension:TextExtracts#API)。导语请求：

```http
GET /api.php
  ?action=query
  &titles=芙莉莲
  &prop=extracts
  &exintro=1
  &explaintext=1
  &format=json
  &formatversion=2
```

三个样本都能获得一句角色身份和作品归属，可用于候选页面消歧。

去掉 `exintro=1` 后可获得完整的纯文本 extract。实测规模：

| 角色 | 页面 wikitext 长度（`info.length`） | plaintext extract 字符数 | 可识别的角色相关标题 |
|---|---:|---:|---|
| 御坂美琴 | 107,259 | 13,772 | 简介、人物特点、能力与装备、人际关系、经历 |
| 芙莉莲 | 29,167 | 4,392 | 简介、经历概要、魔法 |
| 后藤一里 | 28,354 | 7,416 | 官方介绍、外貌、性格、特长、经历及多个剧情阶段 |

`explaintext=1` 的结果仍保留 `== 标题 ==` 形式的章节标记，因此可以在本地做粗粒度章节切分。但这不是稳定的结构化章节 API：

- 各页面编辑风格不同；
- 模板生成的小标题可能丢失等号层级；
- 引用和脚注不会作为逐条 provenance 保留下来；
- 模板字段不会变成统一 JSON；
- 正文混有梗、萌战战绩、外界影响和衍生作品内容；
- 内容可能包含最新剧情剧透，不能自动等价为某个 Canon 截止点。

`exchars` 或 `exsentences` 可以限制返回规模，适合候选确认；角色编译若需要正文，只应按需取得有限章节并保留原页链接。

## 分类、链接、模板和图片

以下标准查询模块当前均可用，并支持 `continue` 分页：

- [`prop=categories`](https://www.mediawiki.org/wiki/API:Categories)
- [`prop=links`](https://www.mediawiki.org/wiki/API:Links)
- [`prop=templates`](https://www.mediawiki.org/wiki/API:Templates)
- [`prop=images`](https://www.mediawiki.org/wiki/API:Images)

组合请求示例：

```http
GET /api.php
  ?action=query
  &titles=后藤一里
  &prop=categories|links|templates|images|extlinks|redirects
  &cllimit=max
  &pllimit=max
  &tllimit=max
  &imlimit=max
  &ellimit=max
  &rdlimit=max
  &format=json
  &formatversion=2
```

三个角色实测：

| 角色 | 分类 | 内部链接 | 模板 | 图片 | 外部链接 | 反向重定向 |
|---|---:|---:|---:|---:|---:|---:|
| 御坂美琴 | 51 | 至少 500，需 continuation | 109 | 69 | 8 | 1 |
| 芙莉莲 | 29 | 141 | 54 | 5 | 2 | 1 |
| 后藤一里 | 40 | 152 | 92 | 52 | 6 | 5 |

### 分类能提供什么

分类包含作品、身份、外貌、能力、声优和萌属性。对 RP 较有用的样本包括：

- 御坂美琴：`优等生`、`傲娇`、`元气`；
- 芙莉莲：`不懂爱`、`怕黑`、`收集癖`、`赖床`、`魔法师`；
- 后藤一里：`弱气`、`社交恐惧症`、`阴角`、`吉他`。

这些分类适合生成“待验证特质候选”，不适合直接成为人格真值。分类粒度不统一，可能是编辑社区标签、梗、外貌或身份，且没有强度、触发条件、剧情阶段和来源等级。

### 内部链接能提供什么

内部链接可发现：

- 作品页；
- 相关角色和组织；
- 能力、物品和地点；
- 事件年表或世界观页面。

例如芙莉莲页面链接到 `葬送的芙莉莲/事件年表`。它适合作为下一轮候选页面发现机制，但页面链接集合会混入歌曲、萌战、声优、通用概念和导航模板链接，必须按页面类别和正文位置进一步过滤。

### 模板能提供什么

模板列表可以提示页面使用了 `人物信息`、`萌点`、`剧透提醒` 等模板，但当前拿不到模板调用参数。由于 `revisions` 和 `action=parse` 被限制，不能通过匿名 API 把人物信息框稳定转换为结构化字段。

这也意味着当前 API 不能直接产出“姓名、年龄、生日、身高、声优、阵营”等统一角色表。尝试从 rendered plaintext 反推字段既脆弱，也可能触及萌百 `llms.txt` 明确禁止的“infobox-equivalent structured datasets”。

### 图片能提供什么

`prop=images` 只返回页面使用的文件标题。`prop=pageimages` 当前可返回页面代表图：

```http
GET /api.php
  ?action=query
  &titles=芙莉莲
  &prop=pageimages
  &piprop=thumbnail|original
  &pithumbsize=300
  &format=json
  &formatversion=2
```

三个样本都返回了 `thumbnail.source` 和 `original.source`。但 [`prop=imageinfo`](https://www.mediawiki.org/wiki/API:Imageinfo) 实测返回 `action-notallowed`，因此无法通过当前匿名 API 获取文件作者、时间、许可扩展元数据、SHA1、MIME 等。产品不应仅凭图片 URL 就下载或再分发，需要单独验证素材授权。

## 消歧义

萌百安装了 Disambiguator。按照其 [API 约定](https://www.mediawiki.org/wiki/Extension:Disambiguator#API)，查询 `pageprops` 时，存在 `disambiguation` 属性即表示消歧义页：

```http
GET /api.php
  ?action=query
  &titles=爱丽丝|凛|Saber
  &prop=info|pageprops|extracts
  &exintro=1
  &explaintext=1
  &format=json
  &formatversion=2
```

三个样本均返回 `pageprops.disambiguation`。角色创建 Agent 应在这种情况下展示若干候选及作品归属，让用户选择，而不是自行猜一个角色。

## 当前被限制的模块

2026-08-17 匿名、带描述性 User-Agent 实测：

| 请求 | 标准 MediaWiki 理论能力 | 萌百当前结果 |
|---|---|---|
| `list=search` | 全文搜索、snippet、字数、时间 | `action-notallowed` |
| `list=prefixsearch` | 前缀候选 | `action-notallowed`；可改用当前开放的 `generator=prefixsearch` |
| `list=allpages` | 页面枚举 | `action-notallowed` |
| `prop=revisions` | revision 元数据和 wikitext | `action-notallowed`，即使不请求正文 |
| `action=parse` | sections、HTML、wikitext、链接、模板、图片、分类 | `action-notallowed` |
| `prop=imageinfo` | 文件 URL、尺寸、MIME、作者、许可元数据 | `action-notallowed` |
| `action=paraminfo` | 当前 API 模块参数发现 | `action-notallowed` |

标准能力说明：

- [Revisions API](https://www.mediawiki.org/wiki/API:Revisions)
- [Parsing wikitext](https://www.mediawiki.org/wiki/API:Parsing_wikitext)
- [Imageinfo API](https://www.mediawiki.org/wiki/API:Imageinfo)

这些限制可能随站点策略变化。集成时应做 capability probe，并在缓存中记录探测日期，不能把本次结果硬编码为永久事实。

兼容性提醒：任何工具若通过 `prop=revisions&rvprop=content&rvslots=main` 实现 `--wikitext`，在萌百当前匿名 API 下都会失败。Character Skill Producer 一类依赖原始 wikitext 的抓取脚本不能直接复用，需要切换到开放的 extracts 路径，或把官方/用户提供文本作为主要输入；不能用页面 HTML 抓取去绕过站点的 API 与机器人策略。

## 时间线和角色行为能否可靠抽取

### 能辅助抽取，但不能单源可靠定稿

三个样本说明页面常常包含 RP 有价值的材料：

- 御坂美琴：人物特点、人际关系、经历、能力差异；
- 芙莉莲：经历概要和粗粒度阶段，如早年、辛美尔时期；
- 后藤一里：明确的性格、特长、经历，以及“加入结束乐队”“结识喜多郁代”“发光发热”等剧情阶段。

这些内容可以让 Agent 生成候选：

```text
候选性格特征
候选重要关系
候选剧情节点
候选行为样本
候选知识边界
```

但不能仅凭萌百生成“官方 Canon 时间线”和可执行行为规则，原因包括：

1. 当前 API 不能取得每条陈述对应的引用和原作位置。
2. 分类与正文混合事实、社区概括、梗、二手解读和衍生作品。
3. 页面结构不统一；有的角色按事件分段，有的只有一段“经历”。
4. `extracts` 是渲染后纯文本，缺少模板语义和部分章节结构。
5. 页面反映的是当前编辑版本，可能覆盖整个作品进度，无法天然建立用户选择的 Canon cutoff。
6. 描述“傲娇”“社恐”只能提供标签，无法给出稳定的“触发 -> 反应 -> 内部原因”。

### 对 Role Interview 的合理用法

萌百数据应作为 `source_claim`，而不是默认 `canon_fact`：

```json
{
  "content": "候选角色特征或经历",
  "kind": "source_claim",
  "source": {
    "provider": "萌娘百科",
    "page_title": "后藤一里",
    "page_url": "https://zh.moegirl.org.cn/后藤一里",
    "page_id": 404558,
    "last_revision_id": 8606350,
    "retrieved_at": "2026-08-17"
  },
  "confidence": 0.6
}
```

推荐流程：

1. 用 `generator=prefixsearch` 或 `opensearch` 找候选页。
2. 用导语、分类和作品链接确认角色身份。
3. 从完整 extract 的标题和有限片段生成候选剧情节点。
4. 用官方角色页、官方剧情简介或用户提供的原作文本交叉验证关键节点。
5. 向用户展示易懂的阶段差异，由用户选择体验状态。
6. 将萌百陈述标记为 `source_claim`；只有得到更强来源支持后才提升为 `canon_fact`。
7. 通过访谈把标签转成具体行为样本，而不是直接写进 System Prompt。

例如，萌百分类显示“社交恐惧症”，下一步应追问或从剧情样本验证：

```text
面对陌生人主动搭话时，她会回避、僵住、过度脑补，还是勉强回应？
关系熟悉之后，这种反应如何变化？
```

## 访问、User-Agent、速率与反爬边界

### User-Agent

MediaWiki 的 [API etiquette](https://www.mediawiki.org/wiki/API:Etiquette) 要求提供描述性 User-Agent，建议形式：

```text
ShioriRoleResearch/0.1 (contact: <contact>)
```

浏览器 JavaScript 无法修改 User-Agent 时使用 `Api-User-Agent`。Shiori 桌面端更适合由主进程或后端统一请求、缓存和节流，不应让每个 renderer 直接并发访问。

### 速率与重试

萌百没有在所查一手资料中公布固定 QPS 或并发额度。本次低频请求未遇到 429，也没有观察到专用的 rate-limit 响应头；这不代表可以高频抓取。

实现至少应：

- 合并多个 `prop` 到一次 query；
- 使用 `continue`，不要丢弃分页数据；
- 缓存 `pageid + lastrevid` 对应的结果；
- 非交互批处理携带 `maxlag=5`；
- 遇到 429/503 时遵守 `Retry-After` 并指数退避；
- 限制并发，避免批量枚举页面；
- 记录 `action-notallowed`，不要反复重试被策略禁止的模块。

[`maxlag`](https://www.mediawiki.org/wiki/Manual:Maxlag_parameter) 是服务端高负载保护参数，不是客户端超时。Wikimedia 的 [API rate limits](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits) 可作为保守工程参考，但不是萌百对外承诺的固定配额。

### robots.txt 与 AI 使用政策

萌百一手政策：

- [`robots.txt`](https://zh.moegirl.org.cn/robots.txt)
- [`llms.txt`](https://zh.moegirl.org.cn/llms.txt)

2026-08-17 的 `robots.txt` Content-Signal 为：

```text
search=yes, ai-train=no, use=reference
```

并明确禁止 GPTBot、ClaudeBot、CCBot 等多个机器人；通用 crawler 规则还限制 `/index.php`、`action=`、`oldid=`、`diff=` 等路径。

`llms.txt` 允许：

- 读取和总结公开条目的有限部分；
- 非商业研究、教育和分析；
- 高层、非穷举概述或事实描述。

同时要求：

- 明显署名“萌娘百科 (Moegirlpedia)”并链接原文；
- 明确说明内容是摘要而非完整条目；
- 在适用时鼓励用户访问原页；
- 可再分发的衍生摘要使用相同 CC BY-NC-SA 许可。

明确禁止：

- 商业 AI 训练、转售或货币化 AI 服务使用；
- 复刻完整条目；
- 生成与信息框等价的结构化数据集；
- 用摘要完全替代原页面。

因此建议把萌百定位为“可选参考来源”，每条引用显示来源链接，不把整页内容持久化为 Shiori 自有角色数据库，也不把它作为商业版默认角色生成数据源。

## 建议的 MVP 接入边界

可以做：

1. 用户说角色名后调用 `generator=prefixsearch` 或 `opensearch`，展示候选标题和作品。
2. 取得 `info + exintro + pageprops + pageimages` 做身份确认和有限预览。
3. 取得分类、链接和完整 extract 的标题，生成少量“待确认的特征/关系/剧情节点”。
4. 明示来源是萌娘百科摘要，并提供原页链接。
5. 让用户通过访谈确认、纠正和补足内容。
6. 关键 Canon 事实再查官方来源或要求用户提供原作文本。

不应做：

1. 把整页 extract 自动持久化为角色背景。
2. 把分类直接转成 Big Five 或行为规则。
3. 把萌百单源描述标记为官方 Canon。
4. 从页面批量构建信息框等价的结构化角色库。
5. 未核验许可就下载或再分发角色图片。
6. 依赖当前被限制的 `revisions`、`parse`、`imageinfo`。

最终判断：**萌百 API 对“角色是谁、属于什么作品、有哪些常见特征、关联哪些人物和事件、页面里大致有哪些经历段”很有帮助；对“精确 Canon 时间线、行为因果、角色在某一叙事节点知道什么”不够可靠，必须与官方来源和用户访谈组合使用。**

## 本次验证范围

实际样本：

- [御坂美琴](https://zh.moegirl.org.cn/御坂美琴)，page ID `9757`
- [芙莉莲](https://zh.moegirl.org.cn/芙莉莲)，page ID `448787`
- [后藤一里](https://zh.moegirl.org.cn/后藤一里)，page ID `404558`
- 消歧义补充样本：[爱丽丝](https://zh.moegirl.org.cn/爱丽丝)、[凛](https://zh.moegirl.org.cn/凛)、[Saber](https://zh.moegirl.org.cn/Saber)

验证方式：匿名 HTTP GET、低频串行/小规模并行请求、描述性 User-Agent、`format=json&formatversion=2`。没有登录，没有绕过站点限制，没有批量保存正文或图片。

站点 API 能力和政策都可能变化。接入前应重新读取 `robots.txt`、`llms.txt` 并运行最小 capability probe。
