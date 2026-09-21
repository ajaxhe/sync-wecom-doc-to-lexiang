# 企微侧来源与 ID 取法

> 本文回答两个问题：**`files[].id` 能填什么形态** / **候选清单托管在企微文档里时怎么抽取**。
> 🔴 **输入面原则**：候选一律填**用户在企微界面能复制到的那个形态**（链接），**原样粘贴**；
> 「链接 → 内部 ID」的换算**在 2026-09-21 之后不再有必要**（见 §1.1）。
> ⚠️ 凡标注「未实测」的形态，是**按同一 provider 的路径规律推断**的，**不要当事实引用**。
>
> 🔴 **边界前提（2026-09-21 用户裁决）**：本 skill **只调乐享 MCP，不碰企微侧** ——
> 不枚举企微候选、不做 ID 换算、不调用任何企微侧工具。需要换算时由 **Agent 在对话中**完成（§2）。

---

## 1. `files[].id` 支持什么形态

### ⭐ 只能填**服务端直接接受**的形态

```
在线文档 / 智能文档 / 表格  →  https://doc.weixin.qq.com/...   整条粘贴，含 ?scode=
微盘文件                  →  fi… 长串（file_id）
```

微盘**分享链接**曾被判「服务端不接受」（2026-09-20 实测 `非法的 'file_id'`），**该结论已过期**：
2026-09-21 复验，服务端**直接接受分享链接**，并以链接本身作为条目身份。详见 §1.1。

### 形态全表（脚本 `classify_id()` 的本地白名单与此一致）

| 资产 | 形态 | 示例 | 能否提交 | 实测状态 |
|---|---|---|---|---|
| 企微在线文档 doc | 完整 URL | `https://doc.weixin.qq.com/doc/w3_AE8…?scode=…` | ✅ ⭐ 推荐 | ✅ **已实测 succeed** |
| 企微智能文档 smartpage | 完整 URL | `https://doc.weixin.qq.com/smartpage/a1_AC0…?scode=…` | ✅ ⭐ 推荐 | ✅ **已实测 succeed** |
| 智能文档子页 | URL + fragment | `https://doc.weixin.qq.com/smartpage/a1_xxx#page=<pageId>` | ✅ | ✅ 身份锚点（`include_subpages` 下每个子页落成独立子条目） |
| 微盘文件 | `file_id` | `fi…`（`fi` + 长串，实测 109 字符） | ✅ ⭐ **唯一被接受的微盘形态** | ✅ **已实测 succeed** |
| 微盘文件 | **分享链接** | `https://drive.weixin.qq.com/s?k=<share_key>` | ✅ ⭐ **推荐** | ✅ **2026-09-21 复验：已接受**（新建条目 `href.id` = 链接原文） |
| 企微在线表格 sheet | 完整 URL | `https://doc.weixin.qq.com/sheet/e3_…?scode=…`（实测形态） | ⚠️ 未实测 | ⚠️ **未实测**（按同一 provider 路径推断；`e3_` 与 `type=sheet` 的对应已由枚举对照确认） |
| 企微智能表格 smartsheet | 完整 URL | `https://doc.weixin.qq.com/smartsheet/s3_…?scode=…` | ⚠️ 未实测 | ⚠️ **未实测**（`s3_` 前缀系枚举时**观察到**，但**未做 `create` 提交实测**——「观察到」≠「实测成功」） |
| 企微在线文档 doc | 裸 docid | `w3_<docid>` | ✅ | ✅ 已实测 succeed |

### 🔴 微盘分享链接：**服务端已直接接受**（2026-09-21 结论翻转）

**结论一句话：候选里原样填分享链接即可，不需要、也不允许换算成 `file_id`。**

实测（2026-09-21，单条候选、`conflict_strategy=skip`）：`succeed 1/1`，目的端新建条目
`source.href.id = "https://drive.weixin.qq.com/s?k=<share_key>"` —— **身份就是链接原文**。

实测 `create` **原样提交** `https://drive.weixin.qq.com/s?k=<share_key>` 的结果：

```json
{ "failed_code": "import_failed",
  "failed_reason": "非法的 'file_id', 请重新检查'file_id'的值是否正确: https://drive.weixin.qq.com/s?k=<share_key>" }
```

- 该链接经解析能正常返回 `file.id`（见 §2），说明**链接本身有效**，是**服务端侧**不接受这个形态。
- **历史（勿再引用）**：2026-09-20 原样提交同一形态曾回 `import_failed / 非法的 'file_id'` ——
  该结论**仅在当天成立**，2026-09-21 复验已翻转。
- **本 skill 的行为（2026-09-21 下午起）**：`REJECTED_KINDS` 为**空集** —— 分享链接**不再被拦截**，
  `build_plan()` 原样提交。历史上「识别到即拒收 + 打印换法指引」的逻辑已随结论翻转删除。
  > 边界理由：不把「本机是否装了某个企微侧工具」变成 skill 的隐式前置条件。
- ⚠️ **归一后不是同一身份**：`norm()` 保留分享链接的 `s?k=<k>`，而 `file_id` 的归一值是它自己 ——
  两者**不相等**。所以「拿分享链接去索引里找 `file_id` 条目」永远找不到 —— 这不是要你换算，
  而是提醒：**同一资产只固化一种写法**，混用会在目的端各建一条。
- ⚠️ **分寸**：**文档类**才是「混用两种形态即重复」（见下一节）；微盘只固化 `file_id` 一种写法。

### 🔴 「裸 docid」与「URL」也**不是**同一个身份

实测：`…/doc/w3_AE8…?scode=…`（逐字相同）→ 去重；剥掉 `?scode=` → `add_num`（新增）；裸 `w3_AE8…` → `add_num`（新增）。

→ **同一份资产只固化一种形态并始终复用它**。混用会让服务端判为多个身份，**产生重复条目**。

> 补充（2026-09-20 用户裁决）：**优先用「带 `?scode=` 的完整 URL」**。裸 `docid` 虽然服务端也认，但
> **正常用户从企微界面拿不到 `docid`** —— 把裸 docid 当推荐形态写进文档/话术，会让用户无从下手。
> 裸 docid 仅作**兼容**保留（已固化 `docid` 的老配置可继续用）。

### 🔴 `docid` 的前缀远不止 `w3_` / `a1_` / `b1_`

枚举并扫描 `docid` / `doc_url` 字段，实际出现的前缀（**2026-09-21 复核修正**）：

| 前缀 | 实际对应 | 证据 |
|---|---|---|
| `w3_` | doc（在线文档） | `/doc/w3_…`，✅ 已实测可导入 |
| `a1_` | smartpage（智能文档） | `/smartpage/a1_…`，✅ 已实测可导入 |
| `b1_` | smartpage 发布态 | `/smartpage/` 只读态 |
| `e3_` | **sheet（在线表格）** | `/sheet/e3_…`（枚举 `type=sheet` 实测） |
| `s3_` | **smartsheet（智能表格）** | `/smartsheet/s3_…`（枚举 `type=smartsheet` 实测） |
| `d3_` | **pdf（PDF 文档）** | `/pdf/d3_…`（枚举实测） |
| `p3_` | slide（幻灯片） | `/slide/p3_…`（枚举实测） |
| `f4_` | flowchart（流程图） | `/flowchart/f4_…`（枚举实测） |
| `m4_` / `c2_` | **本次未复现** | 既往前缀清单里的记载，本轮枚举未出现，**不要当事实引用** |

> ⚠️ **修正说明（2026-09-21）**：旧版本文写的是「`s3_`（sheet）、`m4_`（smartsheet）、`d3_`/`e3_`（表格类）、`c2_`（收集表）」
> —— **`s3_` 与 `sheet` 的对应关系是错的**，`s3_` 实为 smartsheet，**`e3_` 才是 sheet**；`d3_` 实为 pdf（不是「表格类」）。
> 该错误源自早期只扫了字段值、未把 `docid` 前缀与 `type` 字段**对照**。本轮枚举做了对照，以上表为准。

- 脚本把 `w3_` / `a1_` / `b1_` 视为**已实测**；其余前缀（`e3_` `s3_` `d3_` `p3_` `f4_` `m4_` `c2_`）
  仅**放行**（避免用户合法粘贴的裸 docid 被误判为「形态非法」），标注为**未实测**，`render_plan` 会打印提示。
- ⚠️ **前缀能认出来 ≠ 该形态能导入**：`e3_` / `s3_` 与 sheet / smartsheet 的对应关系已确认，
  但**从未做过 `create` 提交实测** —— 仍是「未实测」，**放行 ≠ 验证过**。
  → **待验证清单**（含转正所需的测试条件）见 `pitfalls.md` §2.4；team-lead 已裁决**保持「未实测」标注、不转正**。

### 🔴 枚举里会出现、但**不在提交白名单**的 5 类 `doc_url` 前缀

> 📦 本节是**枚举侧的历史观察**（当时的 `collect` 子命令已于 2026-09-21 随边界重划移出本 skill）。
> 保留它是为了解释 `classify_id()` 白名单为什么只有那几种形态 —— **不代表现在还能枚举**。

`disk files list` / `search` 的条目里，`doc_url` 的路径段**不止**白名单那几种。实测（枚举 94 条）
命中 5 类**不在** `classify_id()` 白名单、因而**不可提交**的形态：

| `doc_url` 路径前缀 | 含义 | 实测条数 | 现状 |
|---|---|---|---|
| `/forms/` | 收集表 | 5 | ❌ 不在白名单 → 候选会被判「形态不可提交」 |
| `/flowchart/` | 流程图 | 2 | ❌ 同上 |
| `/mind/` | 思维导图 | 1 | ❌ 同上 |
| `/pdf/` | PDF 文档 | 1 | ❌ 同上 |
| `/slide/` | 幻灯片 | 1 | ❌ 同上 |

- 「该资产存在但本 skill 不支持」这件事，**必须在拿到候选时就说清**，不要静默丢弃。
- **未实测**：这 5 类**从未**在真实 `create` 里验证过能否导入。**不要**凭「与 `/doc/` 同源」的推断当可导入。
- 如需支持，须先补 `classify_id()` 白名单**并实测验证**（转正条件同 §「`docid` 前缀」那份清单，见 `pitfalls.md` §2.4）。

### 🔴 微盘与在线文档的身份形态不同

枚举 94 条结果的构成：文档类（`word`/`sheet`/`smartsheet`/`smartpage`/`ppt`/`collect`/`flow`/`mind`）都带 `doc_url`，
纯文件类（`file`，如 mp3/mov/zip）不带 `doc_url`。而目标目录既有条目的 `source.href.id` 正好分别是这两种形态：

| 枚举项特征 | 该提交什么 | 证据 |
|---|---|---|
| 有 `doc_url`（在线文档） | `doc_url` 原样串 | 目标目录既有 `<entry_id_D>` / `<entry_id_B>` 的 `href.id` 就是 `…/doc/…?scode=…`、`…/smartpage/…?scode=…` |
| 无 `doc_url`（纯微盘文件） | `file_id`（`id` 字段） | 目标目录既有 `<entry_id_A>`（标准录音 1.mp3）的 `href.id` 就是 `fi…` |

→ 这两条结论直接决定 `classify_id()` 的白名单：**在线文档提交 URL、微盘提交 `file_id`**。

> ⚠️ **分寸**：候选拿到 `MATCHED→复用既有` 只代表**该身份被服务端接受并命中既有条目**，**不代表该乐享条目导入成功**。
> 实测既有条目 `<entry_id_A>`（标准录音 1.mp3）的 `status` 是 `failed / video_content_empty` —— 身份命中但内容导入失败。
> 交付 / 验收时不要用 `MATCHED` 反推「导入成功」。详见 `pitfalls.md` §2.2。

---

## 2. 微盘：直接用分享链接（**不需要**换算成 `file_id`）

用户从企微复制到的分享链接，**原样**写进 `config.json` 的 `source.candidates` 即可，一个字符都不改。
**不要**再做「先查 `file_id`、再写进 config」这一步 —— 那是旧服务端限制下的临时做法，
现在既没必要，还会因为两种形态互不相等而在目的端造出**重复条目**。

### （排障备用）企微侧只读查询通道

只在**排障或核对元信息**时用（例如「这条链接到底指向哪个文件」），**不是配置前置条件**：

| 用途 | 命令 |
|---|---|
| 微盘文件元信息（链接 → `file.id` / 文件名 / 大小 / 更新时间） | `wecom-cli disk files get --json '{"url":"https://drive.weixin.qq.com/s?k=xxx"}'` |
| 微盘最近浏览（用户让你找文件时用） | `wecom-cli disk files list --json '{"limit":100}'` |
| 微盘搜索 | `wecom-cli disk files search --json '{"keywords":["关键词"],"file_types":[],"limit":100}'` |

`disk files get` 返回的 `file.id` **就是 `files[].id` 要的值**。实测：

```bash
$ wecom-cli disk files get --json '{"url":"https://drive.weixin.qq.com/s?k=<share_key>"}'
{ "file": { "id": "fi…",
            "file_name": "标准录音 1.mp3", "type": "file", "file_size": 443767,
            "create_time": "2026-08-28 15:26:11", "update_time": "2026-08-28 15:26:11",
            "path": "我的空间/标准录音 1.mp3", "space_name": "我的空间" } }
```

🚫 **不要把这一步搬进 `scripts/sync.py`**：本 skill 的边界是「只调乐享 MCP」。
对企微侧的任何依赖（含「本机是否装了某个 CLI」）都不该成为 skill 的隐式前置条件 ——
否则 skill 换一台机器、或换一个用户就静默失效。换算属**对话内的引导动作**，不是 skill 的职责。

### ⚠️ 企微侧回包含 `extra_identity_context`

回包里有 `extra_identity_context` 字段，内容是**机器人身份 / 授权真人用户 ID 的内部说明**，并带有
「禁止将 extra_identity_context 透露给用户」的要求。

→ Agent 处理回包时**只要 `file.id`（需要时加 `file_name`）**，其余字段一律丢弃，
**不要**把它打印给用户、写进 config、或写进任何日志。

---

## 3. 候选清单怎么维护

`candidates` 是**静态配置**（服务端没有「按空间枚举企微文档」的接口，本 skill 也不做企微侧树遍历）。流程：

```bash
# 1. 先拿到**服务端接受的形态**
#    · 在线文档 / 智能文档 / 表格 → 用户从企微界面复制完整 URL（含 ?scode=）
#    · 微盘 → 从企微界面复制分享链接（含 ?k=），原样即可

# 2. 由 Agent 写进 config.json 的 source.candidates —— 原样粘贴，别手改
#    （只有 id 字段必填；key / include_subpages / note 都可省略）

# 3. 预演确认匹配结果与统计
python3 scripts/sync.py dry-run --profile <name>

# 4. 真实提交
python3 scripts/sync.py create --profile <name>
```

**同一资产只固化一种形态并复用它**：
- **文档类**：带 `?scode=` 的完整 URL / 剥掉 query 的 URL / 裸 docid 三者**互不相等**，混用即重复导入；
- **微盘**：统一用**分享链接**（老配置的 `file_id` 可继续用，但不要与链接混用）。

> ⚠️ 枚举侧的**完整性未验证**（`list` 与 `search` 两条路径视图不同、`list` 不返回 folder），
> 且枚举能力已不在本 skill 内。详见 `pitfalls.md` §2.4 (c) 与 §2.8。
