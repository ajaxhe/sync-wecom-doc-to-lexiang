---
name: sync-wecom-doc-to-lexiang
description: 把【企业微信 / 企微】知识库资产（在线文档 doc / smartpage / sheet / smartsheet + 微盘文件）批量、增量地【导入】【同步】到【乐享】知识库指定目录。走乐享 MCP 的 import_create_task / import_describe_task 直连服务端导入任务，服务端自己抓正文、图片与文件，Agent 侧无需读正文、无需上传文件。**候选只填源端链接原文、原样粘贴**：在线文档 / 智能文档 / 表格贴完整 URL（含 ?scode=），微盘贴分享链接（`https://drive.weixin.qq.com/s?k=…` 含 ?k=，2026-09-21 实测服务端已直接接受）—— **不要**把链接换成 docid / file_id 等任何 ID。本 skill 的职责只有三件事：**引导配置 → 执行脚本 → 告知结果**（不维护任何中间状态、不追踪目的端增删）。首选 scripts/sync.py 脚本（多 profile 隔离、任务 id 缓存、--debug 日志）；resolve 子命令把乐享目录链接解析成 space_id / entry_id（引导配置用，只读不改配置）；**本 skill 不碰企微侧**（不枚举企微候选、不做 ID 换算、不调用任何企微侧工具）；**使用前提：该乐享企业已在乐享页面完成「授权配置」**（未完成或已过期会让导入失败）。当用户提到企微、企业微信、WeCom、微盘、微盘分享链接、企微知识库、企微文档、乐享、导入、同步、增量导入、批量导入时使用本 skill。profiles/ 含密钥与日志，绝不可提交到代码托管平台。
agent_created: true
---

# sync-wecom-doc-to-lexiang

## 本 skill 干什么 / 不干什么（先读这条，能省掉大半无效工作）

把企微知识库资产**批量**导入乐享指定目录（**仅 Python 标准库**）：扫目标目录 → 一次批量提交 → 轮询终态。
Agent 侧**只做三件事**：① **引导配置**（帮用户把 `config.json` 填对，含首次初始化与后续更新，见「配置引导」）
→ ② **执行脚本** → ③ **告知结果**。

> 与后台「连接器 - 微盘存档」的差异：那条链路对在线文档只能存链接、**不解析正文**；本 skill 走 MCP 导入任务，
> 服务端按 URL 抓正文并转存图片（**正文/图片/文件一律服务端自己抓**，Agent 侧不碰内容），**导入结果可被 RAG 问答**。

**不做的事**（做了就是浪费用户的 token）：

| 不做 | 为什么 |
|---|---|
| 汇报 / 追踪「目的端目录里多了或少了几条」 | 目的端增删是**接口参数** `conflict_strategy` 的职责。源端与目的端的文档都会被编辑删除，**没有"正确条目数"这个概念**，不必盘点、不必对账 |
| 维护本地「已同步清单」/ manifest / 快照 | 增删与去重由接口自行处理，**本 skill 不维护任何本地同步状态**。不要建、不要读、不要修 |
| 替用户决定「该不该覆盖目的端」 | 把「冲突处理策略」表讲清楚让用户选。**默认 `skip`**；Agent 不要自行改成 `replace` |
| 解析 / 改写企微或乐享的 ID | 见红线 1。用户给的标识（在线文档 URL / 微盘分享链接）**原样写进 config 即可**，不改一个字符；**不要**换成 docid / file_id |
| 在报告里复述脚本已打印的原始回包 | 用户要的是**结论**（见「回复模板」）。回包只在**失败排障**时贴，且只贴 `failed_items` |
| 读企微正文 / 下载文件 / 转存图片 | **服务端自己抓**，Agent 侧不碰内容 |
| 查企微侧枚举候选、做任何 ID 换算 | **本 skill 不碰企微侧** —— 不调用任何企微侧工具，避免把「本机装没装某工具」变成隐式前置条件。候选只放**源端链接原文**，链接与 ID 的互转在本链路**不需要** |
| **判断「哪类文档能导入 / 哪种形态不行」** | 🔴 **这是服务端的判定，不是我们的**。脚本**不预判、不按类型拦截**：候选原样提交，**接口的原始信息与错误**（`status` / 计数 / `failed_items[].failed_code` + `failed_reason`）如实返回，由 Agent 组织话术。**禁止**在 skill / 代码 / 提示词里维护「支持类型清单」或「已实测 / 未实测」分档 —— 一次实测只代表当时那次，写进去就变成过期结论 + 多余动作 |
| **为「将来可能出现的新文档类型」改 skill** | 🔴 **绝不需要，也不要预留**。接口将来支持新类型（新路径 / 新 host）时，本 skill **不改一行就能导入** —— 脚本对候选只做「原样提交」，形态表只产出**报告标签**、不命中走通用兜底。理由见红线 9：**用户更新 skill 是不确定行为**，不能把「支持新类型」寄托在升级上。反向也禁止：任何**按文档类型分叉**的硬编码（白名单 / 黑名单 / 类型→参数映射） |
| 研究企微 MCP / uaKey / apikey | 与本链路无关（走的是乐享 MCP） |
| 做本地控制台 / Web 界面 | 超出本 skill 范围 |

**⚠️ 唯一例外**：用户**主动问**「会不会删我东西 / 会不会覆盖」时，必须回答 —— 那是在问配置语义，
照着「冲突处理策略」讲清 `skip` / `replace` / `keep_both` 的差异，并说明**`dry-run` 对该策略是盲的**。

### 红线（违反即制造重复条目或泄露密钥）

1. 🔴 **脚本绝不改写待提交的 ID 字符串** —— 剥 `?scode=`、URL ↔ 裸 docid 互转，服务端判定为**不同身份 → 重复导入**。
2. 🔴 **`norm()` 仅供客户端匹配判等，绝不回传给服务端**。
3. 🔴 **绝不 `scp` / 覆盖 `profiles/*/config.json`**（含个人 MCP Token）；不得把 token 写进 SKILL.md / references / 任何输出。
4. 🔴 **禁止 mock / 占位假数据**：直连真实 MCP 端点；凭证缺失时报明确错误并 `exit 1`，**不降级 mock**。
5. 🔴 **回包 `code:0` ≠ 成功**：`create` 返回 task_id 只代表任务已创建，成败必须轮询 `import_describe_task`。
6. 🔴 **候选只填源端链接原文，不做任何 ID 换算，也不预判它能不能导入**：
   从企微界面复制的**完整链接**（含 `?scode=` / `?k=`）**原样粘贴**即可。
   链接 ↔ docid / file_id 互转、剥离 query 参数，都会被服务端判成**另一个身份**（→ 目的端重复条目）。
   **哪类文档能导入、哪种形态会失败，一律由服务端判定** —— 脚本不判断、不拦截、不改写，
   只把接口回包（含失败项的 `failed_code` / `failed_reason`）**原样**交回给 Agent；
   Agent 照回包讲结论，**不要**自行推测原因或引导用户「换个写法再试」。
7. 🔴 **必须显式下发 `conflict_strategy`（脚本已内置，默认 `skip`），绝不依赖服务端默认** ——
   实测（2026-09-20）：**不传该字段时，一次 `create` 把目标目录原有 10 条条目（含 7 条与本批候选无关的）裁成本次提交的 3 条**。
   另：**`dry-run` 对该策略是盲的**（不传 / replace / skip / keep_both 四路 `dry_run_stats` 实测完全一致），
   所以「dry-run 报零新增」**不能**当成「真跑不会动目的端」的依据。`replace` 会改动/删除目的端既有条目 → **只能在专用导入目录使用**。
8. 🔴 **业务工具走哪条路径由「当前可见 tools」决定 —— 每次先探 `tools/list`，不要写死**（服务端按
   company / feature_flag / allowlist 过滤下发，**后台开关也会改可见集**）。可见 → 直调；不可见但
   `call_tool` 在 → 必须经它包装；`scripts/sync.py` 已**先探再选**并留兜底，**不要绕过脚本直连 MCP**。
   见 `tool is not allowed: <工具名>` = 服务端本次没下发它，**既非凭证过期、也非配置错**（见 `references/import-api.md`）。
9. 🔴 **免升级设计：接口新增文档类型时，本 skill 必须「不改一行」就能导入** —— **用户更新 skill 是不确定
   行为**。⇒ 禁止任何**按文档类型分叉**的硬编码（白名单 / 黑名单 / 形态禁入表 / 类型→参数映射）；`_ID_RULES`
   只产报告标签（不命中有 `_GENERIC_LABEL_RX` 兜底）、`norm()` 只按噪声 query 键归一、`source.type` 读 config，
   三者都**不参与提交决策**。**改完必跑**：临时 profile 塞 3 条没见过的形态 → `dry-run` 须 0 条被拦。详见 `references/wecom-sources.md`。

### 可直接复制的命令块

```bash
cd <skill 目录>
python3 scripts/sync.py list                          # 看有哪些 profile
python3 scripts/sync.py dry-run  --profile default    # 预演（不写库）→ 看 dry_run_stats
python3 scripts/sync.py create   --profile default    # 真实提交（显式下发 conflict_strategy，轮询到终态）
python3 scripts/sync.py create   --profile default --strategy replace  # 临时覆盖策略（replace/keep_both 有风险，慎用）
python3 scripts/sync.py status   --profile default    # 查缓存任务状态 / 失败原因
python3 scripts/sync.py resolve  '<乐享目录链接>'      # 解析目标目录 → space_id / entry_id（只读，不改配置）
python3 scripts/sync.py init     --profile team-a     # 新建一个 profile（定时任务各自隔离）
python3 scripts/sync.py create   --profile team-a --debug   # 出错时加 --debug 落 sync.log
```

候选 id 填什么、形态表怎么查：见下方「config.json 结构」与 `references/wecom-sources.md`。

### 改完必跑什么（改 `scripts/sync.py` 后，提交前逐条实跑）

```bash
python3 -m py_compile scripts/sync.py                      # 语法
python3 scripts/sync.py list                               # 不联网分支
python3 scripts/sync.py dry-run --profile default          # 联网：必须拿到 dry_run_stats
python3 scripts/sync.py create  --profile default          # 真实提交（会写库）
python3 scripts/sync.py status  --profile default          # failed 时必须能打印 failed_items 的 reason
python3 scripts/sync.py resolve '<乐享目录链接>'            # 只读：解析 space_id / entry_id
```

### 同步结果报告（脚本末尾 `── 同步结果 ──` 段）

`create` / `dry-run` 末尾固定输出**三档**，数据**全部取自接口与既有扫描**，脚本不自行判断「文档内容有没有被改过」：

| 档 | 来源 |
|---|---|
| ✅ 新增（`add_num`） | 候选归一后未命中目端既有 `source.href.id` |
| ♻️ 已存在·复用（`special_num`） | 命中既有条目（按既有原始字符串提交 → 幂等复用），报告里带**目端条目名 + 目端链接** |
| ❌ 失败 | 接口 `failed_items[]` 的 `failed_code` / `failed_reason` |

`dry-run` 额外打一行 `接口计数 add_num/special_num`，与本地匹配数**交叉校验**，不等即告警（说明索引口径与接口不一致，要查）。

⚠️ **接口没有「内容有更新」这一维度**：`import_describe_task` 只回 `status / percentage / total_num / current_num`。
要单列「有更新的文档」，得先在**导入接口侧**补字段（如条目级 `operation`，或回传源端版本号），再给 `render_report` 加一档 ——
**不要**在脚本里自造内容指纹去猜（企微文档 / 智能文档 API 都不回 mtime）。详见 `references/import-api.md`「报告能取到什么」。

### 回复模板

✅ **正常完成**（结论优先，3~6 行）：

> 同步完成：3 条候选全部命中既有条目（**✅新增 0 / ♻️已存在·复用 3 / ❌失败 0**），任务 `succeed 3/3`，策略 `skip`。
> - #1 企微文档 · #2 智能文档 · #3 微盘 mp3 均已在目标目录（复用未新建）；task_id `<task_id>`；无需处理。

❌ **反面**：把脚本输出整段抄一遍；或越界汇报「我扫描发现目录里有 3 条 / 之前有 10 条」；或贴 200 行原始回包。

**失败时**才展开，且只给三样：`task_id`、终态、`failed_items[].failed_code` + `failed_reason`；若失败与**授权 / 凭证**有关，附一句「导入的前提是乐享侧授权配置有效」+ 文档链接，其余排查一律不展开。

## 命令

| 命令 | 用途 | 退出码 |
|---|---|---|
| `init [--profile N]` | 生成 profile 配置模板 + `profiles/.gitignore`（已存在则不覆盖） | 0 / 2 |
| `list` | 列出全部 profile 及配置就绪状态 | 0 / 2 |
| `dry-run [--profile N]` | 预演：`dry_run=true`，**不写库**，打印 `dry_run_stats` | 0 / 1 / 2 |
| `create [--profile N] [--no-wait]` | 提交导入任务（轮询到终态） | 0 / 1 / 2 |
| `status [--profile N]` | 查缓存任务状态 / 进度 / 失败原因 | 0 / 1 / 2 |
| `resolve <乐享目录链接或 entry_id>` | **只读**：解析出 `space_id` / `entry_id` / 名称 / 类型，打印可直接粘贴的 `target` 片段。**绝不改配置** | 0 / 1 / 2 |

**退出码**：`0` 成功（含「已有进行中任务 → 静默退出」，供定时任务复用）；`1` 运行期失败（鉴权失效 / **任务 `failed` —— 含服务端判「非法的 'file_id'」等形态问题** / 凭证缺失 / 目录扫描失败 / 网络异常 / 轮询超时）；`2` 用法错误。

**通用开关**：`--profile NAME`（缺省 `default`）、`--debug`（把「时间戳 + 等价 curl（token 打码）+ 请求体 + 原始回包」写入该 profile 的 `sync.log`，不带则不产日志）、`--no-wait`（仅建任务不轮询）。

## 配置引导（Agent 必做，脚本不会代劳）

> 🔴 **脚本在任何命令下都不会改写 `config.json`** —— 只有 `init` 会生成模板，且已存在则不覆盖。
> 配置的建立与更新**由 Agent 编辑文件完成**。这是硬约束：执行期改配置，会让同一条命令产生不同结果。

### 前置：乐享侧「授权配置」（首次初始化必做，且不在本 skill 职责内）

**导入能跑通的前提：该乐享企业已完成「授权配置」。** 这一步在**乐享页面上由用户完成** ——
本 skill **不做授权、不代查授权状态、也不复述文档内容**（文档由乐享官方维护）。

| 时机 | Agent 要做的 |
|---|---|
| **首次初始化** | 主动提示用户先确认这件事（未完成 → 导入必失败），把文档链接给用户 |
| **报错** | 鉴权失败、或鉴权通过但导入任务 `failed` —— 都先给用户这篇文档，再谈其它排查 |

授权配置文档：<https://lexiangla.com/pages/d4a717fbf4604efea4bd286fdcdac31a?company_from=906ba45e6f9a11f089c57a2a2b4bccb6>

> 脚本已在 `init` 与各个失败出口（鉴权失败 / 创建任务失败 / 任务 `failed`，含 `dry-run`）打印该文档地址 —— Agent 不必背链接。

### 要收集的信息（就这 4 项，别多问）

| 信息 | 怎么拿 | 注意 |
|---|---|---|
| ① 乐享**目标目录**链接 | 让用户从乐享页面复制（`https://<租户>.lexiangla.com/pages/<32位id>`） | **只问链接，不要问 `space_id`** —— 用 `resolve` 自动解析 |
| ② 要同步的**企微资产**标识 | 在线文档 / 智能文档 / 表格：从企微界面复制**完整 URL**（含 `?scode=`）；微盘：复制**分享链接**（`https://drive.weixin.qq.com/s?k=…`，含 `?k=`） | 一条一个，**原样粘贴不要手改**（不要换成 docid / file_id） |
| ③ 冲突策略 | 默认 `skip`；只解释差异，不替用户决定 | 目标目录里若还有别的内容，`replace` 会删掉它们 |
| ④ MCP Token | 用户从 `https://lexiangla.com/ai/claw` 取 | 只写进 config：**绝不回显、绝不写进报告** |

### 首次初始化（4 步）

> ⚠️ 动手前先确认「乐享侧授权配置」已完成（见上节）—— 授权未完成 / 已过期时，**配置本身看起来是通的**，
> 问题要到真跑（或任务失败）才暴露，极易被误判成「配置写错了」。

```bash
cd <skill 目录>

# ① 建 profile（生成仅含占位符的模板；已存在则不覆盖。单人自用可直接用 default）
python3 scripts/sync.py init --profile <任务名>

# ② 解析目标目录 → 拿到 space_id / parent_entry_id（只读，不改配置）
python3 scripts/sync.py resolve '<用户给的乐享目录链接>'

# ③ Agent 编辑 profiles/<任务名>/config.json：
#    auth.mcp_token ← 用户给的 token
#    target         ← 上一步打印的那段（含 space_id / parent_entry_id）
#    source.candidates ← 源端链接原文，一条一个 { "id": "…" }（微盘填分享链接，原样）

# ④ 校验配置（不写库）
python3 scripts/sync.py dry-run --profile <任务名>
```

**第 ④ 步必须看到 `dry_run_stats` 才算配置成功**。报错对照见「常见问题速查」。

### 更新配置（最常见的 3 种，只改对应字段）

| 用户说 | 只改哪里 | 改完必须跑 |
|---|---|---|
| 「再加几个文档」 | `source.candidates` **末尾追加**对象 | `dry-run` |
| 「换一个目标目录」 | `target` 整块（先用 `resolve` 重解析） | `dry-run`，**重点看 `add_num`**（换目录后应全是新增） |
| 「改成覆盖 / 别覆盖」 | `source.conflict_strategy` | `dry-run` + **口头告知该档风险** |

🔴 改候选时**只 append、不要动已有条目的字符串** —— 手改一个字符，服务端就当成另一个身份，会重复导入。

## 目录结构

```
scripts/
  sync.py               # 全部子命令的实现（唯一入口）
profiles/
  .gitignore            # 自动生成：忽略本目录全部（防密钥/日志泄露），仅留自身
  default/              # 不带 --profile 时使用：config.json / .task_id.cache / sync.log（--debug）
  <任务名>/             # 每个定时任务一个 profile，互不干扰、无并发冲突
```

## config.json 结构

（简单任务看到这个形状就够了；复杂任务照下面的完整示例一次写对，**别靠反复试错改配置**）

```jsonc
{
  "auth": { "endpoint": "https://mcp.lexiang-app.com/mcp", "mcp_token": "lxmcp_…", "request_timeout": 30 },
  "source": {
    "type": "wecombot",              // 固定值（实测唯一支持）
    "conflict_strategy": "skip",     // 可选；skip（默认，安全）/ replace / keep_both
    "include_subpages": true,        // 可选全局默认；缺省 true。个别候选可在元素上覆盖
    "candidates": [
      { "id": "https://doc.weixin.qq.com/doc/w3_…?scode=…" },
      { "id": "https://doc.weixin.qq.com/smartpage/a1_…?scode=…", "include_subpages": false },
      { "id": "https://drive.weixin.qq.com/s?k=…" }   // 微盘分享链接，原样粘贴（服务端已直接接受）
    ]
  },
  "target": {
    "lexiang_url": "https://<租户>.lexiangla.com/pages/<entry_id>",
    "space_id": "<space_id>",              // 用 scripts/sync.py resolve 得到，不要手填
    "parent_entry_id": "<目标目录 entry_id>"
  }
}
```

> 接口**仅有**下列参数：必填 `space_id` / `type` / `files` / `parent_entry_id`；可选 `dry_run` / `conflict_strategy`；
> `files[]` 元素仅有 `id` / `include_subpages`。**服务端不校验未知字段**（多余字段被静默忽略，不会报错、也不会生效）。
> 完整参数表与探测方法见 `references/import-api.md`。

**候选字段**（**只有 `id` 必填；其余三个都可省略，省略即取默认值**）

- `id`（必填，唯一）：**填用户从企微界面复制到的链接原文**，**原样粘贴、勿手改**（手改一个字符 = 换一个身份 = 重复条目）。形态速查见 `references/wecom-sources.md`。
  - 在线文档 / 智能文档 / 表格 → **完整 URL**（`https://doc.weixin.qq.com/doc/w3_…?scode=…`、`…/smartpage/a1_…?scode=…`），**保留 `?scode=`**；
  - 微盘文件 → **分享链接**（`https://drive.weixin.qq.com/s?k=…`，保留 `?k=`）。2026-09-21 复验：服务端**已直接接受**该形态并以链接本身作为身份，**无需**换成 `file_id`；
  - ⚠️ 裸 `docid`（`w3_…` 等）与裸 `file_id`（`fi…`）**兼容但不推荐**：正常用户从企微界面拿不到，仅在沿用既有固化配置时使用。
- 以下三个**可省略**（日常用不上，省略即取默认值）：
  - `key`（默认 `""`）：**身份覆盖值**。默认空 = 用 `id` 原样提交。仅当候选字符串与既有条目**文字不同、又确信是同一资产**时才填（逃生口）。
  - `include_subpages`（默认取 `source.include_subpages`，后者默认 `true`）：是否连子页一起导入。
    需要全局关掉子页时，在 `source` 下加一行 `"include_subpages": false`。
  - `note`（默认 `""`）：本地备注，**不进请求体**（避免污染 `href.id`）。

**脚本构造的请求体**（不含本地字段，**不传 `files[].name`** —— 服务端以企微实际标题为准）：

```json
{ "space_id": "<target.space_id>", "type": "wecombot",
  "parent_entry_id": "<target.parent_entry_id>",
  "files": [{ "id": "<实际提交的 id 字符串>", "include_subpages": true }],
  "dry_run": false,
  "conflict_strategy": "skip" }
```

## 冲突处理策略（核心）

决定服务端怎么处置目的端：

| 取值 | 含义 | 风险 |
|---|---|---|
| `skip` | 跳过已存在的 | **安全档（默认）**：不改动目的端既有条目 |
| `replace` | 覆盖目的端 | ⚠️ **服务端以本次提交为准替换该目录内容，既有条目会被删除** |
| `keep_both` | 两者都保留 | ⚠️ **会产生重复条目** |

- 配置位置：`source.conflict_strategy`；临时覆盖：`create --strategy <值>`。脚本一律**显式下发**该字段，
  绝不依赖服务端默认（缘由见红线 7 与 `references/pitfalls.md` §2.9）。
- ⚠️ **别拿 `dry-run` 反推安全性**：它对该策略**全盲**（不传 / replace / skip / keep_both 四路 `dry_run_stats` 完全一致），
  「零新增」≠「没动目的端」；也不要拿 `special_num` 反推 —— **命中之后是跳过还是覆盖由参数决定，不由匹配结果决定**。
- ⚠️ `replace` 只能在**专用导入目录**上使用：本 skill 不维护任何本地同步状态，源端与目的端的增删一律**由该参数表达**。

> 与**去重 / 匹配语义**（服务端怎么判重、`norm()` 规则、三层保障）相关的内容属**脚本与接口的内部实现**，
> 不用 Agent 操心；只在排查「为什么重复了」时才读 `references/pitfalls.md` §1 与 `references/import-api.md` §4。
>
> 脚本输出的完整样例（`候选提交保真清单` / `dry_run_stats` / 同源 WARN 行）与两条**实现约束**，
> 见 `references/pitfalls.md` 的「输出样例与实现约束」。

## 常见问题速查

| 现象 | 处理 |
|---|---|
| 仍出现重复条目 | 读 `references/pitfalls.md`。文档类多为「同一资产混用了两种形态」（带 `?scode=` 的 URL / 剥掉 query 的 URL / 裸 docid 三者互不相等） |
| 候选写了微盘分享链接 | **正常形态，直接放行**（2026-09-21 复验服务端已接受，原样提交即可）。**不要**换成 `file_id` —— 那是多余动作，且两者互不相等会造出重复条目 |
| 任务 `failed` 但 `err_message` 只有一句泛化文案 | 真正原因在 `failed_items[].failed_reason`，脚本已逐条打印。**注意失败项不在 `entries[]` 里**，且部分失败 = 整任务 `failed` |
| `dry_run_stats` 出现 `None` | 计数为 0 时服务端不回该字段，脚本已归一成 `0` |
| `create` 跑完**没有** `服务端统计` 一行 | 正常 —— `dry_run_stats` **仅 `dry_run=true` 时才有**（见 `references/import-api.md`），真跑任务不回该字段。定时任务报告里这一项应写「未回传 / 按规则等价 0」，或改用客户端 `候选提交保真清单` 的 `MATCHED→复用既有 / NEW→原样提交` 计数（二者口径不同，别混着说） |
| 鉴权失败 / 401 | 先按 token 处理：`auth.mcp_token` 无效或过期，从 `https://lexiangla.com/ai/claw` 重新获取。**换 token 后仍失败** → 是乐享侧「授权配置」未完成或已过期，把授权文档给用户（见「配置引导」前置节） |
| 导入任务 `failed`，原因指向**授权**（未完成 / 已过期） | **不要改 config、不要换 token、不要改候选** —— 这是乐享侧的授权问题，不是本 skill 的参数问题。把授权文档给用户，由其在乐享页面完成授权后重跑 |
| 报 `tool is not allowed: xxx` | **不要改 config、不要换 token、也不要改脚本里的路径** —— 只说明服务端本次下发（`tools/list`）里没有它（后台开关 / allowlist 都会导致），脚本会自动改走 `call_tool` 包装。判凭证是否有效只需直调一次 `whoami`（成功即有效）。想让直调恢复是要**乐享侧放回 + 客户端重启**，本地别绕 |
| 目录扫描失败 | 脚本**主动中止**、不提交任何任务 —— 这是有意的：跳过匹配强行提交会制造重复 |
| 候选 ID 形态报错 | **照实提交、照实回传**：脚本不做形态判断，服务端回什么就报什么（含 `failed_items[].failed_reason` 原文）。**不要**改写形态、换算 ID，也不要写「换个写法就能过」—— 能不能导入由服务端判定 |

## references

| 文件 | 内容 | 什么时候读 |
|---|---|---|
| `references/import-api.md` | **接口参数全表**（4 必填 + 2 可选 + `files[]` 元素字段 + 校验行为 + 非法值探测方法）、**MCP 调用路径（按可见 tools 选路，2026-09-21 实测）**、去重语义、`dry_run_stats`、异步时序、四条实测口径（`err_message` / `failed_items` / 部分失败 / 计数为 0 不回字段）、**⭐ 报告能取到什么（哪些维度接口没有）**、`entry_list_children` 分页 | 要改接口调用时 / 要动报告字段时 |
| `references/wecom-sources.md` | 企微侧**链接形态速查**（形态 ↔ 示例，**不含支持性结论**）、**候选清单托管在企微文档里时的抽取**（原样抽链接、不做 ID 换算）、同一资产只固化一种写法、**⭐ 接口新增文档类型时的「免升级设计」与验证方法** | 要确认「粘贴什么最稳妥」/ 候选来自一篇企微清单文档 / 要加形态相关代码前 |
| `references/pitfalls.md` | 红线 + 已知限制（含索引只扫一层）+ **输出样例与实现约束** + 实测现场记录（含「把支持性判断写进 skill」的反面案例 §2.4） | 动 `norm()` 或索引逻辑前**必读**；排查「为什么重复了 / 为什么没匹配上 / 为什么任务 failed」 |
