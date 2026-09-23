"""Agent 层用到的纯函数工具：文本切分、关键词匹配、检索分词、JSON 容错解析等。

这些都是确定性的、不依赖网络与模型的逻辑，因此可以脱离 LLM 单独测试——
``backend/evals/`` 里的离线评测评的就是这一层。
"""

import json
import re

# ---------------------------------------------------------------- 上下文估算


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数。

    中文大约 1 字 ≈ 1 token，英文大约 4 字符 ≈ 1 token，取折中值 ``len/2``。
    这里只要一个量级正确的数字来决定「要不要压缩上下文」，不追求精确
    （精确计数要调 tokenizer，而我们要压缩的正是为了省钱）。
    """
    if not text:
        return 0
    return max(1, len(text) // 2)


def truncate(text: str, limit: int) -> str:
    """截断长文本，并在末尾标注原始长度（便于模型知道信息被截了）。"""
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"…（已截断，原文 {len(text)} 字符）"


# ---------------------------------------------------------------- JSON 容错


def loads_json_loose(text: str) -> dict | None:
    """尽量把模型输出解析成 dict。

    模型常见的三种偏差都要兜住：自带 ```json 围栏、前后有解释性文字、
    尾随逗号。解析不出来返回 None，由调用方决定降级策略。
    """
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        data = json.loads(cleaned)
    except Exception:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            return None
        snippet = cleaned[start : end + 1]
        try:
            data = json.loads(snippet)
        except Exception:
            try:
                data = json.loads(re.sub(r",\s*([}\]])", r"\1", snippet))
            except Exception:
                return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------- 简历切分

# 版块别名 → 规范名。中英文简历都要能认出来。
_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "个人信息": ("个人信息", "基本信息", "联系方式", "个人资料", "basic info", "contact"),
    "求职意向": ("求职意向", "求职目标", "目标岗位", "应聘岗位", "objective", "job intention"),
    "教育背景": ("教育背景", "教育经历", "教育", "education"),
    "工作经历": (
        "工作经历",
        "工作经验",
        "职业经历",
        "实习经历",
        "工作履历",
        "work experience",
        "experience",
        "employment",
        "internship",
    ),
    "项目经历": ("项目经历", "项目经验", "主要项目", "项目", "projects", "project experience"),
    "校园经历": ("校园经历", "社团经历", "学生工作", "社会实践", "campus"),
    "专业技能": ("专业技能", "技能清单", "核心技能", "技术栈", "技能", "skills", "technical skills"),
    "证书荣誉": ("证书荣誉", "证书", "荣誉", "获奖", "奖励", "certificates", "awards", "honors"),
    "语言能力": ("语言能力", "语言", "languages"),
    "自我评价": ("自我评价", "个人总结", "自我描述", "个人简介", "summary", "about me", "profile"),
    "科研成果": ("科研成果", "论文", "科研", "研究成果", "publications", "research"),
}

_DECORATION = "#＊*•·-—– \t　【】[]「」『』:：|"
# 标题与内容同行时，别名之后必须紧跟这些分隔符才算标题（避免「工作经验不足」被误判）。
# 括号类也要算：简历里常见「【求职意向】大模型应用开发」这种写法。
_SEPARATORS = ":：|｜—–-　 \t【】「」『』[]（）()"
_MAX_HEADING_LEN = 24


def _canonical_section(line: str) -> tuple[str, str] | None:
    """判断一行是不是版块标题。

    命中则返回 ``(规范版块名, 标题后同行剩余的正文)``；不是标题返回 None。
    """
    raw = line.strip()
    if not raw:
        return None
    inner = raw.strip(_DECORATION).strip()
    if not inner:
        return None
    lowered = inner.lower()

    for canonical, aliases in _SECTION_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if not lowered.startswith(alias):
                continue
            remainder = inner[len(alias):]
            # 「专业技能：Python、FastAPI」这种标题带内容的写法：
            # 别名后面紧跟分隔符，就认定是标题，同行剩余内容归入该版块。
            if remainder and remainder[0] in _SEPARATORS:
                rest = remainder.strip(_SEPARATORS).strip()
                if rest and len(rest) <= 200:
                    return canonical, rest
                if not rest:
                    return canonical, ""
            # 完全相等（去掉装饰后）也是标题
            if remainder == "":
                return canonical, ""
    return None


def split_resume_sections(text: str) -> dict[str, str]:
    """把简历正文按版块标题切成 ``{版块名: 正文}``（保持原文顺序）。

    识别三类标题：独立成行的中文版块名（可带冒号）、Markdown 标题（#/##/###）、
    以及「教育背景：XX大学」这种标题与内容同行的写法。标题之前的内容归入「头部信息」。
    """
    sections: dict[str, str] = {}
    current = "头部信息"
    sections[current] = []
    pending: list[str] = []

    for line in (text or "").splitlines():
        stripped = line.strip()
        markdown_heading = bool(re.match(r"^\s{0,3}#{1,6}\s+", line))
        match = _canonical_section(stripped)

        if match is None and markdown_heading:
            # Markdown 标题但不在已知版块里：出现在第一个真实版块之前的多半是人名
            # （「# 张三」），归入头部信息；之后的按标题本身命名，保证内容不丢。
            title = stripped.strip(_DECORATION).strip()
            already_started = any(name != "头部信息" for name in sections)
            if title and len(title) <= _MAX_HEADING_LEN and already_started:
                canonical, rest = title, ""
            else:
                sections[current].append(line)
                continue
        elif match is not None:
            canonical, rest = match
        else:
            # 普通正文行（含空行）先攒着，遇到下一个标题时再归入当前版块。
            pending.append(line)
            continue

        # 落到这里说明遇到了新标题
        if pending:
            sections[current].extend(pending)
            pending = []
        name = canonical
        suffix = 2
        while name in sections:  # 同名版块出现多次，加序号保留全部内容
            name = f"{canonical}({suffix})"
            suffix += 1
        sections[name] = [rest] if rest else []
        current = name

    sections[current].extend(pending)

    return {
        name: "\n".join(lines).strip()
        for name, lines in sections.items()
        if "\n".join(lines).strip()
    }


# ---------------------------------------------------------------- 关键词匹配

_ASCII_WORD = re.compile(r"[a-zA-Z0-9]")


def _contains_keyword(text_lower: str, keyword: str) -> bool:
    """判断关键词是否出现。

    纯英文/数字关键词用「词边界」匹配，避免 ``Go`` 命中 ``Google``、
    ``C`` 命中 ``CSS``；含中文的关键词直接做子串匹配。
    """
    kw = keyword.strip()
    if not kw:
        return False
    kw_lower = kw.lower()
    if _ASCII_WORD.search(kw) and not re.search(r"[\u4e00-\u9fff]", kw):
        pattern = r"(?<![a-z0-9+#._-])" + re.escape(kw_lower) + r"(?![a-z0-9+#._-])"
        return re.search(pattern, text_lower) is not None
    return kw_lower in text_lower


def keyword_hits(text: str, keywords: list[str]) -> tuple[list[str], list[str]]:
    """返回 ``(命中的关键词, 缺失的关键词)``（去重、保持输入顺序）。"""
    text_lower = (text or "").lower()
    present: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()
    for keyword in keywords or []:
        if not isinstance(keyword, str):
            continue
        kw = keyword.strip()
        key = kw.lower()
        if not kw or key in seen:
            continue
        seen.add(key)
        (present if _contains_keyword(text_lower, kw) else missing).append(kw)
    return present, missing


# ---------------------------------------------------------------- 幻觉数字检查

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?%?")


def _normalize_number(raw: str) -> str:
    return raw.replace(",", "").rstrip("%")


def unsupported_numbers(original: str, rewritten: str) -> list[str]:
    """找出改写稿里「原文没有」的数字。

    这是对「简历不能编造量化成果」这条硬约束的确定性检查：模型很爱把
    「参与优化」改写成「性能提升 40%」，而 40% 原文里根本不存在。
    只做数字比对，判错的可能性很低（判漏是有可能的，所以是「兜底」而非「保证」）。
    """
    original_numbers = {_normalize_number(m) for m in _NUMBER.findall(original or "")}
    suspicious: list[str] = []
    for match in _NUMBER.findall(rewritten or ""):
        normalized = _normalize_number(match)
        if normalized and normalized not in original_numbers and normalized not in suspicious:
            suspicious.append(normalized)
    return suspicious


# ---------------------------------------------------------------- 检索分词

_ASCII_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#._+-]*")
_CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")


def tokenize_for_search(text: str) -> list[str]:
    """切成检索用词：英文按词、中文按二元组（中文二元组比单字噪声小很多）。"""
    lowered = (text or "").lower()
    tokens = _ASCII_TOKEN.findall(lowered)
    cjk = _CJK_CHAR.findall(lowered)
    tokens.extend(cjk[index] + cjk[index + 1] for index in range(len(cjk) - 1))
    if len(cjk) == 1:
        tokens.append(cjk[0])
    return tokens
