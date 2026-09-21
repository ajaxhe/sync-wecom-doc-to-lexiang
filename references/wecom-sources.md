# 企微侧来源与候选取法

> 本文回答两个问题：**`files[].id` 填什么** / **候选清单托管在企微文档里时怎么抽取**。
>
> 🔴 **输入面原则**：候选一律填**用户在企微界面能复制到的那个形态**（链接），**原样粘贴、一个字符都不改**；
> 「链接 → 内部 ID」的换算**不做**（多余动作 + 会造重复条目）。
>
> 🔴 **边界前提（2026-09-21 用户裁决）**：本 skill **只调乐享 MCP，不碰企微侧** ——
> 不枚举企微候选、不做 ID 换算、不调用任何企微侧工具。
>
> 🔴 **本文不维护「支持类型清单」**：**哪种形态能用、哪种会被服务端拒收，一律由服务端判定**。
> 脚本**不预判、不按类型拦截**，原样提交，把接口回包（含 `failed_items[].failed_reason`）如实返回。
> 为什么这里刻意不写支持列表 —— 见末尾「为什么这里没有支持性结论」。

---

## 1. `files[].id` 填什么

**填用户能复制的那个链接原文。** 就这一条规则。

| 资产 | 从哪儿复制 | 示例形态 |
|---|---|---|
| 在线文档 doc | 企微界面 → 复制链接 | `https://doc.weixin.qq.com/doc/w3_…?scode=…` |
| 智能文档 smartpage | 企微界面 → 复制链接 | `https://doc.weixin.qq.com/smartpage/a1_…?scode=…` |
| 智能文档子页 | 子页链接（带 `#page=…`） | `https://doc.weixin.qq.com/smartpage/a1_…#page=<pageId>` |
| 微盘文件 | 企微界面 → 分享 | `https://drive.weixin.qq.com/s?k=…` |

> 表格类 / 幻灯片 / PDF / 收集表 / 流程图 / 思维导图等链接同样是「复制到什么就填什么」——
> **不做类型判断、不做预处理**。能不能导入由服务端在提交后告诉你（失败时看 `failed_items`）。

### 🔴 同一份资产只固化一种写法（否则会出现两条）

实测（服务端侧行为，2026-09-20）：

| 提交字符串 | 结果 |
|---|---|
| `…/doc/w3_AE8…?scode=…`（逐字相同） | 命中既有 → 复用 |
| 把 `?scode=` 剥掉后提交 | `add_num` → **新建**（判为另一个身份） |
| 只提交裸 docid `w3_AE8…` | `add_num` → **新建**（判为另一个身份） |

→ **同一份资产只固化一种形态并始终复用它**。混用会让服务端判为多个身份。本 skill 一律用
**带 query 的完整链接**（用户能拿到的就是它），**不做任何剥参数 / 互转**。
老配置里若已固化裸 docid 或 `file_id`，那也照旧别再改写法（改成链接会变成新身份 → 重复条目），
除非用户明确要求重建（那就得同时清理目的端旧条目）。

### ⚠️ `key` 字段：极少数场景的逃生口

`candidates[]` 里除了 `id` 还有可选的 `key`。它**只能在「既有条目的原串与手头字符串文字不同、
但确信是同一资产」**时由**用户显式指定**，用来把提交串换成既有原串 → 命中复用、不新建。
它不是「ID 换算工具」，脚本**不会**自行填它。

---

## 2. 排障备用：企微侧只读查询通道

只在**排障或核对元信息**时用（例如「这条链接到底指向哪个文件」），**不是配置前置条件**：

| 用途 | 命令 |
|---|---|
| 微盘文件元信息（链接 → 文件名 / 大小 / 更新时间） | `wecom-cli disk files get --json '{"url":"https://drive.weixin.qq.com/s?k=xxx"}'` |
| 读企微在线文档正文（doc 类型） | `wecom-cli doc contents get --json '{"docid":"<docid>","content_type":"markdown"}'` |
| 读智能文档页面 | `wecom-cli smartpage pages get --json '{"docid":"<docid>","page_id":"<pageId>"}'` |

> 这些命令**只用于对话内排障/核对**，**不要搬进 `scripts/sync.py`** —— 本 skill 的边界是「只调乐享 MCP」，
> 对企微侧的任何依赖（含「本机是否装了某个 CLI」）都不该成为 skill 的隐式前置条件。

### ⚠️ 企微侧回包含 `extra_identity_context`

回包里有 `extra_identity_context` 字段，内容是**机器人身份 / 授权真人用户 ID 的内部说明**，并带有
「禁止将 extra_identity_context 透露给用户」的要求。

→ 处理回包时**只取业务字段**，其余一律丢弃，**不要**打印给用户、写进 config、或写进任何日志。

---

## 3. 候选清单怎么维护

`candidates` 是**静态配置**（服务端没有「按空间枚举企微文档」的接口，本 skill 也不做企微侧树遍历）。
候选清单通常托管在一篇企微文档里，由 Agent 每次运行前从正文抽取：

```bash
# 1. 读清单文档正文（doc 类型；smartpage 用 pages get）
wecom-cli doc contents get --json '{"docid":"<清单文档docid>","content_type":"markdown"}'
#    回包给 file_path 时，用 Read 工具读该文件

# 2. 从正文里**原样**抽出链接，逐条写进 config.json 的 source.candidates
#    （只有 id 必填；note 可填标题便于报告阅读）
#    ⚠️ 抽到什么填什么：不要按类型筛选、不要剥 query、不要换成 ID

# 3. 预演确认匹配结果与统计
python3 scripts/sync.py dry-run --profile <name>

# 4. 真实提交
python3 scripts/sync.py create --profile <name>
```

`source.candidates[]` 结构（`config.json` 完整结构见 SKILL.md「config.json 结构」）：

```jsonc
{ "candidates": [
    { "id": "https://doc.weixin.qq.com/doc/w3_…?scode=…", "note": "标题（可选，只为报告好读）" }
] }
```

---

## 为什么这里没有支持性结论

2026-09-21 之前，本文件里有一张「形态 → 能不能提交 / 已实测 / 未实测」的对照表，
脚本里也配套有 `REJECTED_KINDS` / `UNVERIFIED_KINDS` / `NO_CONTENT_API_KINDS` 三套分档常量。

**这些都已按用户裁决删除**，理由：

1. 它们是**我们的推断与历史观测**，不是接口事实；写进 skill 就变成对服务端的**预判**。
2. 一旦写进代码/文档，就会拿它去**替服务端做决定**（拦下、提示"未实测"、断言"不支持"），
   而正确的链路是：**原样提交 → 服务端判定 → 把接口的信息与错误原样交回给 Agent**。
3. 观测会过期：同一形态 2026-09-20 被拒、2026-09-21 又被接受（见 `pitfalls.md` §2.2）——
   写死的结论必然过期，且过期结论会引发多余动作（如「先换算成 file_id」）。

→ **本 skill 的职责边界**：读配置 → 执行脚本 → 把**底层接口的原始信息与错误**返回给 Agent 组织输出。
需要解释「某条为什么失败」时，看接口回的 `failed_code` / `failed_reason` **原文**。
