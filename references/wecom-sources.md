# 企微侧来源与 ID 取法

> 本文回答两个问题：**`files[].id` 能填什么形态** / **用户给的是微盘分享链接时怎么办**。
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

微盘**分享链接**（`https://drive.weixin.qq.com/s?k=…`）**服务端不接受**：实测 `create` 原样提交回
`failed_code: import_failed` / `failed_reason: 非法的 'file_id'`（原文见 §1.2）。
必须先换成 `file_id` —— **这一步本 skill 不做**，由 Agent 在对话中完成（§2）。

### 形态全表（脚本 `classify_id()` 的本地白名单与此一致）

| 资产 | 形态 | 示例 | 能否提交 | 实测状态 |
|---|---|---|---|---|
| 企微在线文档 doc | 完整 URL | `https://doc.weixin.qq.com/doc/w3_AE8…?scode=…` | ✅ ⭐ 推荐 | ✅ **已实测 succeed** |
| 企微智能文档 smartpage | 完整 URL | `https://doc.weixin.qq.com/smartpage/a1_AC0…?scode=…` | ✅ ⭐ 推荐 | ✅ **已实测 succeed** |
| 智能文档子页 | URL + fragment | `https://doc.weixin.qq.com/smartpage/a1_xxx#page=<pageId>` | ✅ | ✅ 身份锚点（`include_subpages` 下每个子页落成独立子条目） |
| 微盘文件 | `file_id` | `fi…`（`fi` + 长串，实测 109 字符） | ✅ ⭐ **唯一被接受的微盘形态** | ✅ **已实测 succeed** |
| 微盘文件 | **分享链接** | `https://drive.weixin.qq.com/s?k=<share_key>` | ❌ **不接受**（须先换成 `file_id`） | ❌ 原样提交实测 `import_failed`（§1.2） |
| 企微在线表格 sheet | 完整 URL | `https://doc.weixin.qq.com/sheet/<id>` | ⚠️ 未实测 | ⚠️ **未实测**（按同一 provider 路径推断） |
| 企微智能表格 smartsheet | 完整 URL | `https://doc.weixin.qq.com/smartsheet/s3_ABoA…?scode=…` | ⚠️ 未实测 | ⚠️ **未实测**（`s3_` 前缀系枚举时**观察到**，但**未做 `create` 提交实测**——「观察到」≠「实测成功」） |
| 企微在线文档 doc | 裸 docid | `w3_<docid>` | ✅ | ✅ 已实测 succeed |

### 🔴 微盘分享链接：服务端不接受该**形态**，必须**先换成 `file_id`**

**结论一句话：分享链接不能原样提交。本 skill 不代换 —— 由 Agent 在对话中把它换成 `file_id` 后再写进 config。**

实测 `create` **原样提交** `https://drive.weixin.qq.com/s?k=<share_key>` 的结果：

```json
{ "failed_code": "import_failed",
  "failed_reason": "非法的 'file_id', 请重新检查'file_id'的值是否正确: https://drive.weixin.qq.com/s?k=<share_key>" }
```

- 该链接经解析能正常返回 `file.id`（见 §2），说明**链接本身有效**，是**服务端侧**不接受这个形态。
- 需求摘要 §2.2 最初记为「微盘分享链接 ✅ succeed」，**该记载已按本次实测改正**：服务端**只认 `file_id`**，
  **不存在「两种形态都行」的做法**。
- **本 skill 的行为（2026-09-21 起）**：候选若是分享链接 → `build_plan()` 经 `REJECTED_KINDS` **直接拒收**，
  `dry-run` / `create` 打印「本 skill 不做 ID 换算」+ 换法指引，`exit 1`，**不发出导入请求**
  （此前已为构建去重索引发过 `entry_list_children` 读请求）。
  > 边界理由：不把「本机是否装了某个企微侧工具」变成 skill 的隐式前置条件。
- ⚠️ **归一后不是同一身份**：`norm()` 保留分享链接的 `s?k=<k>`，而 `file_id` 的归一值是它自己 ——
  两者**不相等**。所以「拿分享链接去目标目录索引里找」**永远找不到**，转换是**必需的**，且必须在**提交之前**完成。
- ⚠️ **分寸**：**文档类**才是「混用两种形态即重复」（见下一节）；微盘只固化 `file_id` 一种写法。

### 🔴 「裸 docid」与「URL」也**不是**同一个身份

实测：`…/doc/w3_AE8…?scode=…`（逐字相同）→ 去重；剥掉 `?scode=` → `add_num`（新增）；裸 `w3_AE8…` → `add_num`（新增）。

→ **同一份资产只固化一种形态并始终复用它**。混用会让服务端判为多个身份，**产生重复条目**。

> 补充（2026-09-20 用户裁决）：**优先用「带 `?scode=` 的完整 URL」**。裸 `docid` 虽然服务端也认，但
> **正常用户从企微界面拿不到 `docid`** —— 把裸 docid 当推荐形态写进文档/话术，会让用户无从下手。
> 裸 docid 仅作**兼容**保留（已固化 `docid` 的老配置可继续用）。

### 🔴 `docid` 的前缀远不止 `w3_` / `a1_` / `b1_`

枚举 94 条并扫描 `docid` 字段（当时的枚举能力见下方说明），实际出现的前缀有：
`w3_`（doc）、`a1_`（smartpage）、`s3_`（sheet）、`m4_`（smartsheet）、`d3_` / `e3_`（表格类）、
`p3_`（ppt）、`f4_` / `c2_`（收集表 forms）。

- 脚本把 `w3_` / `a1_` / `b1_` 视为**已实测**；其余前缀（`c2_` `d3_` `e3_` `f4_` `m4_` `p3_` `s3_`）
  仅**放行**（避免用户合法粘贴的裸 docid 被误判为「形态非法」），标注为**未实测**，`render_plan` 会打印提示。
- 这些前缀**放行 ≠ 验证过能导入**，别当事实引用。
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

## 2. 把微盘分享链接换成 `file_id`（**Agent 在对话中做，本 skill 不做**）

本 skill 只接受服务端认的形态。用户手上若只有微盘分享链接，**Agent 在对话中**完成下面这一步，
拿到 `file.id` 后由 Agent 写进 `config.json` 的 `source.candidates`。

企微侧只读查询通道（本机已安装并授权）—— `disk files get` 就是「分享链接 → file_id」：

| 用途 | 命令 |
|---|---|
| 微盘文件元信息（**分享链接 → file_id**） | `wecom-cli disk files get --json '{"url":"https://drive.weixin.qq.com/s?k=xxx"}'` |
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
#    · 微盘 → 先按 §2 在对话中换成 file_id（Agent 引导，本 skill 不做）

# 2. 由 Agent 写进 config.json 的 source.candidates —— 原样粘贴，别手改
#    （只有 id 字段必填；key / include_subpages / note 都可省略）

# 3. 预演确认匹配结果与统计
python3 scripts/sync.py dry-run --profile <name>

# 4. 真实提交
python3 scripts/sync.py create --profile <name>
```

**同一资产只固化一种形态并复用它**：
- **文档类**：带 `?scode=` 的完整 URL / 剥掉 query 的 URL / 裸 docid 三者**互不相等**，混用即重复导入；
- **微盘**：只用 `file_id` 一种写法（分享链接不被服务端接受，也不参与匹配）。

> ⚠️ 枚举侧的**完整性未验证**（`list` 与 `search` 两条路径视图不同、`list` 不返回 folder），
> 且枚举能力已不在本 skill 内。详见 `pitfalls.md` §2.4 (c) 与 §2.8。
