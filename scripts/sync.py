#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync-wecom-doc-to-lexiang —— 把企微知识库资产（在线文档 + 微盘文件）批量 + 增量导入乐享指定目录。

零第三方依赖（仅 Python 标准库，不需要装任何 pip 包）。
多 profile 隔离：profiles/<name>/{config.json,.task_id.cache,sync.log}。

前置条件（都在乐享侧完成，本脚本只指路、不代劳）：
    · 该乐享企业/账号已完成「授权配置」—— 导入能跑通的前提；未完成或已过期会让导入失败。
      授权文档：https://lexiangla.com/pages/d4a717fbf4604efea4bd286fdcdac31a?company_from=906ba45e6f9a11f089c57a2a2b4bccb6
    · config.json 已填该账号 MCP Token（获取：https://lexiangla.com/ai/claw）。

用法：
    python3 scripts/sync.py init    [--profile NAME]              # 生成 profile 配置模板 + profiles/.gitignore
    python3 scripts/sync.py list                                  # 列出全部 profile 及配置就绪状态
    python3 scripts/sync.py dry-run [--profile NAME]              # 预演（dry_run=true，不写库），打印 dry_run_stats
    python3 scripts/sync.py create  [--profile NAME] [--no-wait] [--strategy S]
                                                          # 提交导入任务（轮询到终态）
                                                          # --strategy：覆盖配置的冲突策略
                                                          #   skip（默认，安全）| replace | keep_both
    python3 scripts/sync.py status  [--profile NAME]              # 查缓存任务状态与进度
    python3 scripts/sync.py resolve '<乐享目录链接>'              # 解析出 space_id / entry_id（只打印，不改配置）
    加 --debug：把「时间戳 + 等价 curl（token 打码）+ 请求体 + 原始回包」写入该 profile 的 sync.log

    不指定 --profile 时默认用 default profile。

MCP 调用路径（走哪条**由当前可见 tools 决定**，不遵守会让所有联网命令 exit 1）：
    官方规则（resource `lexiang://docs/instructions/v1`「工具调用方式」）：可见工具清单由服务端按
    company / feature_flag / allowlist 过滤 —— 在清单里就直接调，不在而 `call_tool` 在就必须包装。
    所以**不同账号 / 环境可能不同，不能写死**：
    · 脚本先查一次 `tools/list`（进程内缓存），再据此选路径；
    · 业务工具在可见清单里 → 直调；不在 → 包装成
      {"name":"call_tool","arguments":{"tool_name":"<工具名>","arguments":{…}}}
    · 元工具（whoami / call_tool / get_tool_schema / lexiang_fetch / lexiang_search /
      list_tool_categories / search_tools）→ 直接调用
    · 另一条路径留作兜底（探测失败 / 服务端反馈与清单不一致时）；两条都被拒才报错。
    --debug 打印的等价 curl 就是最终发出的这一层，可直接复制复现。

候选 id 填什么（**只能填服务端直接接受的形态**）：
    · 企微在线文档 / 智能文档 / 表格 → **原始链接**：`https://doc.weixin.qq.com/...` 整条粘贴（含 `?scode=`）。
    · 微盘文件 → `file_id`（`fi…` 长串）。
    · 微盘分享链接（`https://drive.weixin.qq.com/s?k=…`）**不被服务端接受**，本脚本也**不做换算** ——
      识别到即中止并给出指引；需先在**对话中**把它换成 `file_id` 再填进候选。
    · 裸 docid / 裸 file_id 也能识别，但**不推荐**：正常用户从企微界面拿不到 docid。

冲突处理策略（服务端字段 `conflict_strategy`，本脚本**一律显式下发**，默认 `skip`）：
    · skip      = 跳过已存在的（**默认、安全档**：不改动目的端既有条目）
    · replace   = 覆盖目的端（服务端以本次提交为准替换该目录内容，**既有条目可能被删除**）
    · keep_both = 两者都保留（**会产生重复条目**）
    配置位置：`source.conflict_strategy`；也可用 `create --strategy <值>` 临时覆盖。
    ⚠️ **dry-run 对该策略是盲的** —— 不传 / replace / skip / keep_both 四路的 dry_run_stats 实测完全一致。
       所以「dry-run 报零新增」**不能**当成「真跑不会动目的端」的依据。
    ⚠️ **不传该字段时，服务端默认行为是破坏性的**（实测：一次 create 把目标目录原有 10 条条目、
       含 7 条与本批无关的，裁成本次提交的 3 条）→ 脚本**绝不省略**这个字段。详见 references/pitfalls.md §2.9。

退出码：0 成功（含「已有进行中任务 → 静默退出」，供定时任务复用）；
        1 运行期失败（鉴权失效 / 任务 failed / ID 形态非法 / 凭证缺失 / 目录扫描失败 /
                     网络异常 / 轮询超时 / 候选为服务端拒收形态）；
        2 用法错误（未知命令、缺参数）。

🔴 三条不变式（改代码前务必先读 references/pitfalls.md）：
   1. 脚本绝不改写**待提交**的 ID 字符串（剥 query、URL↔裸 id 互转 → 制造重复条目）。
      候选一律**原样提交**（命中归一索引时回填既有原串，仍不改一个字符）。
   2. norm() 仅供客户端匹配判等，绝不回传给服务端。
   3. **本 skill 不碰企微侧**：不枚举企微候选、不做 ID 换算、不调用任何企微侧工具。
      候选必须是服务端直接接受的形态；微盘分享链接一律拒收（exit 1）并给出「先换 file_id」的指引，
      绝不猜测、绝不代跑 —— 需要转换时由 Agent 在**对话中**引导完成。

⚠️ 安全：profiles/ 含密钥（config.json 的 mcp_token）与日志，绝不可提交到任何代码/skill 托管平台。
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))    # = <skill>/scripts
SKILL_ROOT = os.path.dirname(HERE)                   # = <skill> 根目录
PROFILES_DIR = os.path.join(SKILL_ROOT, "profiles")  # 状态目录固定留在 skill 根
DEFAULT_PROFILE = "default"

# 任务状态
IN_PROGRESS_STATES = {"page_processing", "processing", "pending", "running"}
FINAL_STATES = {"succeed", "failed"}

# 轮询上限：60 次 × 3s = 180s。超时即 exit 1，绝不无限轮询（主理人硬规格 #3）
POLL_INTERVAL = 3
POLL_MAX = 60

# 目录扫描分页
CHILDREN_PAGE_LIMIT = 100
CHILDREN_MAX_PAGES = 200

DEBUG = os.environ.get("SYNC_DEBUG", "").strip() in ("1", "true", "yes", "on")


class AuthError(RuntimeError):
    """鉴权失效（401/403）——单独一类，便于给用户明确文案。"""


class ToolPathUnavailable(RuntimeError):
    """服务端拒绝了**当前的调用路径**（不是工具本身）。

    用于在「call_tool 包装」与「直调」两条路径之间自动回退 —— 与其它类型错误的语义
    严格区分开，避免把「路径不通」误当成「工具不可用」而放弃重试，反之亦然。
    """


# --------------------------------------------------------------------------
# MCP 调用路径（走哪条**由当前可见 tools 决定**，不是平台的固定行为；改动前务必读完本节）
# --------------------------------------------------------------------------
# 官方说明 resource `lexiang://docs/instructions/v1`「工具调用方式」一节的原文规则：
#   可见工具清单由 MCP 服务按【company / feature_flag / allowlist】动态过滤，于是
#     ① 当前可见 tools 里**有**目标业务工具 → 直接调用；
#     ② **没有**、但 `call_tool` 在 → **必须**经 call_tool 包装（传 tool_name + arguments）。
# 实测（2026-09-21，个人 token 环境）：
#   `tools/list` 只回下面这 7 个元工具；直调 entry_* / import_* 回**纯文本**
#   「tool is not allowed: <工具名>」；同一 token 下直调 whoami 正常、包装调用正常
#   → 说明是**可见性**差异，不是凭证问题。
# ⚠️ 不要把这条实测当成「平台禁止直调」：可见性与账号 / 环境有关，别人的 allowlist 下
#   可能就是能直调的。所以脚本按官方规则**先查可见 tools 再选路径**，两种配置都能跑；
#   报错文案（_path_rejected）只作最后兜底。
META_TOOLS = frozenset([
    "whoami", "call_tool", "get_tool_schema",
    "lexiang_fetch", "lexiang_search",
    "list_tool_categories", "search_tools",
])
CALL_TOOL = "call_tool"

# 乐享站点根地址：**仅用于「用户只给了裸 entry_id」时拼接展示用链接**，不参与任何接口调用
# （接口地址走 config 的 auth.endpoint）。默认通用域名；可用环境变量 LEXIANG_ORIGIN
# 覆盖为自己租户的地址，例如 https://<你的租户>.lexiangla.com
DEFAULT_LEXIANG_ORIGIN = os.environ.get("LEXIANG_ORIGIN", "https://lexiangla.com").rstrip("/")

# MCP Token 获取页（乐享 AI 页面）。
TOKEN_URL = "https://lexiangla.com/ai/claw"

# 乐享侧「授权配置」官方文档 —— **导入的前置条件**：未完成或已过期会让导入任务失败。
# ⚠️ 这是**对外公开的产品文档链接**，不是本机/个人资源：skill 发布到代码托管平台时**保留**，
#    脱敏扫描请把本常量列入白名单（URL 里的 32 位串是文档 entry_id 与该企业的 company_from 参数）。
AUTH_DOC_URL = "https://lexiangla.com/pages/d4a717fbf4604efea4bd286fdcdac31a?company_from=906ba45e6f9a11f089c57a2a2b4bccb6"

# 进程内缓存：{endpoint: frozenset(可见工具名)}。探测失败记 None → 退回「包装→直调」回退链。
_VISIBLE_TOOLS = {}


CONFIG_TEMPLATE = {
    "_comment": "sync-wecom-doc-to-lexiang profile 配置。含密钥，切勿提交（profiles/ 已 gitignore）。"
                "候选**只填 id 就够**。可选字段（都可省略，省略即取默认）："
                "candidates[].key（身份归一覆盖值，默认空）、"
                "candidates[].include_subpages（默认取 source.include_subpages，后者默认 true）、"
                "candidates[].note（本地备注，不进请求体）。",
    "auth": {
        "endpoint": "https://mcp.lexiang-app.com/mcp",
        "mcp_token": "lxmcp_在此填入个人MCP Token",
        "request_timeout": 30,
    },
    "source": {
        "type": "wecombot",
        # skip（默认，安全：不改动目的端既有条目）| replace（覆盖：会替换该目录内容）| keep_both（会产生重复）
        "conflict_strategy": "skip",
        "candidates": [
            {
                "id": "在此填入服务端直接接受的形态（在线文档 https://doc.weixin.qq.com/... 整条粘贴；"
                      "微盘 file_id fi… 长串。分享链接不被服务端接受，需先换成 file_id）",
            }
        ],
    },
    "target": {
        "lexiang_url": "https://<租户>.lexiangla.com/pages/在此填入目标entry_id",
        "space_id": "在此填入space_id",
        "parent_entry_id": "在此填入目标目录entry_id",
    },
}

GITIGNORE_CONTENT = (
    "# 本目录含密钥(config.json 的 mcp_token)与日志(sync.log 可能含请求细节)。\n"
    "# 严禁提交到 GitHub / ClawHub 等任何代码或 skill 托管平台，防止敏感信息泄露。\n"
    "*\n"
    "!.gitignore\n"
)


class Ctx(object):
    """承载 profile 相关路径（替代全局常量）。"""

    def __init__(self, profile):
        self.profile = profile
        self.dir = os.path.join(PROFILES_DIR, profile)
        self.config_path = os.path.join(self.dir, "config.json")
        self.cache_path = os.path.join(self.dir, ".task_id.cache")
        self.log_path = os.path.join(self.dir, "sync.log")


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _mask_token(token):
    """token 打码：保留前缀 + 末 4 位，中间 ***。绝不把明文写进日志。"""
    if not token:
        return ""
    if len(token) <= 12:
        return token[:4] + "***"
    return token[:10] + "***" + token[-4:]


def print_auth_hint(stream=None, indent="  "):
    """打印「去乐享页面完成授权」的引导 —— 全脚本**唯一出口**（避免同一段文案在多处漂移）。

    由调用方决定时机：init（首次初始化）、鉴权 / 授权类失败、创建任务失败、导入任务 failed。
    本 skill **不做授权、也不代查授权状态**，只把乐享官方文档指给用户；也**不复述文档内容** ——
    文档由乐享官方维护，复述会随其更新而失真。
    """
    out = sys.stderr if stream is None else stream
    print("%s授权提示   : 导入的前置条件是在乐享页面完成「授权配置」；若尚未完成或已过期，"
          "按此文档操作 ——" % indent, file=out)
    print("%s             %s" % (indent, AUTH_DOC_URL), file=out)


def debug_log(ctx, *lines):
    if not DEBUG:
        return
    with open(ctx.log_path, "a", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln + "\n")


def build_curl(endpoint, token, body_str):
    safe_body = body_str.replace("'", "'\\''")
    return (
        "curl -s -X POST \"%s\" \\\n"
        "  -H \"Content-Type: application/json\" \\\n"
        "  -H \"Accept: application/json\" \\\n"
        "  -H \"Authorization: Bearer %s\" \\\n"
        "  -d '%s'"
    ) % (endpoint, _mask_token(token), safe_body)


# ==========================================================================
# ID 归一（仅供客户端匹配判等，绝不回传）
# ==========================================================================

def _lower_host(s):
    """仅把 scheme + host 小写；path / fragment 大小写原样保留。"""
    m = re.match(r"^(https?://)([^/]+)(.*)$", s, re.I | re.S)
    if not m:
        return s
    return m.group(1).lower() + m.group(2).lower() + m.group(3)


def norm(raw):
    """归一规则（**仅供客户端判等**，绝不回传给服务端）：

    ① 去首尾空白（含从聊天窗口复制带进来的 \\n / 空格）；
    ② 剥 `?...` query（scode / from 等）；
    ③ **保留** `#page=<pageId>` fragment —— include_subpages 下智能文档每个子页是独立子条目，
       href.id 形如 `…/smartpage/a1_xxx#page=<pageId>`，fragment 是身份锚点，剥了会错配；
    ④ 微盘分享链接 `s?k=<k>` —— 身份本体是 k，**保留 k**；
    ⑤ host 小写，path / id 大小写不改写。
    """
    s = (raw or "").strip()
    if not s:
        return ""
    if "#" in s:
        base, frag = s.split("#", 1)
        frag = "#" + frag
    else:
        base, frag = s, ""
    if "?" in base:
        base, query = base.split("?", 1)
    else:
        base, query = base, ""

    base_l = _lower_host(base)
    # ④ 微盘分享链接：保留 k
    if "drive.weixin.qq.com/s" in base_l and base_l.rstrip("/").endswith("/s"):
        m = re.search(r"(?:^|&)k=([^&\s]+)", query)
        if m:
            return "https://drive.weixin.qq.com/s?k=" + m.group(1) + frag
    return base_l + frag


# ==========================================================================
# ID 形态本地校验（classify_id 为纯本地函数，只做正则匹配，不发起网络请求）
# ==========================================================================

# (kind, 正则, 人话标签, 是否已实测)
_ID_RULES = [
    ("wecom_doc_url", re.compile(r"^https?://doc\.weixin\.qq\.com/doc/[A-Za-z0-9_\-]+", re.I),
     "企微在线文档 URL（/doc/）", True),
    ("wecom_smartpage_url", re.compile(r"^https?://doc\.weixin\.qq\.com/smartpage/[A-Za-z0-9_\-]+", re.I),
     "企微智能文档 URL（/smartpage/）", True),
    ("wecom_sheet_url", re.compile(r"^https?://doc\.weixin\.qq\.com/sheet/[A-Za-z0-9_\-]+", re.I),
     "企微在线表格 URL（/sheet/）", False),
    ("wecom_smartsheet_url", re.compile(r"^https?://doc\.weixin\.qq\.com/smartsheet/[A-Za-z0-9_\-]+", re.I),
     "企微智能表格 URL（/smartsheet/）", False),
    ("wecom_disk_share_url", re.compile(r"^https?://drive\.weixin\.qq\.com/s\?[^\s]*\bk=[A-Za-z0-9_\-]+", re.I),
     "微盘分享链接（drive.weixin.qq.com/s?k=）", True),
    ("wecom_disk_file_id", re.compile(r"^fi[A-Za-z0-9_\-]{20,}$"),
     "微盘 file_id（fi… 长串）", True),
    # 裸 docid：需求摘要点名的是 w3_ / a1_ / b1_（已实测）。
    ("wecom_bare_id", re.compile(r"^(?:w3_|a1_|b1_)[A-Za-z0-9_\-]+$"),
     "裸 docid（w3_ / a1_ / b1_）", True),
    # 实跑 disk files list 发现 docid 字段远不止 w3_/a1_/b1_：还出现 c2_（收集表）、d3_、e3_、f4_、m4_、p3_、s3_。
    # 无法识别这些前缀会让用户合法粘贴的裸 docid 被本地误判为「形态非法」，所以放行；
    # 但**没有实测**过它们能否被导入，故标 False（脚本会打印「按同一 provider 路径推断，未实测」）。
    ("wecom_bare_id_other", re.compile(r"^[a-z][0-9]_[A-Za-z0-9_\-]{6,}$"),
     "裸 docid（w3_/a1_/b1_ 之外的前缀：c2_ / d3_ / s3_ 等）", False),
]

ID_SHAPE_HINT = (
    "推荐填服务端直接接受的形态：企微在线文档 / 智能文档 / 表格 URL（`https://doc.weixin.qq.com/...` 整条粘贴，含 ?scode=）、"
    "微盘 file_id（fi… 长串）。"
    "微盘分享链接（`https://drive.weixin.qq.com/s?k=…`）不被服务端接受，本脚本不做换算，需先换成 file_id；"
    "裸 docid（w3_ / a1_ 等）也接受，但正常用户从企微界面拿不到，不推荐"
)

# 按同一 provider 路径推断、但本次未实测的形态 —— 必须显式提示，不能把推断当事实
UNVERIFIED_KINDS = {"wecom_sheet_url", "wecom_smartsheet_url", "wecom_bare_id_other"}

# 服务端**实测拒收**、且本 skill **不做**任何企微侧查询与换算的形态：
# 识别出来只为给一条明确指引，绝不放行到提交阶段。
# 微盘分享链接实测被拒（任务 failed，failed_reason = 非法的 'file_id' …，详见 references/pitfalls.md §2.3）——
# 需**先在对话中**把它换成 file_id，再写进候选（本 skill 不代跑这一步）。
REJECTED_KINDS = {"wecom_disk_share_url"}

# ==========================================================================
# 冲突处理策略（服务端字段 `conflict_strategy`）
# ==========================================================================
# 取值由服务端校验器实测吐出（2026-09-20）：
#   conflict_strategy: value must be in list ["replace", "skip", "keep_both"]
#
#   skip       = 跳过已存在的（本脚本**默认**：不动目的端、不产生重复）
#   replace    = 覆盖目的端
#   keep_both  = 两者都保留（**会产生重复条目**）
#
# 🔴 实测事故记录（2026-09-20，**未传该字段**时的服务端默认行为）：
#   一次 create 把目标目录原有 10 条条目（含 7 条与本批候选**无关**的）全部删除，
#   重建为本次提交的 3 条 —— 即**默认行为等价于「把目标目录内容替换成本次提交的集合」**。
#   对内容会变动 / 需要增量累积的目录，这是破坏性的。详见 references/pitfalls.md §2.9。
# 🔴 **dry-run 对该策略是盲的**：不传 / replace / skip / keep_both 四路的 dry_run_stats
#   完全一致（实测），所以**「dry-run 报零新增」绝不能当作「真跑不会动目的端」的依据**。
#   → 因此本脚本**一律显式传该字段**，默认 `skip`，绝不依赖服务端默认。
CONFLICT_STRATEGIES = ("skip", "replace", "keep_both")
DEFAULT_CONFLICT_STRATEGY = "skip"


def classify_id(raw):
    """返回 (kind, label, tested)；无法识别返回 (None, None, None)。"""
    s = (raw or "").strip()
    if not s:
        return None, None, None
    for kind, rx, label, tested in _ID_RULES:
        if rx.match(s):
            return kind, label, tested
    return None, None, None


# ==========================================================================
# 配置 / 缓存
# ==========================================================================

def ensure_gitignore():
    if not os.path.isdir(PROFILES_DIR):
        os.makedirs(PROFILES_DIR)
    gi = os.path.join(PROFILES_DIR, ".gitignore")
    if not os.path.exists(gi):
        with open(gi, "w", encoding="utf-8") as f:
            f.write(GITIGNORE_CONTENT)


def load_config(ctx):
    if not os.path.exists(ctx.config_path):
        print("profile 「%s」不存在或未配置：%s\n请先运行 `python3 scripts/sync.py init --profile %s` 初始化，再填写 config.json。"
              % (ctx.profile, ctx.config_path, ctx.profile), file=sys.stderr)
        sys.exit(1)

    with open(ctx.config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    auth = cfg.get("auth", {}) or {}
    src = cfg.get("source", {}) or {}
    tgt = cfg.get("target", {}) or {}
    token = str(auth.get("mcp_token") or "")
    space_id = str(tgt.get("space_id") or "")
    parent = str(tgt.get("parent_entry_id") or "")
    candidates = src.get("candidates") or []

    joined = token + space_id + parent + json.dumps(candidates, ensure_ascii=False)
    if "在此填入" in joined or not token or not space_id or not parent:
        print("profile 「%s」的 config.json 仍是初始化模板：请填 auth.mcp_token / source.candidates / target 后再运行。\n"
              "获取 token：%s" % (ctx.profile, TOKEN_URL), file=sys.stderr)
        sys.exit(1)

    if not candidates:
        print("profile 「%s」的 source.candidates 为空：请至少放一条企微候选"
              "（服务端直接接受的形态：在线文档 URL 或微盘 file_id）。"
              % ctx.profile, file=sys.stderr)
        sys.exit(1)

    for i, c in enumerate(candidates, 1):
        if not str(((c or {}).get("id")) or "").strip():
            print("profile 「%s」的 source.candidates 第 %d 项缺少 id。" % (ctx.profile, i), file=sys.stderr)
            sys.exit(1)

    try:
        timeout = int(auth.get("request_timeout") or 30)
    except (TypeError, ValueError):
        timeout = 30

    # 冲突处理策略：缺省 `skip`（安全档）。**一律显式下发，绝不依赖服务端默认** ——
    # 实测其默认行为会把目标目录内容替换成本次提交的集合（既有条目会被删），见 CONFLICT_STRATEGIES 注释。
    strategy = str(src.get("conflict_strategy") or DEFAULT_CONFLICT_STRATEGY).strip().lower()
    if strategy not in CONFLICT_STRATEGIES:
        print("profile 「%s」的 source.conflict_strategy 取值非法：「%s」。合法取值：%s"
              % (ctx.profile, strategy, " / ".join(CONFLICT_STRATEGIES)), file=sys.stderr)
        sys.exit(1)

    return {
        "endpoint": auth.get("endpoint") or "https://mcp.lexiang-app.com/mcp",
        "token": token,
        "timeout": timeout,
        "type": src.get("type") or "wecombot",
        "include_subpages": bool(src.get("include_subpages", True)),
        "conflict_strategy": strategy,
        "candidates": candidates,
        "space_id": space_id,
        "parent_entry_id": parent,
        "target_url": tgt.get("lexiang_url", ""),
    }


def read_cache(ctx):
    if not os.path.exists(ctx.cache_path):
        return None
    with open(ctx.cache_path, "r", encoding="utf-8") as f:
        tid = f.read().strip()
    return tid or None


def write_cache(ctx, task_id):
    with open(ctx.cache_path, "w", encoding="utf-8") as f:
        f.write(task_id.strip() + "\n")


# ==========================================================================
# 乐享 MCP HTTP
# ==========================================================================

def _rpc_post(ctx, cfg, payload, path):
    """发**一次** JSON-RPC，返回**外层**对象（只做传输 + 外层解析，不碰 tools/call 语义）。

    `path` 仅用于 debug 日志如实标注本次走的是哪条路径，由调用方显式传入 ——
    **不要**靠工具名反推（`call_tool` 本身也是元工具名，反推会标错）。
    """
    body_str = json.dumps(payload, ensure_ascii=False)
    shown = (payload.get("params") or {}).get("name") or payload.get("method")

    debug_log(
        ctx,
        "=" * 78,
        "[%s] >>> REQUEST  profile=%s  tool=%s  endpoint=%s" % (_now(), ctx.profile, shown, cfg["endpoint"]),
        "--- 调用路径 ---",
        {"meta": "元工具，直接调用",
         "wrapped": "经 call_tool 包装调用",
         "direct": "直调（该业务工具在当前可见 tools 里）"}.get(path, str(path)),
        "--- 请求体 (JSON-RPC) ---",
        body_str,
        "--- 等价 curl (token 已打码) ---",
        build_curl(cfg["endpoint"], cfg["token"], body_str),
    )

    req = urllib.request.Request(
        cfg["endpoint"],
        data=body_str.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer " + cfg["token"],
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        debug_log(ctx, "[%s] <<< HTTP ERROR code=%s" % (_now(), e.code), "--- 错误回包 ---", body)
        if e.code in (401, 403):
            raise AuthError(
                "乐享鉴权失败（HTTP %s）。\n"
                "  · 先在 config.json 更新 auth.mcp_token（重新获取：%s）。\n"
                "  · 若更新后仍失败，可能是乐享侧「授权配置」未完成或已过期 —— "
                "按此文档在乐享页面完成授权：\n"
                "    %s" % (e.code, TOKEN_URL, AUTH_DOC_URL))
        raise RuntimeError("调用乐享 MCP 失败：HTTP %s %s" % (e.code, body[:300]))
    except AuthError:
        raise
    except Exception as e:
        debug_log(ctx, "[%s] <<< 请求异常: %s" % (_now(), e))
        raise RuntimeError("调用乐享 MCP 失败：%s" % e)

    debug_log(ctx, "[%s] <<< RESPONSE (原始回包)" % _now(), raw)

    try:
        outer = json.loads(raw)
    except ValueError:
        raise RuntimeError("调用乐享 MCP 失败：回包不是合法 JSON（可加 --debug 查看 sync.log）")

    if "error" in outer:
        raise RuntimeError("调用乐享 MCP 失败：%s" % json.dumps(outer["error"], ensure_ascii=False)[:300])
    return outer


def _visible_tools(ctx, cfg):
    """当前 token 上下文下的**可见工具清单**（官方要求：调用前先检查可见 tools）。

    可见性由 company / feature_flag / allowlist 过滤 —— **不同账号 / 环境可能不同**，
    所以它是本脚本唯一区分「直调」与「call_tool 包装」的依据，不能写死。
    探测失败（网络 / 解析）返回 None，调用方退回「包装→直调」回退链，不影响可用性。
    """
    key = cfg["endpoint"]
    if key not in _VISIBLE_TOOLS:
        try:
            outer = _rpc_post(ctx, cfg, {"jsonrpc": "2.0", "id": 0,
                                        "method": "tools/list", "params": {}}, "meta")
            result = outer.get("result") or {}
            names = frozenset(
                str(t.get("name")) for t in (result.get("tools") or []) if t.get("name"))
            _VISIBLE_TOOLS[key] = names
            debug_log(ctx, "[%s] <<< tools/list 可见工具 %d 个：%s"
                       % (_now(), len(names), sorted(names)))
        except Exception as e:      # 探测失败绝不能影响主流程
            debug_log(ctx, "[%s] <<< tools/list 探测失败 → 退回「包装→直调」回退链：%s" % (_now(), e))
            _VISIBLE_TOOLS[key] = None
    return _VISIBLE_TOOLS[key]


def _mcp_post(ctx, cfg, tool_name, arguments, req_id, path="meta"):
    """发一次 `tools/call` 并解出内层对象（单路径，不做重试 / 回退）。

    回包表明「这条调用路径被服务端拒绝」时抛 ToolPathUnavailable，交由 mcp_call() 决定回退。
    """
    outer = _rpc_post(ctx, cfg, {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }, path)

    result = outer.get("result", {}) or {}
    content = result.get("content", []) or []
    if content and content[0].get("type") == "text":
        text = content[0]["text"]
        try:
            inner = json.loads(text)
        except ValueError:
            # 服务端在下面两种情况下回的是**纯文本**而不是 JSON：
            #   "tool is not allowed: <工具名>"  "tool not found: <工具名>"
            if _path_rejected(text, tool_name):
                raise ToolPathUnavailable(str(text).strip()[:200])
            raise RuntimeError(
                "调用乐享 MCP 失败：回包 content 不是 JSON —— 「%s」（可加 --debug 查看 sync.log）"
                % str(text).strip()[:300])
        msg = str(inner.get("message") or "")
        low = msg.lower()
        if "unauthorized" in low or "invalid token" in low or inner.get("code") in (401, 403):
            raise AuthError(
                "乐享鉴权失败（token 无效或过期）。\n"
                "  · 先在 config.json 更新 auth.mcp_token（重新获取：%s）。\n"
                "  · 若更新后仍失败，可能是乐享侧「授权配置」未完成或已过期 —— "
                "按此文档在乐享页面完成授权：\n"
                "    %s" % (TOKEN_URL, AUTH_DOC_URL))
        return inner
    if isinstance(result.get("structuredContent"), dict):
        return {"code": 0, "data": result["structuredContent"]}
    raise RuntimeError("无法解析 MCP 返回（可加 --debug 查看 sync.log）")


def _path_rejected(text, called_name):
    """回包文本是否为「**这条调用路径**被服务端拒绝」。

    判据：形如 `<marker>: <名字>`，且 `<名字>` 与我们**实际调用**的工具一致。
    这样能把两种情况分开：
      · "tool is not allowed: call_tool"      → 包装路径不通 → 可以回退直调
      · "tool is not allowed: import_create_task"（包装调用时收到）→ 工具本身不可用 → 回退无意义
    """
    low = str(text).strip().lower()
    for marker in ("tool is not allowed:", "tool not found:"):
        if low.startswith(marker):
            return low[len(marker):].strip() == called_name.lower()
    return False


def mcp_call(ctx, cfg, tool_name, arguments, req_id=1):
    """调用乐享 MCP，返回解出的内层对象（已剥掉 JSON-RPC 与 content[0].text 两层）。

    路径选择按**官方规则**（`lexiang://docs/instructions/v1`「工具调用方式」）：
      · 元工具 → 直调；
      · 业务工具在**当前可见 tools** 里 → 直调；不在 → 经 `call_tool` 包装。
    保留「另一条路径」作为兜底（可见性探测失败、或服务端反馈与可见清单不一致时用），
    且**只在路径本身被拒时**才切换 —— 「工具被禁 / 不存在」照原样抛出，不做无谓重试。
    """
    if tool_name in META_TOOLS:
        return _mcp_post(ctx, cfg, tool_name, arguments, req_id, path="meta")

    visible = _visible_tools(ctx, cfg)
    is_visible = visible is not None and tool_name in visible
    order = ("direct", "wrapped") if is_visible else ("wrapped", "direct")
    debug_log(ctx, "[%s] --- 路径选择 --- %s：可见=%s（%s）→ 先走 %s"
               % (_now(), tool_name, "是" if is_visible else "否",
                  "未探测" if visible is None else "已探测", order[0]))

    last = None
    for path in order:
        try:
            if path == "wrapped":
                return _mcp_post(ctx, cfg, CALL_TOOL,
                                 {"tool_name": tool_name, "arguments": arguments}, req_id,
                                 path="wrapped")
            return _mcp_post(ctx, cfg, tool_name, arguments, req_id, path="direct")
        except ToolPathUnavailable as e:
            last = e

    raise RuntimeError(
        "乐享 MCP 拒绝了两种调用路径（call_tool 包装与直调都返回 %s）。"
        "通常是该 token 的**工具可见性**变了（allowlist / feature_flag），"
        "请核对 token 与账号权限（可加 --debug 查看 sync.log）" % str(last).strip()[:160])


def query_status(ctx, cfg, task_id):
    resp = mcp_call(ctx, cfg, "import_describe_task", {"task_id": task_id}, req_id=2)
    return resp.get("data", {}) or {}


# ==========================================================================
# 目标目录扫描 + 归一索引
# ==========================================================================

def list_all_children(ctx, cfg, parent_id):
    """拉取目标目录的**直接**子条目（分页拉完）。

    ⚠️ 已知限制：只扫一层。智能文档的子页落在「文档条目之下」（第二层），不在目标目录下，
    因此用子页 URL（含 #page=）做候选时匹配不到 → 可能重复。见 references/pitfalls.md。
    """
    out = []
    page_token = None
    for _ in range(CHILDREN_MAX_PAGES):
        args = {"parent_id": parent_id, "limit": CHILDREN_PAGE_LIMIT}
        if page_token:
            args["page_token"] = page_token
        resp = mcp_call(ctx, cfg, "entry_list_children", args, req_id=3)
        if resp.get("code") != 0:
            raise RuntimeError("entry_list_children 返回 code=%s：%s"
                               % (resp.get("code"), str(resp.get("message"))[:200]))
        data = resp.get("data", {}) or {}
        entries = data.get("entries") or []
        out.extend(entries)
        page_token = data.get("next_page_token")
        # 服务端到末页仍可能回一个 next_page_token → 以「本页为空」作为终止条件
        if not entries or not page_token:
            break
    return out


def build_norm_index(entries, warn=print):
    """建 `norm(source.href.id) → 既有原始 href.id` 映射。

    目标目录里**真实存在同源重复条目**（本次实测就有一对：<entry_id_B> 与 <entry_id_C>，都是同一份智能文档），
    所以朴素的 `{norm: 原始}` 会互相覆盖。处理方式：

      - 按 `created_at` **升序**取**最早**的那条 href.id 作为映射值
        （稳定、可预测：只要最早那条还在，索引值就不变 → 重复跑结果一致）；
      - created_at 相同再按 entry_id 字典序打破平局（避免顺序抖动）；
      - 检测到多个既有条目归一后键相同 → 打印 WARN 并列出冲突的 entry_id。

    为什么取「最早」而不是「最后」：本次实测的重复对成因是「先带 ?scode= 导入 → 后又剥掉 query 导了一次」，
    最早那条恰好是**带完整 query 的原始形态**，回填它最贴近用户第一手粘贴的字符串。
    """
    groups = {}
    for e in entries:
        href = (((e.get("source") or {}).get("href")) or {}).get("id")
        if not href:
            continue
        k = norm(href)
        if not k:
            continue
        try:
            created = int(str(e.get("created_at") or "0"))
        except ValueError:
            created = 0
        groups.setdefault(k, []).append((created, str(e.get("id") or ""), href))

    index = {}
    for k, lst in groups.items():
        lst.sort(key=lambda t: (t[0], t[1]))
        if len(lst) > 1:
            ids = ", ".join("%s (created_at=%s)" % (t[1], t[0]) for t in lst)
            warn("WARN: 目标目录存在 %d 条同源条目（entry_id: %s），归一索引取最早一条 %s"
                 % (len(lst), ids, lst[0][1]))
        index[k] = lst[0][2]
    return index


# ==========================================================================
# 提交清单（保真 + 归一匹配）
# ==========================================================================

def build_plan(cfg, index):
    """返回 (files, plan)。

    失败时返回 (None, (序号, 原始输入, kind, 细节))，由调用方打印错误并 exit 1。

    铁律 1：脚本绝不改写**待提交**字符串。命中归一索引时**回填既有原始字符串**
    （服务端按字节命中 → 幂等）；未命中则用候选原样字符串提交。
    铁律 2：norm() 只用于这里的判等，绝不回传给服务端。
    铁律 3：候选必须是服务端直接接受的形态 —— 本函数**不做**任何 ID 换算。
            REJECTED_KINDS 一律拒收（由调用方打印指引并 exit 1），
            以免把「本机是否装了某个企微侧工具」变成 skill 的隐式前置条件。
    """
    files, plan = [], []
    for i, c in enumerate(cfg["candidates"], 1):
        c = c or {}
        submit_raw = str(c.get("key") or c.get("id") or "")
        kind, label, tested = classify_id(submit_raw)
        if kind is None:
            return None, (i, submit_raw, None, "")

        if kind in REJECTED_KINDS:
            return None, (i, submit_raw, kind, "")

        k = norm(submit_raw)
        if k in index:
            submit, result = index[k], "MATCHED→复用既有"
        else:
            submit, result = submit_raw, "NEW→原样提交"
        plan.append({
            "i": i, "result": result, "submit": submit,
            "kind": kind, "label": label, "tested": tested,
            "note": str(c.get("note") or ""),
        })
        files.append({
            "id": submit,
            # 候选级缺失 → 回退全局；全局也缺失 → True（走 .get 而非 [ ]，避免调用方漏填即 KeyError）
            "include_subpages": bool(c.get("include_subpages", cfg.get("include_subpages", True))),
        })
    return files, plan


def render_plan(plan):
    print("  候选提交保真清单（实际提交字符串 · 匹配结果）:")
    for p in plan:
        print("    #%d %-18s submit=%s" % (p["i"], p["result"], p["submit"]))
        tips = []
        if not p["tested"]:
            tips.append("形态 %s：按同一 provider 路径推断，未实测" % p["label"])
        if p["note"]:
            tips.append(p["note"])
        if tips:
            print("        └ %s" % "；".join(tips))


def render_entries(data):
    entries = data.get("entries") or []
    if not entries:
        return
    print("  条目明细:")
    for e in entries:
        href = (((e.get("source") or {}).get("href")) or {})
        st = e.get("status") or {}
        extra = ("  reason=%s" % st.get("failed_reason")) if st.get("failed_reason") else ""
        print("    - [%s] %s  href.id=%s%s" % (
            st.get("status", "?"), e.get("name", ""), href.get("id", "(none)"), extra))


def render_failures(data):
    """打印 `failed_items[]` —— 顶层 `err_message` 只有一句泛化文案（「导入失败，请查看失败文档」），
    真正的原因（failed_code / failed_reason）在这个数组里。不打印它 = 用户排不了障。"""
    fails = data.get("failed_items") or []
    if not fails:
        return
    print("  未成功项（failed_items）:")
    for f in fails:
        print("    - id=%s" % f.get("id"))
        if f.get("name") and f.get("name") != f.get("id"):
            print("      name=%s" % f.get("name"))
        print("      failed_code=%s" % f.get("failed_code"))
        print("      reason=%s" % f.get("failed_reason"))


def render_stats(data):
    drs = data.get("dry_run_stats")
    if isinstance(drs, dict):
        # 服务端在计数为 0 时**不回该字段**（实测：add_num=None 时 special_num=3；special_num=None 时 add_num=2），
        # 所以 None 等价于 0。不归一会让用户看到 `add_num=None` 一头雾水。
        print("  服务端统计 : dry_run_stats add_num=%s, special_num=%s"
              % (drs.get("add_num") or 0, drs.get("special_num") or 0))
    return drs if isinstance(drs, dict) else None


def render_plan_summary(plan):
    add = sum(1 for p in plan if p["result"].startswith("NEW"))
    matched = len(plan) - add
    print("  将新增 : %d 条（add_num）   已存在 : %d 条（special_num）" % (add, matched))


# ==========================================================================
# 子命令
# ==========================================================================

def do_init(ctx):
    ensure_gitignore()
    if not os.path.isdir(ctx.dir):
        os.makedirs(ctx.dir)
    if os.path.exists(ctx.config_path):
        print("profile 「%s」已存在：%s（未覆盖）" % (ctx.profile, ctx.config_path))
    else:
        with open(ctx.config_path, "w", encoding="utf-8") as f:
            json.dump(CONFIG_TEMPLATE, f, ensure_ascii=False, indent=2)
        print("已创建 profile 「%s」：%s" % (ctx.profile, ctx.config_path))
        print("请编辑该文件，填入 auth.mcp_token / source.candidates / target 后再运行 create。")
        print("获取 mcp_token：访问 %s" % TOKEN_URL)
        print_auth_hint(stream=sys.stdout, indent="")
    print("提示：profiles/ 已写入 .gitignore，切勿提交到任何代码托管平台。")


def do_list():
    if not os.path.isdir(PROFILES_DIR):
        print("尚无任何 profile。运行 `python3 scripts/sync.py init` 创建 default profile。")
        return 0
    names = sorted(d for d in os.listdir(PROFILES_DIR) if os.path.isdir(os.path.join(PROFILES_DIR, d)))
    if not names:
        print("尚无任何 profile。运行 `python3 scripts/sync.py init` 创建 default profile。")
        return 0
    print("可用 profile：")
    for n in names:
        p = os.path.join(PROFILES_DIR, n, "config.json")
        if not os.path.exists(p):
            print("  - %s  (未配置 config.json)" % n)
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                c = json.load(f)
            n_cand = len((c.get("source") or {}).get("candidates") or [])
            print("  - %s  (候选 %d 条 · 目标 %s)"
                  % (n, n_cand, (c.get("target") or {}).get("parent_entry_id") or "?"))
        except Exception as e:
            print("  - %s  (config.json 解析失败：%s)" % (n, e))
    return 0


def _prepare(ctx, cfg):
    """扫目标目录 → 建归一索引 → 生成提交清单。返回 (files, plan, err_code)。"""
    try:
        existing = list_all_children(ctx, cfg, cfg["parent_entry_id"])
    except (AuthError, RuntimeError) as e:
        print("读取目标目录既有条目失败：%s。为保证幂等、避免制造重复，已中止"
              "（未提交任何任务，不可跳过匹配强行提交）。可加 --debug 查看 sync.log" % e, file=sys.stderr)
        return None, None, 1
    print("  既有扫描   : entry_list_children → %d 条" % len(existing))
    index = build_norm_index(existing)
    files, plan = build_plan(cfg, index)
    if files is None:
        i, raw, kind, detail = plan
        if kind in REJECTED_KINDS:
            print("候选 #%d 是微盘分享链接，**本 skill 不做 ID 换算**，已中止"
                  "（未发出导入请求；此前已为构建去重索引读取过目标目录）：\n  %s\n"
                  "  · 分享链接形态服务端实测拒收（failed_reason『非法的 'file_id'』），不能原样提交。\n"
                  "  · 需先把它换成 file_id（`fi…` 长串）再填进 config.json 的候选 —— 这一步在**对话中**\n"
                  "    由 Agent 引导你取得该文件在企微侧的 file_id，本脚本不代跑、不猜测。\n"
                  % (i, raw), file=sys.stderr)
        elif kind is None:
            print("候选 #%d 的 id 形态无法识别：%s。%s" % (i, raw, ID_SHAPE_HINT), file=sys.stderr)
        else:
            print("候选 #%d 的 id 形态不可提交（%s）：%s。%s%s"
                  % (i, kind, raw, ID_SHAPE_HINT,
                     ("\n  " + detail) if detail else ""), file=sys.stderr)
        return None, None, 1
    return files, plan, 0


def _submit_and_poll(ctx, cfg, files, dry_run, wait):
    """建任务 → 写缓存 → 轮询到终态。返回 (data, err_code)。"""
    args = {
        "space_id": cfg["space_id"],
        "type": cfg["type"],
        "parent_entry_id": cfg["parent_entry_id"],
        "files": files,
        "dry_run": bool(dry_run),
        # 显式下发冲突策略（**不可省略**）：服务端默认行为会替换目标目录内容，见 CONFLICT_STRATEGIES。
        "conflict_strategy": cfg["conflict_strategy"],
    }
    try:
        resp = mcp_call(ctx, cfg, "import_create_task", args, req_id=1)
    except (AuthError, RuntimeError) as e:
        print("%s（可加 --debug 查看 sync.log）" % e, file=sys.stderr)
        return None, 1
    if resp.get("code") != 0:
        print("创建任务失败：%s" % json.dumps(resp, ensure_ascii=False)[:400], file=sys.stderr)
        print_auth_hint()
        return None, 1
    task_id = (resp.get("data") or {}).get("task_id")
    if not task_id:
        print("创建任务失败：回包无 task_id。%s" % json.dumps(resp, ensure_ascii=False)[:300], file=sys.stderr)
        return None, 1
    if not dry_run:
        write_cache(ctx, task_id)
    print("  task_id    : %s" % task_id)
    if not wait:
        print("  提示       : --no-wait 已返回；稍后运行 status 查询进度")
        return {"__task_id": task_id}, 0

    data = None
    for n in range(POLL_MAX):
        try:
            data = query_status(ctx, cfg, task_id)
        except (AuthError, RuntimeError) as e:
            print("%s（任务已创建，task_id=%s；可加 --debug 查看 sync.log）" % (e, task_id), file=sys.stderr)
            return None, 1
        st = (data.get("status") or "").strip()
        if n == 0 or st in FINAL_STATES:
            print("  状态       : %s   进度 %s/%s" % (st, data.get("current_num"), data.get("total_num")))
            render_stats(data)
        if st in FINAL_STATES:
            return data, 0
        time.sleep(POLL_INTERVAL)

    print("  超时       : 轮询 %d 次 × %ds 仍未到终态（task_id=%s）。请稍后用 status 查询。"
          % (POLL_MAX, POLL_INTERVAL, task_id), file=sys.stderr)
    return data, 1


def render_strategy(cfg):
    """打印本次下发的冲突处理策略；非安全档给醒目警告。

    ⚠️ `dry_run_stats` 对冲突策略是**盲的**（四路 stats 实测完全一致），所以这里必须显式提示，
    不能让用户误以为「dry-run 通过 = 真跑不会动目的端」。
    """
    s = cfg["conflict_strategy"]
    label = {
        "skip": "跳过已存在的（安全档：不改动目的端既有条目）",
        "replace": "覆盖目的端（服务端以本次提交为准替换该目录内容，既有条目可能被删除）",
        "keep_both": "两者都保留（会产生重复条目）",
    }.get(s, "(未知)")
    print("  冲突策略   : %s —— %s" % (s, label))
    if s != "skip":
        print("  ⚠️ 警告     : 策略「%s」不是安全档。**dry-run 对冲突策略是盲的**，"
              "dry-run 结果不能作为「真跑不动目的端」的依据；请先确认目标目录内容可否被改动。" % s,
              file=sys.stderr)


def do_dry_run(ctx, cfg):
    print("[profile=%s] 预演（dry_run，不写库）" % ctx.profile)
    print("  目标目录   : %s" % (cfg["target_url"] or cfg["parent_entry_id"]))
    print("  候选       : %d 条" % len(cfg["candidates"]))
    render_strategy(cfg)
    files, plan, rc = _prepare(ctx, cfg)
    if rc != 0:
        return rc
    render_plan(plan)
    render_plan_summary(plan)
    data, rc = _submit_and_poll(ctx, cfg, files, dry_run=True, wait=True)
    if rc != 0:
        return rc
    render_entries(data)
    render_failures(data)
    if (data.get("status") or "").strip() == "failed":
        print_auth_hint()
    return 0


def do_create(ctx, cfg, wait=True):
    task_id = read_cache(ctx)
    if task_id:
        try:
            data = query_status(ctx, cfg, task_id)
            st = (data.get("status") or "").strip()
            if st in IN_PROGRESS_STATES:
                print("[profile=%s] 已有进行中任务 %s（%s），本次跳过。" % (ctx.profile, task_id, st))
                return 0
        except (AuthError, RuntimeError) as e:
            print("[warn] 查询缓存任务失败，将创建新任务：%s" % e, file=sys.stderr)

    print("[profile=%s] 提交导入任务（type=%s）" % (ctx.profile, cfg["type"]))
    print("  目标目录   : %s" % (cfg["target_url"] or cfg["parent_entry_id"]))
    render_strategy(cfg)
    files, plan, rc = _prepare(ctx, cfg)
    if rc != 0:
        return rc
    render_plan(plan)

    data, rc = _submit_and_poll(ctx, cfg, files, dry_run=False, wait=wait)
    if rc != 0:
        return rc
    if not wait:
        return 0
    render_entries(data)
    render_failures(data)
    if (data.get("status") or "").strip() == "failed":
        total = data.get("total_num")
        n_fail = len(data.get("failed_items") or [])
        print("导入任务失败：%s（总计 %s 条，其中 %s 条未成功 —— 逐条原因见上「未成功项」）"
              % (data.get("err_message") or "(无)", total, n_fail), file=sys.stderr)
        print_auth_hint()
        return 1
    return 0


def do_status(ctx, cfg):
    task_id = read_cache(ctx)
    if not task_id:
        print("profile 「%s」本地无缓存任务。请先运行 python3 scripts/sync.py create --profile %s"
              % (ctx.profile, ctx.profile), file=sys.stderr)
        return 1
    try:
        data = query_status(ctx, cfg, task_id)
    except (AuthError, RuntimeError) as e:
        print("%s（可加 --debug 查看 sync.log）" % e, file=sys.stderr)
        return 1
    status = (data.get("status") or "unknown").strip()
    print("profile : %s   task_id : %s   状态 : %s   进度 : %s/%s"
          % (ctx.profile, task_id, status, data.get("current_num"), data.get("total_num")))
    render_stats(data)
    render_entries(data)
    render_failures(data)
    if status == "failed":
        print("导入任务失败：%s" % (data.get("err_message") or "(无)"), file=sys.stderr)
        print_auth_hint()
        return 1
    return 0


# ==========================================================================
# 参数解析 / main
# ==========================================================================

USAGE_COMMANDS = ("init", "list", "dry-run", "create", "status", "resolve")


def parse_args(argv):
    global DEBUG
    args = list(argv)

    if "--debug" in args:
        DEBUG = True
        args = [a for a in args if a != "--debug"]

    no_wait = False
    if "--no-wait" in args:
        no_wait = True
        args = [a for a in args if a != "--no-wait"]

    profile = DEFAULT_PROFILE
    if "--profile" in args:
        i = args.index("--profile")
        if i + 1 >= len(args):
            print("错误：--profile 后需跟 profile 名字。", file=sys.stderr)
            sys.exit(2)
        profile = args[i + 1]
        del args[i:i + 2]

    # --strategy：覆盖 config 的 source.conflict_strategy（skip / replace / keep_both）
    strategy = None
    if "--strategy" in args:
        i = args.index("--strategy")
        if i + 1 >= len(args):
            print("错误：--strategy 后需跟取值（%s）。" % "/".join(CONFLICT_STRATEGIES), file=sys.stderr)
            sys.exit(2)
        strategy = args[i + 1].strip().lower()
        del args[i:i + 2]
        if strategy not in CONFLICT_STRATEGIES:
            print("错误：--strategy 取值必须是 %s 之一，收到「%s」。"
                  % (" / ".join(CONFLICT_STRATEGIES), strategy), file=sys.stderr)
            sys.exit(2)

    return {"command": args[0] if args else None, "profile": profile,
            "no_wait": no_wait, "strategy": strategy,
            # resolve 的位置参数（命令名之后的第一个参数）
            "target": args[1] if len(args) > 1 else None}


# --------------------------------------------------------------------------
# 目标目录解析（引导配置用；只读 + 只打印，**绝不改配置**）
# --------------------------------------------------------------------------

_LEXIANG_ENTRY_RE = re.compile(r"/(?:pages|entries)/([0-9a-fA-F]{32})")


def parse_lexiang_entry_id(s):
    """从乐享链接或裸 id 里取出 entry_id；取不到返回 None。"""
    s = (s or "").strip()
    m = _LEXIANG_ENTRY_RE.search(s)
    if m:
        return m.group(1)
    if re.match(r"^[0-9a-fA-F]{32}$", s):
        return s
    return None


def do_resolve(ctx, cfg, target):
    """把「乐享目录链接」解析成可直接填进 config 的 target 片段。

    存在的理由：用户手上只有**页面链接**，拿不到 space_id；而 config 必须填 space_id。
    初始化 / 更新配置时先跑这条，把解析结果写进 config（写配置的动作由 Agent 做，不由脚本做）。

    ⚠️ 本命令**只打印，不写任何配置文件**。
    """
    if not target:
        print("错误：resolve 需要传入乐享目录链接（或 32 位 entry_id）。\n"
              "  例：python3 scripts/sync.py resolve 'https://<租户>.lexiangla.com/pages/<32位id>'",
              file=sys.stderr)
        return 2
    entry_id = parse_lexiang_entry_id(target)
    if not entry_id:
        print("无法从「%s」解析出乐享 entry_id。请贴**页面链接**"
              "（形如 https://<租户>.lexiangla.com/pages/<32位id>）或直接给 32 位 entry_id。"
              % target, file=sys.stderr)
        return 1

    resp = mcp_call(ctx, cfg, "entry_describe_entry", {"entry_id": entry_id}, req_id=9)
    if resp.get("code") != 0:
        print("解析失败：entry_describe_entry 返回 code=%s %s"
              % (resp.get("code"), str(resp.get("message"))[:200]), file=sys.stderr)
        return 1
    e = (resp.get("data") or {}).get("entry") or {}
    space_id = str(e.get("space_id") or "")
    etype = str(e.get("entry_type") or "")
    name = str(e.get("name") or "")
    if not space_id:
        print("解析失败：回包里没有 space_id（可加 --debug 查看 sync.log 的原始回包）。", file=sys.stderr)
        return 1

    url = target.strip() if target.strip().lower().startswith("http") else \
        "%s/pages/%s" % (DEFAULT_LEXIANG_ORIGIN, entry_id)

    print("[profile=%s] 解析乐享目标目录" % ctx.profile)
    print("  名称     : %s" % (name or "(无)"))
    if etype == "folder":
        print("  类型     : folder ✓ 可作为导入目标目录")
    else:
        print("  类型     : %s ⚠️ 不是 folder —— 导入目标通常是**目录**，请确认后再填"
              % (etype or "(未知)"))
    print("  space_id : %s" % space_id)
    print("  entry_id : %s" % entry_id)
    print()
    print("把下面这段填进 profiles/<profile>/config.json 的 target 字段（脚本不会自动改配置）：")
    print(json.dumps({"lexiang_url": url, "space_id": space_id, "parent_entry_id": entry_id},
                     ensure_ascii=False, indent=2))
    return 0


def _prepare_log(ctx, command):
    ensure_gitignore()
    if DEBUG:
        if not os.path.isdir(ctx.dir):
            os.makedirs(ctx.dir)
        debug_log(ctx, "", "########## [%s] scripts/sync.py %s (profile=%s, debug on) ##########"
                  % (_now(), command, ctx.profile))
        print("[debug] 日志写入: %s" % ctx.log_path, file=sys.stderr)


def main(argv):
    # 行缓冲：stdout 被管道接走时默认是全缓冲，会让 stderr 的错误文案跑到 stdout 前面去（顺序错乱）。
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    opts = parse_args(argv)
    command = opts["command"]

    if command == "list":
        return do_list()
    if command == "init":
        do_init(Ctx(opts["profile"]))
        return 0
    if command not in USAGE_COMMANDS:
        print(__doc__)
        return 2

    ctx = Ctx(opts["profile"])
    _prepare_log(ctx, command)

    try:
        cfg = load_config(ctx)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1

    if opts.get("strategy"):
        # CLI 显式指定 > config；已通过白名单校验
        cfg["conflict_strategy"] = opts["strategy"]

    try:
        if command == "dry-run":
            return do_dry_run(ctx, cfg)
        if command == "create":
            return do_create(ctx, cfg, wait=not opts["no_wait"])
        if command == "status":
            return do_status(ctx, cfg)
        if command == "resolve":
            return do_resolve(ctx, cfg, opts.get("target"))
    except AuthError as e:
        print("%s" % e, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已中断。", file=sys.stderr)
        return 1
    except Exception as e:  # 兜底：任何未预期异常都不得以 traceback 形式糊到用户脸上
        print("调用乐享 MCP 失败：%s（可加 --debug 查看 sync.log）" % e, file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
