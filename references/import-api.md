# 乐享导入接口参考（实测）

> 事实源：`企业微信知识库导入-Skill需求摘要.md` + 2026-09-20 本 skill 的实跑验证。
> 凡与本文冲突的推测，以本文为准（本文标注了哪些是实测、哪些是推断）。

---

## 1. 端点与鉴权

| 项 | 值 |
|---|---|
| endpoint | `https://mcp.lexiang-app.com/mcp` |
| 协议 | JSON-RPC 2.0，`method = tools/call` |
| 鉴权 | `Authorization: Bearer lxmcp_xxx`（个人 MCP Token，固定不变，适合定时任务） |
| 获取 token | `https://lexiangla.com/ai/claw` |
| 🔑 授权配置（前置） | **导入的前置条件**：该乐享企业须在乐享页面完成「授权配置」。**未完成或已过期时，鉴权可能正常、但导入任务失败** —— 按官方文档操作：<https://lexiangla.com/pages/d4a717fbf4604efea4bd286fdcdac31a?company_from=906ba45e6f9a11f089c57a2a2b4bccb6>（本 skill 不做授权、不代查状态、不复述文档内容） |

### 🔴 调用路径：**先看当前可见 tools 再选路径**（服务端可下发开关，别写死）

官方说明（MCP resource `lexiang://docs/instructions/v1`「工具调用方式」一节）原文规则：

> 以下工具列表由 MCP 服务按当前请求上下文动态追加，已根据 **company、feature_flag 和 allowlist** 过滤。
> 调用前先检查当前可见 tools：
> - 如果可见 tools 已包含目标业务工具名，**可以直接调用**该工具。
> - 如果可见 tools 不包含目标业务工具名，但包含 `call_tool`，**必须**调用 `call_tool`
>   （`tool_name` = 目标工具名，`arguments` = 目标工具的逻辑参数）。
> 例如调用 `entry_list_children` 时，**不要直接调用该工具**；应调用 `call_tool`。

**结论：这是「条件规则」，且可见集是服务端可调的状态 —— 不能猜、更不能写死一条路径。**

#### 2026-09-21「直调突然不可用」的完整结论

- **现象**：上午所有联网命令 `exit 1`；直调业务工具回纯文本 `tool is not allowed: <工具名>`，
  而同一 token、同一秒内直调 `whoami` 正常、经 `call_tool` 包装也正常。
- **真实原因（乐享侧 2026-09-21 13:19 确认）**：后台**加了个参数，让 MCP tool 列表默认隐藏掉大部分工具**，
  agent 看不到就调不到；**当日下午已放回**，客户端**重启**后生效。
  → 既不是凭证问题，也不是「平台禁止直调」。
- **⚠️ 本机实测（同日下午 14:32，个人 token 直连 HTTP 链路）**：`tools/list` **仍只回 7 个元工具**，
  `dry-run` 全程走 `call_tool` 包装并 `exit 0`。同期 `list_tool_categories` **能看到全部业务工具目录**
  （`knowledge.entry` 13 个 / `knowledge.block` 21 个 …）。
  → **「目录里可发现」≠「`tools/list` 里可见」**：前者是注册表，后者是本次下发的可见集；
  **服务端开关状态与本地客户端会话可能不同步**（要放回 + 重启才刷新）。

#### 对照实测（2026-09-21，同一 token、同一秒内）

| 调用方式 | `whoami`（元工具） | `entry_list_children` / `import_*`（业务工具） |
|---|---|---|
| **直调** `{"name":"<工具>","arguments":{…}}` | ✅ 正常（`code:0`） | ❌ 纯文本 `tool is not allowed: <工具名>` |
| **包装** `{"name":"call_tool","arguments":{"tool_name":"<工具>","arguments":{…}}}` | ✅ 正常 | ✅ 正常 |

⚠️ **别读成「凭证过期」**：`whoami` 直调成功即证明 token 有效；「只拒业务工具、同一 token 下包装就通」
这种**选择性**拒绝，机制上不可能由凭证问题产生。
⚠️ **也别读成「平台永久禁止直调」**：2026-09-21 已证明那只是**服务端一次可回滚的开关**。
🔁 **2026-09-21 20:44 复验**：`tools/list` 仍只回 7 个元工具，直调 `import_describe_task` 仍回
`tool is not allowed`、同秒经 `call_tool` 包装正常触达（回业务层 `code:71`）——可见集开关当日未放回，条件规则持续生效。

关于 `import_*` 的两点补充：`get_tool_schema` 对它们回 `tool not found`，而对 `entry_list_children`
正常返回 schema（**不是名字写错**）；18 个连接器类别枚举过，没有 `import_*` 分类。

`scripts/sync.py` 的 `mcp_call()` **先查可见 tools 再选路径**（另留一条路径兜底），
**不要**在业务代码里绕过它直连 MCP。等价 curl（`--debug` 打印）反映的就是最终发出的那一层。

---

## 2. `import_create_task`

### 请求

```json
{
  "jsonrpc": "2.0", "id": 1, "method": "tools/call",
  "params": { "name": "call_tool", "arguments": {
    "tool_name": "import_create_task",
    "arguments": {
      "space_id": "<目标知识库 space_id>",
      "type": "wecombot",
      "parent_entry_id": "<目标目录 entry_id>",
      "files": [{ "id": "<企微侧标识>", "include_subpages": true }],
      "dry_run": false,
      "conflict_strategy": "skip"
    }
  }}
}
```

### 参数全表（**本接口就这些参数，没有更多**）

| 参数 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `space_id` | ✅ | string | 目标知识库 id。用 `scripts/sync.py resolve '<目录链接>'` 自动得到，**不要让用户手填** |
| `type` | ✅ | string | 实测**仅支持** `"wecombot"`（传其他值回 `code=50090008 导入类型不支持`）。服务端回写 `source.platform="wecombot"`、`platform_i18n_name={zh_cn:"企业微信",en_us:"WeCom"}` |
| `parent_entry_id` | ✅ | string | 目标**目录** entry_id（不是 space 的 root）。同样用 `scripts/sync.py resolve` 得到 |
| `files` | ✅ | array | **非空**：传 `[]` 也报 `value is required` |
| `files[].id` | ✅ | string | 源端标识，**填用户能拿到的链接原文**：在线文档原始 URL（含 `?scode=`）/ 微盘分享链接（含 `?k=`，2026-09-21 复验服务端已接受）；`file_id`（`fi…`）与裸 docid 亦兼容但不推荐 |
| `files[].key` | 可选 | string | **文档名称**（接口设计：`id`=链接 URL，`key`=文档名称）。Agent 生成 config 时从清单文档锚文本/标题填入；⚠️ 企微侧**无法通过 URL 反查 doc 类型文档名称**，故**尽量在初始化配置时设置好**。自由文本类字段，类型探针无法发现其存在（见 §7 适用边界） |
| `files[].include_subpages` | 可选 | bool | `true` = 连子页一起导入（智能文档每个子页落成独立子条目）。缺省取 `source.include_subpages`（默认 `true`） |
| `dry_run` | 可选 | bool | `true` = 预演不写库（⚠️ **对 `conflict_strategy` 是盲的** —— 见下） |
| `conflict_strategy` | 可选 | enum | `"skip"` / `"replace"` / `"keep_both"`。**脚本一律显式下发，默认 `skip`** —— 不传时服务端默认行为是破坏性的，见下 |

- `files[].name` **不存在**：服务端以企微实际标题为准，传了不生效且会造成误导。
- 结论来源与适用边界见 §7（探测方法）。已扫过 60+ 个常见候选字段名（含 `files[]` 元素级、`import_describe_task`），**均未命中**。

### 校验行为（实测）

| 情况 | 回包 |
|---|---|
| 缺必填字段 | `code=51`，`validate proto message: validation error:` **逐条列出所有缺失项**（不会只报第一个） |
| 已知字段**类型**不符（如 `dry_run` 传字符串、`files` 传字符串） | `code=999 系统错误` |
| 已知**枚举**字段传非法值 | `code=51` + **吐出合法取值清单** |
| **未知字段** | **静默忽略，`code=0`** —— 不报错、也**不生效**（配置里写错字段名不会报错，只会静默失效） |

必填字段探针输出原文（只删掉 `parent_entry_id`）：

```
code=51 validate proto message: validation error:
 - parent_entry_id: value is required [required]
```

### 🔴 `conflict_strategy`：本接口最危险的一个参数（2026-09-20 实测）

**取值来源**：服务端校验器原文 —— 传非法值时回

```
code=51 validate proto message: validation error:
 - conflict_strategy: value must be in list ["replace", "skip", "keep_both"] [string.in]
```

| 取值 | 含义 | 风险 |
|---|---|---|
| `skip` | 跳过已存在的 | **安全档**：不动目的端既有条目 |
| `replace` | 覆盖目的端 | ⚠️ **以本次提交为准替换该目录内容，既有条目会被删除** |
| `keep_both` | 两者都保留 | ⚠️ 会产生重复条目 |

**实测事故（不传该字段）**：一次 `create`（3 条候选）后，目标目录从 **10 条变为 3 条** ——
**命中本轮候选的那 3 条保留了原 `entry_id`**（2026-09-21 复核更正：**不是"删光重建"**），
**另外 7 条（与本批候选无关的）被删除**，抽查旧 `entry_id` 全部回 `code:71 不存在`。
任务自身报 `succeed 3/3`、`add_num=0`、`exit 0`，**全程无任何删除提示**。

→ 语义归纳：**「本次提交集合」等于「保留下来的集合」；不在集合内的既有条目会被删掉**。
所以 `replace`（以及**不传该字段时的默认行为**）只能在**专用导入目录**上使用。

**两条必须记住的边界**：

1. **`dry_run` 对冲突策略是盲的**：不传 / `replace` / `skip` / `keep_both` 四路的 `dry_run_stats` 实测**完全一致**。
   → **`dry-run` 结果不能作为「真跑不会动目的端」的依据**；本次事故前 dry-run 正是报的 `add_num=0`。
2. **回包不携带 `conflict_strategy`**：`import_describe_task` 的 `data` 里没有该字段，**事后无法追溯**当时用的是哪个策略，
   所以必须在下发时显式指定并在本地留痕（脚本会打印）。
3. **去重索引有延迟**：新建条目后数分钟内，服务端可能仍把同一 `href.id` 判为 `add_num`（实测同一批候选
   4 分钟内从 `add_num=2/special_num=1` 变为 `add_num=0/special_num=3`）→ 不要用短时间内的两次 dry-run 差异下结论。

### 响应

```json
{ "code": 0, "message": "success", "data": { "task_id": "<task_id>" } }
```

🔴 **`code:0` 只代表「任务已创建」**，参数校验在**执行阶段**。必须轮询 `import_describe_task` 才能判定成败。

---

## 3. `import_describe_task`

```json
{ "jsonrpc": "2.0", "id": 2, "method": "tools/call",
  "params": { "name": "import_describe_task", "arguments": { "task_id": "<task_id>" } } }
```

### 响应（实测原文，一次真实失败任务）

```json
{ "code": 0, "message": "success", "data": {
  "status": "failed",
  "percentage": 100,
  "total_num": 3,
  "current_num": 3,
  "err_message": "导入失败，请查看失败文档",
  "failed_items": [
    { "id": "https://drive.weixin.qq.com/s?k=<share_key>",
      "name": "https://drive.weixin.qq.com/s?k=<share_key>",
      "display_icon": "page",
      "failed_code": "import_failed",
      "failed_reason": "非法的 'file_id', 请重新检查'file_id'的值是否正确: https://drive.weixin.qq.com/s?k=<share_key> (callid: …)" }
  ]
}}
```

### 字段语义

| 字段 | 含义 |
|---|---|
| `status` | `page_processing`（进行中）/ `succeed` / `failed` |
| `total_num` / `current_num` | 总条数 / 已完成数（进度） |
| `err_message` | **只有一句泛化文案**（「导入失败，请查看失败文档」），排障价值低 |
| `failed_items[]` | ⭐ **真正的失败原因在这里**：`failed_code` + `failed_reason`（含原始报错与 `callid`）。不打印它 = 用户排不了障 |
| `dry_run_stats` | 仅 `dry_run=true` 时有：`{"add_num": N, "special_num": M}` |

### `dry_run_stats` 人话翻译

| 服务端字段 | 人话 |
|---|---|
| `add_num` | **将新增 N 条**（本次会真正写入） |
| `special_num` | **M 条已存在，跳过/更新**（字节命中既有条目） |

> 实测：dry-run 的 `add_num/special_num` 与客户端归一匹配的预测**逐条吻合**
> （3 条候选 → `add_num=1, special_num=2`，与 `#1 MATCHED / #2 MATCHED / #3 NEW` 一致）。
> 可用这组数字交叉验证 `norm()` 与索引逻辑是否正确。
>
> ⚠️ **dry-run 不校验 ID 合法性**：被判 `add_num` 只表示「服务端认为这是新身份」，
> 不代表这个 ID 真的能被导入。实测那个被判 `add_num` 的分享链接，真跑 `create` 时**失败了**（见上）。

### ⭐ 实测口径（排障前必读，四条都踩过）

**① 顶层 `err_message` 没有排障价值。**

实测它**恒为一句泛化文案**「导入失败，请查看失败文档」，不含任何具体原因、也没有 `callid`。
真正的原因只在 `data.failed_items[].failed_reason`（含原始报错文本 + `callid`）。
→ 任何只打印 `err_message` 的实现都等于把用户丢在原地；**必须逐条渲染 `failed_items`**。

**② 失败项不在 `entries[]` 里。**

`entries[]` 只包含进入处理流程且**成功**的条目；失败项被挪到 `failed_items[]`，**两个数组互不重叠**。
实测一次 3 条候选的任务：`entries[]` 2 条 + `failed_items[]` 1 条 = `total_num` 3。
→ 两个数组都要渲染，只看 `entries[]` 会以为「少了一条、没跑完」。

**③ 部分失败 = 整任务 `failed`。**

上例里 2 条命中既有（等价成功）、1 条失败 → 任务整体 `status=failed`。
→ **`failed` ≠ 全军覆没**。判定口径是 `failed_items[]` 条数 vs `total_num`，
文案要写清「总计 N 条，其中 M 条未成功」，否则用户会误以为全部要重做。
退出码仍按方案给 `exit 1`（有失败就是有失败，不能被「大部分成功」吞掉）。

**④（附带）`dry_run_stats` 的计数为 0 时，服务端不回该字段。**

实测① `add_num=None, special_num=3`（3 条全命中 → 新增 0）；实测② `add_num=2, special_num=None`（命中 0）。
→ `None` 等价于 `0`，**展示时应归一成 0**，否则用户看到 `None` 会以为「服务端没算」。
判断「本次会不会新增」看 `add_num`（归一后）即可。

### ⭐ 报告能取到什么（`render_report` 三档字段的全部来源，2026-09-21 实测）

| 报告项 | 数据来源 | 备注 |
|---|---|---|
| ✅ 新增 N 条 | 本地归一匹配 `NEW→原样提交`；`dry-run` 用 `dry_run_stats.add_num` 交叉校验 | **真跑任务不回 `dry_run_stats`**，真跑时只有本地匹配计数 |
| ♻️ 已存在·复用 M 条 | 本地归一匹配 `MATCHED→复用既有`；`dry-run` 用 `special_num` 交叉校验 | 目端**条目名 + 链接**来自 `entry_list_children`，接口不回 |
| ❌ 失败 K 条 | `failed_items[]`（`failed_code` / `failed_reason`） | 见上方实测口径 ①②③ |
| 任务终态 / 进度 | `status` / `total_num` / `current_num` | 真跑与 dry-run 都回 |

**接口没有的维度 —— 不要在脚本里造：**

- **条目级操作类型**：回包里既无 `entries[]`（2026-09-21 三次真跑均未回），也无 `operation / created / updated / skipped` 之类字段。
  `render_entries()` 的 `entries[]` 分支属**兼容性保留**（早期实测出现过该字段），现网不保证有。
- **「内容有更新」**：`special_num` 只表示「字节命中既有条目」，**既不代表源端内容变过，也不代表服务端会去更新它**。
  `skip` 档实测证据：源端智能文档某页被加了一段文字 → 重跑 `create` → 目端主条目与 5 个子条目的
  `edited_at` / `source.content_version` **全未变**，该页在目端仍为空。
- **源端版本号 / 修改时间**：企微侧 `doc contents get` 不回 mtime、`smartpage pages get` 不回 mtime；
  只有微盘 `disk files list` 有 `update_time`（它等于 `create_time` 时说明文件从未被改过）。

→ 要「单独列出有更新的文档」，只能在**接口侧**补字段（例如回 `operation: created|updated|skipped`，或回传源端 `version/hash`）。
**不做**客户端自造内容指纹（每次抓全文算 hash）：三类资产抓法各异、正文含图片块时 hash 不稳定，
且会把「抓源端内容」变成 skill 的隐式前置条件（与红线 1 冲突）。

---

## 4. 去重语义（幂等的地基）

**服务端按 `source.href.id` 做「字节级严格比对」去重，且不做任何规范化。**

实测三例（以已存在的 doc 条目为基准）：

| 提交的 `files[].id` | 服务端判定 | 含义 |
|---|---|---|
| `…/doc/w3_AE8…?scode=<scode>`（与既有条目**逐字相同**） | `special_num` | 同一身份 → 去重 ✅ |
| `…/doc/w3_AE8…`（**剥掉 `?scode=`**） | `add_num` | **不同身份 → 会重复** |
| `w3_AE8…`（**裸 docid**） | `add_num` | **不同身份 → 会重复** |

微盘同理：**分享链接 `s?k=…` 与 `file_id` 的归一值不相等**（两者会被判为不同身份）。
→ 因此**同一份微盘资产只固化一种写法**：**分享链接原样提交**即可（2026-09-21 复验：服务端直接接受，
见 `pitfalls.md` §2.2）；老配置里的 `file_id` 可继续用，但**不要与链接混用**。
→ 本 skill **不做**「链接 ↔ ID」互转，也**不预判**哪种形态能用（那是接口的判定）—— 详见
`wecom-sources.md`「为什么这里没有支持性结论」。

🔴 **结论（不可违反）**：脚本绝不改写待提交的 ID 字符串。正确做法 = **客户端归一「匹配」 + 服务端原样「去重」**：
命中既有条目时**回填既有的原始字符串**（服务端字节命中 → 幂等），未命中则用候选**原样**提交。
`norm()` **仅供客户端判等，绝不回传**。

### `content_version`（只透传，不解析）

服务端按 provider 能力写入，**至少两种形态**（实测）：

- `{"mt": <源端 update_time 的 Unix 秒>}` —— smartpage 与微盘文件写入；实测 `{"mt":1787901971}` 与源端 `update_time` `2026-08-28 15:26:11` 精确吻合
- `{"hash": "<sha256>", "v": <版本号>}` —— 智能文档子页面上
- `w3_` 文档类实测为 `None`

→ **脚本不得解析或改写它，只做透传/展示。**

---

## 5. 异步任务时序

```
create → code:0 + task_id        （只证明任务已创建，不代表参数合法）
      → status = page_processing （实测约 12s）
      → status = succeed / failed
        succeed: current_num/total_num = N/N，failed_items 为空
        failed : err_message 泛化文案 + entries[]（成功项）+ failed_items[].failed_reason（失败项明细）
                 ↑ 只要有 1 条失败就整体 failed，「部分成功」不会有独立状态
```

**轮询建议**：3s / 次，上限 60 次（=180s），超时即报 `task_id` 并 `exit 1`，**不要无限轮询**。

---

## 6. `entry_list_children`（扫目标目录既有条目）

### ⚠️ 参数是 `parent_id`，不是 `entry_id`

实测：传 `entry_id` → `code:51`，`validation error: parent_id: value is required [required]`。

```json
{ "jsonrpc": "2.0", "id": 3, "method": "tools/call",
  "params": { "name": "entry_list_children",
              "arguments": { "parent_id": "<目录 entry_id>", "limit": 100 } } }
```

支持参数：`parent_id`（必填）、`limit`、`page_token`、`sort_by`、`_mcp_fields`。

### 响应与分页

```json
{ "code": 0, "data": { "entries": [ … ],
                       "next_page_token": "<next_page_token>",
                       "prev_page_token": "…" } }
```

🔴 **坑：到末页 `next_page_token` 仍会返回**（不是空串）。实测 `limit=100` 取回 10 条并仍带 `next_page_token`；
用该 token 再请求 → 返回 **空 `entries`**。**因此终止条件是「本页为空」，而不是「没有 next_page_token」**，
否则会把末页 token 当有效游标死循环。

### 条目字段（建索引所需）

| 字段 | 用途 |
|---|---|
| `id` | entry_id |
| `created_at` | **Unix 秒字符串** —— 同源重复条目取「最早一条」的排序依据 |
| `source.platform` | `wecombot` 表示这条是企微导入来的 |
| `source.href.id` | ⭐ **去重身份的原文**，归一索引的 key 来源 |
| `source.href.title` | 企微侧标题 |
| `has_children` | 是否有子节点（智能文档根条目通常为 true） |

> ⚠️ 手工创建的条目（如 `[探针D]`、`flink`、`_lexiang_wecom_probe`）**没有 `source` 字段**，
> 建索引时必须跳过（它们不参与企微身份匹配）。


---

## 7. 参数探测方法（接口不在工具目录时怎么拿到参数）

`import_*` 既不在 `tools/list`、`get_tool_schema` 也查不到 → **官方 schema 拿不到**，只能用「非法值探针」反解
（2026-09-21 实做，全部 `dry_run=true`，不写库）：

| 探针 | 做法 | 判据 |
|---|---|---|
| **必填探针** | 逐个删掉参数后调用 | `code=51` **逐条列出所有缺失的必填字段**（成功率最高的一招） |
| **枚举探针** | 给已知字段传非法枚举值 | `code=51` + **吐出合法取值清单**（`conflict_strategy` 的三个取值就是这么反解出来的） |
| **类型探针** | 给候选字段名传类型不符的值 | 字段**存在** → `code=999 系统错误`；字段**不存在** → `code=0`（静默忽略） |
| **分组筛 + 二分** | 一次传一组候选字段名 | 服务端**不支持多字段错误聚合**（6 个字段一起传只回一个笼统 `code=999`），命中组仍需二分定位 |

**适用边界（重要）**

- 只对「**有校验**」的字段有效。存在但接受任意字符串的字段（自由文本类）探针**发现不了** —— 与"不存在"同样回 `code=0`。
- 因此本文参数表的结论是「**已确证的**」，不是「穷举的」。2026-09-21 另用 60+ 个常见候选字段名
  （含 `files[]` 元素级 8 个、`import_describe_task` 5 个）扫过，**均未命中**（7 组分组筛全部 `code=0`）。
- 服务端**不校验未知字段**（多余字段静默忽略）—— 这既是阴性判据，也意味着**配置写错字段名不会报错、只会静默失效**，
  所以不要凭猜写参数。
