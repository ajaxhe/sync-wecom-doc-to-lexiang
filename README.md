# Sync WeCom Docs to Lexiang

把**企业微信知识库资产**（在线文档 / 智能文档 / 表格类 / 微盘文件）批量导入**腾讯乐享知识库**指定目录。

> 🔴 **本 skill 不做任何判断逻辑**：**哪种类型、哪种形态能不能导入，一律由服务端判定**。
> 脚本只做三件事 —— **读配置 → 原样提交 → 把底层接口的原始信息与错误（`status` / 计数 /
> `failed_items[].failed_code` + `failed_reason`）返回给 Agent** 组织输出。
> 它**不预判、不按类型拦截、不改写形态**，也**不维护任何「支持类型清单」**（写进去必然过期，还会引出多余动作）。
>
> 🔴 **免升级设计**：接口将来**新增文档类型**（新路径 / 新 host）时，本 skill **不改一行就能导入** ——
> 因为**用户更新 skill 是不确定的行为**，不能把「支持新类型」寄托在用户升级上。
> 详见 `references/wecom-sources.md`「接口新增文档类型时：免升级设计」。

只依赖 Python 标准库，无需安装任何第三方包。

---

## 它是怎么工作的

```
用户给的候选（链接原文）──┐
                        ├─→ [import_create_task] ─→ [轮询终态] ─→ [报告：接口原样回包]
乐享目标目录链接 ───────┘                          ↑
                                      服务端按 id 自己去源侧抓正文 / 图片 / 文件
```

走乐享 MCP 的 `import_create_task` / `import_describe_task` 提交与查询任务：

- **正文、图片、文件全部由服务端抓取** —— Agent 侧不读正文、不上传文件，
  所以无论文档多大多少篇，**LLM token 消耗都极少且固定**；
- 导入结果**可被 RAG 问答**（对比后台「连接器 - 微盘存档」链路：后者对在线文档只存链接、不解析正文）；
- 重复触发是安全的 —— 去重与增量由服务端按 `source.href.id` 处理，**本 skill 不维护任何本地同步状态**。

## 职责边界（重要）

Agent 侧**只做三件事**：① 引导配置 → ② 执行脚本 → ③ 告知结果。

**明确不做**：

| 不做 | 为什么 |
|---|---|
| 在企微侧枚举候选、做任何 ID 换算 | **本 skill 不碰企微侧** —— 不调用任何企微侧工具，避免把「本机装没装某工具」变成隐式前置条件。候选只放**源端链接原文**，链接与 ID 的互转在本链路**不需要** |
| 维护本地「已同步清单」/ manifest / 快照 | 增删与去重由接口自行处理，本 skill 不保存任何本地同步状态 |
| 盘点「目的端目录里多了或少了几条」 | 目的端增删由接口参数 `conflict_strategy` 决定；源端与目的端的文档都会被编辑删除，**没有「正确条目数」这个概念** |
| 改写用户给的 ID 字符串 | 手改一个字符 = 换一个身份 = 产生重复条目 |
| **判断「哪类文档能导入 / 哪种形态不行」** | **那是服务端的判定**。脚本不预判、不按类型拦截，原样提交并把接口回包（含失败原因**原文**）返回；**不要**维护「支持类型清单」或「已实测 / 未实测」分档 |

## 前置条件（先确认，否则导入必失败）

1. **乐享侧「授权配置」已完成** —— 这一步在**乐享页面**上完成，按官方文档操作：
   <https://lexiangla.com/pages/d4a717fbf4604efea4bd286fdcdac31a?company_from=906ba45e6f9a11f089c57a2a2b4bccb6>
   （未完成或已过期会让导入任务失败；脚本在 `init` 与各个失败出口都会打印该地址）
2. 一个乐享 MCP Token —— <https://lexiangla.com/ai/claw>

## 快速开始

```bash
cd <skill 目录>

# ① 建 profile（生成配置模板；已存在则不覆盖）
python3 scripts/sync.py init --profile default

# ② 解析乐享目标目录 → 拿到 space_id / parent_entry_id（只读，不改配置）
python3 scripts/sync.py resolve 'https://<租户>.lexiangla.com/pages/<目录 entry_id>'

# ③ 编辑 profiles/default/config.json：
#      auth.mcp_token    ← 从 https://lexiangla.com/ai/claw 获取
#      target            ← 粘贴上一步打印的片段
#      source.candidates ← 要导入的企微资产标识，一条一个 { "id": "…" }

# ④ 预演（不写库）。必须看到 dry_run_stats 才算配置成功
python3 scripts/sync.py dry-run --profile default

# ⑤ 真实提交（显式下发 conflict_strategy，轮询到终态）
python3 scripts/sync.py create --profile default
```

## 命令

| 命令 | 用途 | 退出码 |
|---|---|---|
| `init [--profile N]` | 生成 profile 配置模板（已存在则不覆盖） | 0 / 2 |
| `list` | 列出全部 profile 及配置就绪状态 | 0 / 2 |
| `dry-run [--profile N]` | 预演：`dry_run=true`，不写库，打印 `dry_run_stats` | 0 / 1 / 2 |
| `create [--profile N] [--no-wait]` | 提交导入任务并轮询到终态 | 0 / 1 / 2 |
| `status [--profile N]` | 查缓存任务状态 / 进度 / 失败原因 | 0 / 1 / 2 |
| `resolve <乐享链接或 entry_id>` | **只读**：解析出 `space_id` / `entry_id`，打印可粘贴的 `target` 片段 | 0 / 1 / 2 |

**通用开关**：`--profile NAME`（缺省 `default`）、`--debug`（把请求体与原始回包写入该 profile 的 `sync.log`）、
`--no-wait`（仅建任务不轮询）、`--strategy <值>`（临时覆盖冲突策略）。

**退出码**：`0` 成功（含「已有进行中任务 → 静默退出」供定时任务复用；含任务 `failed` 但未成功项全部为
内容提示类失败码（`BENIGN_FAILED_CODES`，如 `video_content_empty` —— 文件已导入成功，仅内容处理为空/受限））；
`1` 运行期失败（鉴权失效 / 任务 `failed` 且存在真失败项 / 任务到终态但仍有条目处理中（排空超时，
会打印「等全部处理完再跑 status 汇总」的 Agent 指令）/ 凭证缺失 / 目录扫描失败 / 网络异常 / 轮询超时）；
`2` 用法错误。

## 候选 ID 填什么

**填用户从企微界面能复制到的那个链接原文**，原样粘贴、勿手改：

| 资产 | 填什么 |
|---|---|
| 在线文档 / 智能文档 / 表格类 / 其他文档类型 | 从企微界面复制的**完整链接**（含 `?scode=`） |
| 微盘文件 | 分享链接 `https://drive.weixin.qq.com/s?k=…`（含 `?k=`）；老配置的 `file_id` 可继续用 |

⚠️ **不做类型筛选**：抽到什么填什么。**能不能导入由服务端判定**，失败时脚本会把接口回的
`failed_code` / `failed_reason` **原文**返回 —— 用户要的解释以这份回包为准，不要自行推测原因或改写形态。

**不要换算**：链接 ↔ docid / file_id 互转、剥掉 query 参数，都会被服务端判成**另一个身份** → 目的端多出一条。

> 📦 历史：2026-09-20 曾实测「微盘分享链接被服务端拒收」，据此设计过一套「先换算成 `file_id`」的流程；
> 2026-09-21 复验发现服务端**已直接接受**该形态，换算流程与相关拦截逻辑**全部删除**
> （详见 `references/pitfalls.md` §2.2、§2.4）。
> 教训：**一次实测 ≠ 长期事实** —— 这也是现在「不在 skill 里写任何支持性结论」的原因。

## 冲突处理策略

决定服务端怎么处置目的端：

| 取值 | 含义 | 风险 |
|---|---|---|
| `skip` | 跳过已存在的 | **安全档（默认）** |
| `replace` | 覆盖目的端 | ⚠️ 服务端以本次提交为准替换该目录内容，**既有条目会被删除** |
| `keep_both` | 两者都保留 | ⚠️ **会产生重复条目** |

- 配置位置：`source.conflict_strategy`；脚本一律**显式下发**该字段，不依赖服务端默认。
- ⚠️ **`dry-run` 对该策略是盲的**（四路取值下 `dry_run_stats` 完全一致），「零新增」**不等于**「没动目的端」。
- ⚠️ `replace` 只能在**专用导入目录**上使用。

## 目录结构

```
SKILL.md                  # 主入口：边界、红线、配置引导、命令
scripts/
  sync.py                 # 全部子命令的实现（唯一入口）
references/
  import-api.md           # 接口参数全表 + 校验行为实测 + MCP 调用路径
  wecom-sources.md        # 企微侧链接形态速查（形态 ↔ 示例，不含支持性结论）
  pitfalls.md             # 踩坑、已知限制、实测现场记录
profiles/                 # 运行状态（已 gitignore，绝不提交）
  <任务名>/               # 每个任务一个 profile，互不干扰
    config.json           # 含 MCP Token
    .task_id.cache        # 进行中任务 id（幂等）
    sync.log              # --debug 时产生
```

**多任务隔离**：每个定时任务用一个独立 profile（`--profile <任务名>`），互不干扰、无并发冲突。

## 环境要求

- Python 3（仅标准库）
- 乐享侧**授权配置已完成**（见上面「前置条件」；本 skill 不做授权、也不代查状态）
- 一个乐享 MCP Token（<https://lexiangla.com/ai/claw>）

## 相关

- 本 skill 的架构与边界遵循规范 skill `lexiang-import-skill-spec`（「走 MCP 的 SaaS 导入类 skill」的
  三条边界铁律、标准骨架与红线）
- 姊妹实现：[`sync-obsidian-to-lexiang`](https://github.com/ajaxhe/sync-obsidian-to-lexiang)（Obsidian → 乐享，本地取数族）
