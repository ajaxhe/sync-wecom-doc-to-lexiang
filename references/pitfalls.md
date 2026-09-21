# 红线与已知限制

> 动 `norm()`、索引逻辑、或任何「改写 ID 字符串」的念头之前，**必读本文**。

---

## 一、红线（违反即制造重复条目或泄露密钥）

### 🔴 1. 绝不改写待提交的 ID 字符串

剥 `?scode=`、URL ↔ 裸 docid 互转、`file_id` ↔ 分享链接互转 —— 服务端按 `source.href.id`
**字节级严格比对**去重且**不做任何规范化**，改写 = 造出一个**新身份** = **重复条目**。

实测三例（同一份 doc）：

| 提交形态 | 服务端判定 |
|---|---|
| 与既有条目逐字相同（含 `?scode=`） | 去重（`special`） |
| 剥掉 `?scode=` | **新增**（`add_num`） |
| 裸 docid `w3_…` | **新增**（`add_num`） |

→ 唯一允许的「替换」是**回填既有的原始字符串**（为了触发字节命中），**不是**把字符串规范化后提交。

> 澄清：微盘分享链接的正确处理**也不是「改写」** —— 服务端根本不接受它（§2.2）。
> 正确路径 = **先把它换成 `file_id`，再以 `file_id` 提交**。`file_id` 是服务端认的**唯一身份**，
> 且它本身参与归一匹配（命中既有即回填既有原串）。
> 🔴 **换算发生在哪里**（2026-09-21 边界重划）：**不在本 skill 内** —— 由 Agent 在**对话中**完成，
> 拿到 `file_id` 后写进 config。脚本只接受服务端直接认的形态，遇到分享链接**直接拒收**（`exit 1`）。

### 🔴 2. `norm()` 仅供客户端匹配判等，绝不回传给服务端

回传 `norm()` 的值 = 造新身份 = 重复。

`norm()` 规则（**仅供客户端判等**）：去首尾空白 → 剥 `?…` query → **保留** `#page=<pageId>` fragment
（子页身份锚点，剥了会错配）→ 微盘 `s?k=<k>` **保留 `k`** → host 小写（path/id 大小写不改写）。

### 🔴 3. 不覆盖 `profiles/*/config.json`

文件内含**个人 MCP Token**。禁止 `scp` 覆盖、禁止进任何代码/skill 托管平台
（`profiles/.gitignore` 已忽略整目录，仅留自身）。分享 skill 时整体剔除 `profiles/`。

### 🔴 4. 禁止 mock / 占位假数据

直连真实 MCP 端点（**只连乐享侧**）。凭证缺失 / 未填模板时报**明确错误**并 `exit 1`，**不降级 mock**。

### 🔴 5. `create` 返回 `code:0` ≠ 成功

只代表任务已创建，参数校验在执行阶段。**必须**轮询 `import_describe_task`。

### 🔴 6. 目录扫描失败 → 主动中止，不「跳过匹配强行提交」

`entry_list_children` 失败时若继续提交，就失去了唯一能防重复的能力。
脚本设计为打印明确错误并 `exit 1`，**这是有意的**，不要为了「让它跑起来」而加 fallback 空索引。

---

## 二、已知限制

### 2.1 索引只扫目标目录**一层** → 子页做候选时可能重复

`entry_list_children(parent_id)` 只返回**直接子条目**。而 `include_subpages=true` 时，
智能文档的**子页落在「文档条目之下」（第二层）**，`source.href.id` 形态为
`…/smartpage/a1_xxx#page=<pageId>`，**不在目标目录下**。

**后果**：若直接把**子页 URL（含 `#page=`）**当候选提交，归一索引匹配不到 → 判 `NEW` → **可能重复**。

**当前决策：不改递归扫描。** 理由：递归会显著放大请求量与耗时，而根条目 URL 已在索引里，
正常的用法是维护「根文档候选」而非逐个子页。**这是有意接受的限制**，请在使用侧遵守。

> 若确有「只导某个子页」的需求，让主理人先裁决是否引入递归扫描，不要自行加。

### 2.2 微盘：分享链接**服务端不接受**，必须**先换成 `file_id`**（本 skill 不代换）

| 提交形态 | 服务端 |
|---|---|
| `file_id`（`fi…`） | 命中既有 → 去重 ✅（实测 `special_num`） |
| 分享链接（`s?k=…`）**原样**提交 | ❌ **任务 failed（`import_failed` / 非法的 'file_id'）** |
| 分享链接**换成** `file_id` 后提交 | ✅ 与直接填 `file_id` 等价（同一身份） |

**实测案例**：候选 `https://drive.weixin.qq.com/s?k=<share_key>` 与目标目录既有条目
`<entry_id_A>`（`source.href.id = fi…`，109 字符）
是**同一份 mp3**。分享链接**原样**提交 → 服务端判 `import_failed / 非法的 'file_id'`（见 §2.3）。

> **技术旁注（仍成立）**：`norm()` 故意**保留 `s?k=` 的 `k`**（它才是分享链接的身份本体），
> 所以分享链接的**归一值与 `file_id` 的归一值不相等**。→ 转换必须发生在**提交之前**，
> 拿分享链接直接去索引里找是永远找不到的。

**✅ 正确做法（2026-09-21 起）：先把分享链接换成 `file_id`，再把 `file_id` 写进 config**

```jsonc
// profiles/<name>/config.json —— 候选**只需一个 id 字段**
{ "candidates": [
    { "id": "fi…GRy6xdRBeJU" }   // ✅ 由分享链接换来的 file_id
] }
```

换法是**对话内动作**（Agent 引导用户，用企微侧只读查询通道取回 `file.id`），做法见
`wecom-sources.md` §2。**不要把这一步搬进 `scripts/sync.py`** —— 那会让 skill 多出一个隐式前置依赖。

实测结果（候选 #3 用换来的 `file_id` 提交）：`MATCHED→复用既有`，
服务端 `special_num=3 / add_num=0`，**目标目录零新增**。

> ⚠️ **脚本遇到分享链接的现行行为**：`build_plan()` 经 `REJECTED_KINDS` 直接拒收 →
> 打印「本 skill 不做 ID 换算」+ 换法指引、`exit 1`、**不发出导入请求**
> （仍会先发 `entry_list_children` 读请求用于建索引）。**绝不猜测、绝不代跑、绝不降级**提交分享链接。

> ⚠️ **分寸（别拿它当「导入成功」样板）**：`MATCHED→复用既有` 只说明**该身份被服务端接受、并命中了既有条目**，
> 不代表那条乐享条目本身是成功态。实测既有条目 `<entry_id_A>` 的
> `status = {"status": "failed", "failed_reason": "video_content_empty"}` —— 身份命中，但资产内容导入失败。
> **交付 / 验收时不要用 `MATCHED` 反推「导入成功」**；要看乐享条目自身的 `status`。

> **`key` 字段现在只是「极少数场景」的逃生口**（既有条目原文与手头字符串文字不同、又确信同一资产）。
> `key` 是**用户显式指令**，不是脚本改写 ID —— 与红线 1 不冲突。

> **换算职责的三次变迁（存档）**：
> ① A1 时期 —— 要求用户先手工换算、把 `file_id` 固化进 config，脚本拦下分享链接并 `exit 1`；
> ② 2026-09-20 —— 改为**脚本自动换算**（当时理由是「正常用户拿不到 `file_id`」）；
> ③ **2026-09-21（现行，用户裁决）** —— 换算**移出 skill**，改由 Agent 在**对话中**完成：
>    skill 不碰企微侧，避免把「本机是否装了某企微工具」变成隐式前置条件。
> **因此 ①② 的表述均属过期文案**，文档别处若还有「脚本会自动换算 / config 里直接填分享链接」，一律按 ③ 修正。

### 2.3 §2.2 的实测证据（任务 failed 原文）

实测提交 `https://drive.weixin.qq.com/s?k=…` → 任务 `failed`：

```json
{ "failed_code": "import_failed",
  "failed_reason": "非法的 'file_id', 请重新检查'file_id'的值是否正确: https://drive.weixin.qq.com/s?k=…" }
```

需求摘要 §2.2 最初记为「微盘分享链接 ✅ succeed」，**已按本次实测改正**为「服务端不接受，必须先换 `file_id`」
（owner：team-lead）。`wecom-sources.md` 与本文均已同步，**不存在「两种形态都行」的说法**。

`dry-run` **不会**暴露这个问题（dry-run 只统计身份新旧，不校验 ID 合法性），所以别只看 dry-run 就交付。

### 2.4 `sheet` / `smartsheet` **未实测**（含新增的 docid 前缀）

- `/sheet/` 与 `/smartsheet/` 的 URL 形态**按同一 provider 路径推断放行**（脚本打印
  「按同一 provider 路径推断，未实测」），但**未实测过**。
- 裸 docid 的前缀，需求摘要点名的是 `w3_` / `a1_` / `b1_`；实跑发现还有 `e3_` `s3_` `d3_` `p3_` `f4_`（早前另记有 `m4_` `c2_`，**本轮未复现**）。
  脚本对这些**放行但不认作已验证**（同样打印未实测提示）—— 放行的目的是别把用户合法粘贴的 docid 误判成「形态非法」。
- ⚠️ **2026-09-21 复核修正**：前缀与类型的对应关系早前记错过 —— `s3_` 是 **smartsheet**（不是 sheet）、
  `e3_` 才是 **sheet**、`d3_` 是 **pdf**（不是「表格类」）。对照依据：把枚举项的 `docid` 前缀与 `type` 字段逐条对照。
  完整对照表见 `wecom-sources.md` §「`docid` 的前缀远不止 `w3_` / `a1_` / `b1_`」。

**不要把推断写成事实。** 若要转正，需补一次真实 `create` 验证。

📋 **待验证清单（当前三类挂账项，team-lead 2026-09-20 裁决：不转正、保持标注）**

| 待验证形态 | 现状 | 转正需要什么 |
|---|---|---|
| （a）`/sheet/` URL、`/smartsheet/` URL、`w3_`/`a1_`/`b1_` 之外的裸 docid 前缀（`e3_` `s3_` `d3_` `p3_` `f4_`；`m4_`/`c2_` 本轮未复现） | 本地**放行**、`render_plan()` 打印「按同一 provider 路径推断，未实测」 | **一个真实的 sheet / smartsheet 链接 + 一次真实 `create`**。注意代价：会往目标目录写入条目，写入需 owner 同意。✅ **测试对象已就绪（2026-09-21）**：已由 Agent 在对话中经企微侧枚举产出覆盖各形态的测试候选清单（doc / smartpage / **sheet `e3_`** / **smartsheet `s3_`** / 微盘 `file_id`），不必再等「拿到测试对象」 |
| （b）**不在提交白名单**的 5 类 `doc_url` 前缀（`/forms/` `/flowchart/` `/mind/` `/pdf/` `/slide/`） | 枚举侧**跳过并计数**（比照 `folder`），不产出候选、不可提交 → **覆盖缺口（`list` 路径）：94 条枚举 → 84 条可提交，10 条挂账**（实测：`/forms/`×5 `/flowchart/`×2 `/mind/`×1 `/pdf/`×1 `/slide/`×1）。📦 枚举能力已于 2026-09-21 移出本 skill | 补 `classify_id()` 白名单 + 一次真实 `create` 实测（写入需 owner 同意） |
| （c）枚举返回的 `type=folder` 节点（`list` 路径**不返回** folder；`search` 返回，实测 `search 产品 limit=100` 有 29 个） | 枚举侧跳过并计数（`type=folder`）。**两条枚举路径覆盖面是否相同 —— 未验证**：`search` 是否覆盖到 `list` 漏掉的内容、folder 内是否含可导入文档、其叶子是否会在结果中单独出现，**均未验证** | 取同一空间分别跑 `list` 与 `search` 两条路径并比对全集（含 folder 下钻），确认无遗漏、或明确写下遗漏边界 |

> **各处标注须措辞一致**（改一处必须同步其余各处）。当前实际文案：
> ① `scripts/sync.py` `_ID_RULES` 表的 label 列 →「企微在线表格 URL（/sheet/）」「企微智能表格 URL（/smartsheet/）」
> 「裸 docid（w3_/a1_/b1_ 之外的前缀：e3_ / s3_ / d3_ 等）」，且 `tested=False`；上方 `UNVERIFIED_KINDS = {"wecom_sheet_url","wecom_smartsheet_url","wecom_bare_id_other"}` 带注释说明「必须显式提示，不能把推断当事实」。
> ② `wecom-sources.md` §1 形态表 →「⚠️ **未实测**（按同一 provider 路径推断）」。
> ③ `scripts/sync.py` `render_plan()` 打印给用户 →「形态 `<label>`：按同一 provider 路径推断，未实测」（`label` 取自 `build_plan()` 放进 plan 的人话标签，非 `kind` 机器键）。
> ④ （**已移除**）`_collect_from_items()` 曾在枚举产出候选时追加同样的未实测提示 —— 该函数随 `collect` 子命令于 2026-09-21 移除。
>    现在只在 ③ 处打印一次（枚举侧若由 Agent 在对话中完成，需由 Agent 自己把「未实测」讲清楚）。

### 2.5 顶层 `err_message` 是泛化文案，明细在 `failed_items[]`

`err_message` 实测恒为「导入失败，请查看失败文档」，**没有排障价值**。
真正原因在 `data.failed_items[].failed_reason`（含原始报错与 `callid`）。
脚本必须打印 `failed_items`，否则用户无从下手。

### 2.6 部分失败会用整任务的 `failed` 表达

实测 3 条候选里 2 条命中既有（等价成功）、1 条失败 → 整任务 `status=failed`。
**所以 `failed` ≠ 全军覆没**，要看 `failed_items` 条数与 `total_num`。
退出码仍按方案给 `exit 1`，但文案里带「总计 N 条，其中 M 条未成功」。

### 2.7 （📦 历史）`collect` 产出必须 ⊆ 提交白名单（P1：曾两侧不同步导致断链，已修复）

> 📦 **本节所述的 `collect` 子命令与 `_collect_from_items()` 已于 2026-09-21 随边界重划移除**
> （本 skill 不再碰企微侧）。**教训对任何「枚举 → 提交」两段式流程仍然成立**，故保留存档；
> 文中的函数名 / 子命令现已不存在。

**根因**：`collect` 的 `doc_url` 分支**曾**不调用 `classify_id`，把枚举到的 `doc_url` 无条件原样输出；
而提交白名单 `_ID_RULES` 只认 `/doc/` `/smartpage/` `/sheet/` `/smartsheet/` + 微盘形态。
**两侧名单不同步**时，`collect` 会产出「提交阶段必被拒」的形态 → 用户「collect → 粘贴 → create」**断链**：
`build_plan()` 判 `kind is None` → `_prepare()` 整批 `exit 1`，**整批硬失败**。

**修法（两部分）**：
1. `collect` 的 `doc_url` 分支改为**先过 `classify_id`**：形态不在白名单、或落在 `REJECTED_KINDS` 的
   **跳过并计数**（比照 `folder`），末尾打印一行注释告知「资产存在但暂不支持」，**不静默丢弃**。
   **不补白名单** —— 那几类前缀零实测证据，补进去等于无实测地扩大提交面、并改变 `create` 行为
   （原 `exit 1` 的会变成真提交），爆炸半径太大。
2. **结构性护栏（根因修复）**：`_collect_from_items()` 返回前对每条候选断言 `classify_id(id)[0]` 非 None
   且不在 `REJECTED_KINDS`，违反即 `raise`。→ 「collect 产出 ⊆ 提交白名单」成为**代码级不变量**，
   不再依赖人工同步这两个列表。

> **护栏是「纵深防御不变量」**：它在正常流程中**总是执行**（对 `out` 每条迭代），喂入非法候选时**确实会 `raise`**；
> 但**当前真实数据路径下不可达** —— 上游各分支（`doc_url` 先过 `classify_id`；`file_id` 分支判 `kind is None` 即跳过）
> 加 `_disk_get()` 自带的形态校验（见 `scripts/sync.py`）已排除非法形态。其价值在**防未来回归**
> （有人放宽分支条件、或改动 `_disk_get()` 校验时兜住）。
> ⚠️ **不要把「合成复现」写成「真实可达」**：曾用 monkeypatch 造出合成路径证明它会触发，那**只能**证明「喂入非法候选时会 raise」，
> **不能**证明「真实数据能走到这里」。真实路径已由上述上游校验堵死。

**实测（`collect --limit 100`，94 条）**：跳过 10 条（`/forms/×5 /flowchart/×2 /mind/×1 /pdf/×1 /slide/×1`），
输出 84 条候选**全部**通过 `classify_id`、无一在 `REJECTED_KINDS`。跳过清单见 `wecom-sources.md` §1。

### 2.8 （📦 历史）`collect` 不得因单个不可识别条目作废整批（P1：`space` 节点曾致 `exit 1`，已修复）

> 📦 **本节所述 `collect` 已移除**（同 §2.7）。**「不认识就跳过并计数、而不是 raise」这条判据仍然成立**，
> 对现在由 Agent 在对话中做的枚举同样适用。

**根因**：`disk files search` 的结果里混入 `space`（空间）节点 —— `id` 前缀 `sp`、长 66 字符、**无 `doc_url`**、`type` 也非 `folder`。
它落进 `_collect_from_items()` 的 `file_id` 分支 → `classify_id('sp…')` 返 `None` → **`raise`** → **整批 collect 中断、`exit 1`、零候选**。
（预先存在的 bug，被本轮首次实跑 `collect --search` 暴露。）

**证据（实跑微盘搜索的原始 `type` 分布）**：

| 关键词 | items | `type` 分布 |
|---|---|---|
| 产品 | 10 | `{space:8, file:2}` |
| 乐享 | 10 | `{space:8, collect:1, smartsheet:1}` |
| 标准录音 | 1 | `{file:1}` |

**修法（类型无关的结构化规则）**：
1. `file_id` 分支的「`kind is None` → `raise`」改为**跳过并计数**；
2. 「既无 `doc_url` 也无 `id`/`url`」的 `raise` 同样改为**跳过并计数**（同一类问题）；
3. 跳过台账（folder / 不在白名单的 `doc_url` 形态 / 不可识别节点）**合并为一行注释**，不可识别节点**带 `type` 标签**便于排查；
   注释**前缀中性**（陈述「已跳过」事实），**尾注按实际桶类型自适应**（`；` 连接子句：含 `type=` 桶 → `type= 为非文件/容器节点`；含 `/` 桶 → `其中 <桶> 形态未实测，如需导入请先补 classify_id 白名单并实测验证`；都无则不打印括号）。

> **为什么不写 `type` 名单**（本次关键判断）：4 个关键词就出现 **5 种** `type`（`folder`/`space`/`collect`/`smartsheet`/`file`），
> 任何硬编码黑/白名单都会被下一个新类型打破 —— **那正是本次 bug 的同一失败模式**。故走**类型无关**规则：
> 「不认识 → 跳过并计数」，而非「列举要跳过的类型」。

> **保留 fatal 的路径（有意选择，📦 现已随 `collect` 移除）**：当时的 `_disk_get()` 换算失败仍 `raise` ——
> 那是**另一类失败**（网络 / 鉴权 / 子进程）。**不要把「数据里出现不认识的东西」和「我们自己的调用失败」混为一谈**：
> 前者跳过并计数，后者必须显式报错。

### 2.9 🔴 `conflict_strategy` 未传 → 目标目录内容被替换（2026-09-20 实测事故）

**现象**：一次 `create`（3 条候选，全部 `MATCHED→复用既有`）执行后，目标目录从 **10 条变 3 条**：
本次提交的 3 条被**重建为新条目**（新 `entry_id`、`created_at` = 任务执行时刻），
其余 **7 条与本批候选完全无关**的条目（`SaaS-获取用户身份访问凭证` / `wb+乐享视频demo` /
`[探针D] Agent导入链路测试` / `从一份公开情报…` / `_lexiang_wecom_probe` 等）**一并消失**
（抽查旧 `entry_id` 全部回 `code:71 不存在`）。

| 观测点 | 实测结果 |
|---|---|
| 任务 `status` | `succeed`、`3/3`、`exit 0` —— **全程无任何删除提示** |
| 跑前 `dry_run_stats` | `add_num=0, special_num=3` —— **「零新增」完全没预警** |
| 目标目录 entry 自身 | `created_at` / `edited_at` 均为**旧值** → 目录没被重建，是**目录内条目被清** |
| 事后追溯 | `import_describe_task` 回包**不含** `conflict_strategy` → **无法反查**当时用的策略 |

**根因**：`import_create_task` 有 `conflict_strategy` 参数（合法取值 `replace` / `skip` / `keep_both`，
服务端校验器原文吐出）。**不传时服务端默认行为 = 把目标目录内容替换成本次提交的集合**。
脚本当时**未显式下发**该字段。

**两条致命认知（已写进 SKILL.md 红线 7）**：
1. **`dry-run` 对该策略是盲的** —— 不传 / `replace` / `skip` / `keep_both` 四路 `dry_run_stats` 实测**完全一致**。
   → **「dry-run 报零新增」绝不能当作「真跑不会动目的端」的依据。**
2. **`special_num` ≠ 安全** —— 命中之后是「跳过」还是「覆盖」，由 `conflict_strategy` 决定，**不由匹配结果决定**。

**附带发现（去重索引有延迟）**：同一批候选，事故后 4 分钟内 `dry_run_stats` 从
`add_num=2, special_num=1` 变为 `add_num=0, special_num=3`（新建条目要过几分钟才进入服务端去重索引）。
→ **不要用短间隔的两次 dry-run 差异下结论。**

**修法**：`scripts/sync.py` 一律**显式下发** `conflict_strategy`（默认 `skip`）；配置项 `source.conflict_strategy`；
CLI 可 `create --strategy <值>` 覆盖；`create` / `dry-run` 打印策略，非安全档额外告警。

**⚠️ 未验证（诚实标注，勿当结论用）**：三档的**精确边界**尚未逐一实测 —— 尤其
(a) `replace` 的删除范围是否严格限于 `parent_entry_id` 内；
(b) `skip` 是否**绝对**不触碰目的端既有条目；
(c) `keep_both` 的重复形态（同条目重复 / 新旧各一条）。
下一步应在**专用测试目录**上做对照实验。**注意：当前 MCP 无「删除条目」接口**，
实验产物**无法用 API 清理**，需人工删 —— 这也是本轮未擅自开展该实验的原因。

### 2.10 调用路径取决于「当前可见 tools」—— 我把它误判成了「平台禁止直调」（2026-09-21）

**现象**：2026-09-21 上午，`scripts/sync.py` 的**所有联网命令突然 `exit 1`**：

- `dry-run` → 「读取目标目录既有条目失败：调用乐享 MCP 失败：content 不是合法 JSON」
- 直调任何业务工具（`entry_list_children` / `import_create_task` / `import_describe_task`）→
  纯文本 `tool is not allowed: <工具名>`

**真实规则**（官方 resource `lexiang://docs/instructions/v1`「工具调用方式」原文）：可见工具清单由 MCP 服务按
**company / feature_flag / allowlist** 动态过滤 —— **在清单里就直接调，不在清单里但 `call_tool` 在就必须经它包装**。
所以同一份代码在不同账号 / 环境下走不同路径：**这不是平台的固定规则，更不是"服务端行为变更"**。

**❌ 我犯的归纳错误（本会话内被用户纠正）**：我把「**本 token** 的可见清单里没有业务工具」写成了
「乐享 MCP **已禁止**直调业务工具」，并据此断言「服务端行为变更」。
用户找乐享团队确认「直调是可以的」之后，我才回去读官方说明原文，发现它写的是**条件规则**、不是禁令。

> **教训：判定「平台禁止 X」之前，必须拿到官方原文里的规则句，而不是只凭自己的复现结果。**
> 「我这边复现了」只能证明**当前上下文**如此，不能证明**平台规则**如此。
> 复现结果 + 官方原文，两个都要；只有前者就是过度归纳。

**修法**：`mcp_call()` 按官方规则**先查可见 tools 再选路径** —— `_visible_tools()` 进程内缓存一次
`tools/list`：
- 业务工具在可见清单里 → **直调**；不在 → 经 `call_tool` **包装**。
- 另一条路径留作兜底（探测失败、或服务端反馈与可见清单不一致时），**只在路径本身被拒时**才切换；
  判定集中在 `_path_rejected()`（形如 `<marker>: <名字>` 且名字与我们**实际调用**的工具一致），
  以区分「路径不通」（可切换）与「工具被禁 / 不存在」（切换无意义，不做无谓重试）。

**三条诊断教训（跨项目通用）**

1. **错误信息必须保真**：原脚本在 `content[0].text` 非 JSON 时只报「content 不是合法 JSON」，
   把服务端给出的关键线索（`tool is not allowed: xxx`）**吞掉了**。已改为把原文带进错误信息。
   排查时「笼统的解析失败」几乎总是掩盖了真因。
2. **服务端在报"工具不允许 / 工具不存在"时回的是纯文本，不是 JSON** —— 见到「content 不是合法 JSON」先怀疑这一类，
   而不是先怀疑编码 / 网络。
3. **「凭证问题」与「可见性 / 权限问题」用一条命令就能分开：直调 `whoami`。**
   成功 = token 有效 → 那么「只拒业务工具、包装就通」这种**选择性**拒绝绝不可能是凭证问题。
   用户第一反应是「是不是凭证过期了」，这类误判用 `whoami` 一步就能排除。

**验证**：`dry-run --debug` 日志可见 —— `tools/list 可见工具 7 个` →
`--- 路径选择 --- entry_list_children：可见=否（已探测）→ 先走 wrapped` → `exit 0`、
目录 3 条全 `MATCHED`、`add_num=0`；且**不再产生任何"试错式"的失败请求**（路径在发请求前就定好了）。

> 关联：本节是**调用层**的可见性问题；`conflict_strategy`（§2.9）是**语义层**的风险，两者独立，都要守。

## 三、接口侧踩坑备忘

| 坑 | 现象 | 处理 |
|---|---|---|
| `entry_list_children` 参数名 | 传 `entry_id` → `code:51 validation error: parent_id: value is required` | 用 **`parent_id`** |
| 末页仍返回 `next_page_token` | `limit=100` 取回 10 条仍带 token；用该 token 再请求返回**空数组** | 终止条件 = **本页为空**，不是「没有 token」，否则死循环 |
| 手工创建的条目无 `source` | 建索引时读到 `None` | 跳过没有 `source.href.id` 的条目 |
| `failed_items` ≠ `entries` | 失败项**不在** `entries[]` 里 | 两个数组都要渲染 |
| `dry_run_stats` 计数为 0 时不回字段 | 实测 `add_num=None, special_num=3`；反例 `add_num=2, special_num=None` | `None` **等价 0**，展示前归一 |
| `disk files list` 混着两类资产 | 文档类带 `doc_url`、纯文件类不带；`id` 一律是 `fi…` | 有 `doc_url` 提交 `doc_url`，否则提交 `file_id`；`folder` 跳过 |
| `content_version` 多形态 | `{"mt":…}` / `{"hash":…,"v":…}` / `None` | **只透传，不解析不改写** |
| 企微侧回包 `extra_identity_context` | 回包含内部身份说明 | 输出前剔除，不外泄 |
| stdout 被管道接走时顺序错乱 | stderr 错误文案跑到 stdout 前面 | `sys.stdout.reconfigure(line_buffering=True)` |

---

## 四、实测现场记录（2026-09-20，目标目录 `<target_entry_id>`）

**目录里真实存在一对同源重复条目**（这正是索引必须处理键冲突的原因）：

| entry_id | created_at | `source.href.id` |
|---|---|---|
| `<entry_id_B>` | 1789446554（早） | `…/smartpage/<smartpage_id>?scode=<scode>` |
| `<entry_id_C>` | 1789901234（晚） | `…/smartpage/<smartpage_id>`（**剥掉了 query**） |

两者归一后键相同 → `{norm: 原始}` 会互相覆盖。**取 `created_at` 最早的一条**
（`<entry_id_B>`，恰好是带完整 `?scode=` 的原始形态），并打印：

```
WARN: 目标目录存在 2 条同源条目（entry_id: <entry_id_B> (created_at=1789446554), <entry_id_C> (created_at=1789901234)），
      归一索引取最早一条 <entry_id_B>
```

**为什么取「最早」**：稳定、可预测 —— 只要最早那条还在，索引值就不变，重复跑结果一致；
且它恰好最贴近用户第一手粘贴的完整字符串。

### 幂等实测结果

| 轮次 | 结果 |
|---|---|
| 第 1 次 `create`（default，3 候选，A1 之前） | `#1 MATCHED` / `#2 MATCHED` / `#3 NEW→失败(非法的 file_id)`；**目录 10 → 10** |
| `probe-x` `create`（`key` 覆盖，1 候选，A1 之前） | `MATCHED` → `succeed 1/1`；**目录仍 10** |
| 第 2 次 `create`（default，重复触发，A1 之前） | 同上；**目录仍 10** |
| **A1 之后** `dry-run`（default，候选 #3 改为 `file_id`） | **`#1 / #2 / #3 全 MATCHED→复用既有`**；`add_num=0, special_num=3`（服务端口径一致） |
| **A1 之后** `create`（default） | `succeed 3/3`，`exit 0`；**目录 10 → 10，零新增、零重复** |

→ 累计多次真实提交后目标目录仍是 **10 条**（其中 3 条是手工创建、无 `source`，不参与匹配）。
客户端预测与 `dry_run_stats` 逐条吻合。

### 候选形态的本地拦截实测（含 2026-09-21 边界变更）

| 场景 | 结果 |
|---|---|
| 候选 = 微盘分享链接 → `dry-run` / `create`（2026-09-20 的旧行为） | 本地打印换算指引、`exit 1`，**未发出导入请求** |
| 候选 = 微盘分享链接 → `dry-run` / `create`（2026-09-20 那段时期） | **自动换算**成 `file_id` 后提交；保真清单打印「输入链接 → 换算出的 file_id」；实测 `add_num=0, special_num=3`、**目标目录零新增**、`exit 0` |
| 候选 = 微盘分享链接 → `dry-run` / `create`（**2026-09-21 起，现行**） | 经 `REJECTED_KINDS` **直接拒收**：打印「本 skill 不做 ID 换算」+ 换法指引、`exit 1`、**未发出导入请求**（`.task_id.cache` 不更新）。**绝不猜测、绝不代跑、绝不降级**成提交分享链接 |
| 配置里的 `file_id`（由分享链接换来） | 与既有条目 `href.id` **逐字节一致** → `MATCHED→复用既有`、`exit 0` |
| `collect --url` / `--limit` / `--search` | 📦 已随 `collect` 子命令移除（2026-09-21）。历史行为见下方存档 |
| `--debug` 日志（25.6 KB） | 明文 token 出现 **0 次**，curl 里只有打码形式（形如 `lxmcp_xxxx***yyyy`，中段以 `***` 遮盖） |

### 📦 `collect --search` 关键词矩阵实测（2026-09-20，FIX-1 前后对比；`collect` 已移除，本节为存档）

| 关键词 | 原始 `type` 分布 | 修复前 | 修复后 |
|---|---|---|---|
| `产品` | `{space:8, file:2}` | ❌ `exit 1`、零候选 | ✅ `exit 0`；跳过 8（`type=space×8`）+ 出 2 条 `file_id` |
| `乐享` | `{space:8, collect:1, smartsheet:1}` | ❌ `exit 1`、零候选 | ✅ `exit 0`；跳过 9（`type=space×8 /forms/×1`）+ 出 1 条 `smartsheet`（带「未实测」） |
| `标准录音` | `{file:1}` | ✅ 正常 | ✅ 正常（1 条 `file_id`） |
| `zzz-不存在-zzz` | `{}` | ✅ `[]` | ✅ `[]`、`exit 0`（回归） |

> `collect` 型条目的 `doc_url` 落在 `/forms/` 前缀 → 归入「不在提交白名单」桶。
> 实测跳过注释原文（`--search 乐享`）：
> `<!-- 另有 9 个条目已跳过：type=space×8 /forms/×1（type= 为非文件/容器节点；其中 /forms/ 形态未实测，如需导入请先补 classify_id 白名单并实测验证） -->`（标签按「条数降序、同数按名升序」排列；尾注按实际桶类型自适应）


---

## 输出样例与实现约束

> 2026-09-21 自 SKILL.md 下沉（入口文档只留结论，样例与实现约束放这里）。

```text
[profile=default] 预演（dry_run，不写库）
  目标目录   : https://<租户>.lexiangla.com/pages/<target_entry_id>
  候选       : 3 条
  冲突策略   : skip —— 跳过已存在的（安全档：不改动目的端既有条目）
  既有扫描   : entry_list_children → 10 条
WARN: 目标目录存在 2 条同源条目（entry_id: <entry_id_B> (created_at=1789446554), <entry_id_C> (created_at=1789901234)），归一索引取最早一条 <entry_id_B>
  候选提交保真清单（实际提交字符串 · 匹配结果）:
    #1 MATCHED→复用既有       submit=https://doc.weixin.qq.com/doc/w3_AE8…?scode=<scode>
    #2 MATCHED→复用既有       submit=https://doc.weixin.qq.com/smartpage/a1_AC0…?scode=<scode>
    #3 MATCHED→复用既有       submit=fi…
        └ <候选 note，填了才打>
  将新增 : 0 条（add_num）   已存在 : 3 条（special_num）
  task_id    : <task_id>
  状态       : page_processing   进度 None/3
  状态       : succeed   进度 3/3
  服务端统计 : dry_run_stats add_num=0, special_num=3
```

（以上为 2026-09-20 实跑原文，仅把过长备注与 id 中段做了省略；另删去一行当时会打印的
「输入是微盘分享链接…已自动换算成上面的 file_id」提示 —— 该提示随 2026-09-21 边界重划不再输出。）

> ⚠️ 上面的「既有扫描 → 10 条」是**当天时点快照**，不是稳定判据 —— 目的端条目会被编辑删除，
> **不要把任何一次输出的条目数当断言用**（这也是 SKILL.md 要求 Agent 不要盘点目的端的原因）。

**两条实现约束（改 `scripts/sync.py` 时必须保持）**

1. `create` 必须逐条打印**实际提交的字符串**与匹配结果（保真自证）——
   便于核对「输出字符串与既有条目逐字一致、无被剥离/改写」。
2. 候选若是服务端拒收的形态（现为微盘分享链接），必须**直接拒收并打印换法指引**（`exit 1`、不发导入请求）——
   绝不猜测替换、绝不代跑转换、绝不降级成原样提交。
