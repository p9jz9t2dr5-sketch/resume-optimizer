"""PII 脱敏与身份字段抽取。

- ``anonymize_text``：把姓名、手机号、邮箱、身份证、地址替换成 [已隐藏]，
  用于「发给模型之前」的唯一入口（见 ``resume_service.resume_text_for_llm``）
- ``extract_identity``：从**原文**里抽出姓名/手机/邮箱/求职意向/所在地，
  用于生成之后的**本地回填**——模型看到的是脱敏文本，交付物仍保留真实联系方式

设计上是「宁少勿多」：只在明确的姓名标签或行首识别姓名，避免把正文里的常见字误伤。
规则匹配无法做到 100% 召回，所以对外表述必须写「尽力脱敏」，不能写「绝不泄露」。
"""

import re
from typing import Tuple


# Chinese name patterns: common surnames + given names
CN_SURNAMES = {
    "李", "王", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴",
    "徐", "孙", "胡", "朱", "高", "林", "何", "郭", "马", "罗",
    "梁", "宋", "郑", "谢", "韩", "唐", "冯", "于", "董", "萧",
    "程", "曹", "袁", "邓", "许", "傅", "沈", "曾", "彭", "吕",
    "苏", "卢", "蒋", "蔡", "贾", "丁", "魏", "薛", "叶", "阎",
    "余", "潘", "杜", "戴", "夏", "钟", "汪", "田", "任", "姜",
    "范", "方", "石", "姚", "谭", "廖", "邹", "熊", "金", "陆",
    "郝", "孔", "白", "崔", "康", "毛", "邱", "秦", "江", "史",
    "顾", "侯", "邵", "孟", "龙", "万", "段", "雷", "钱", "汤",
    "尹", "黎", "易", "常", "武", "乔", "贺", "赖", "龚", "文",
}

REPLACEMENT = "[已隐藏]"

# --- 共享正则：脱敏与身份回填必须用同一套规则，避免两边判断不一致 ---
ID_PATTERN = r'\b\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b'
PHONE_PATTERN = r'1[3-9]\d[-\s]?\d{4}[-\s]?\d{4}'
# 回填用的严格版本：18 位身份证里也含 11 位数字串，必须用边界挡住
PHONE_STRICT_PATTERN = r'(?<!\d)1[3-9]\d[-\s]?\d{4}[-\s]?\d{4}(?!\d)'
EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
ADDRESS_PATTERN = (
    r'(?:[一-龥]{2,}(?:省|市|自治区|特别行政区))'
    r'(?:[一-龥]{2,}(?:市|区|县|镇))?'
    r'(?:[一-龥]{2,}(?:街道|路|巷|弄|号|楼|室|单元|村|乡|镇))'
    r'(?:\d{1,6}[号室层楼栋座]?)?'
    r'|'
    r'(?:[一-龥]{2,}(?:区|县|镇))'
    r'(?:[一-龥]{2,}(?:街道|路|巷|弄|号|楼|室|单元|村|乡))\d{0,6}[号室]?'
)
SURNAME_PATTERN = "|".join(CN_SURNAMES)
NAME_CORE = rf"(?:{SURNAME_PATTERN})\s*[一-龥]{{1,2}}"
# 简历 OCR 输出是 Markdown：姓名常写成 "# 张三" / "**张三**" / "- 张三"。
# 只认行首会漏掉这些形式（线上扫描件冒烟时确实漏过），所以允许常见装饰前缀。
NAME_LINE_PATTERN = (
    rf"(?m)^(?P<indent>\s*)"
    rf"(?P<prefix>(?:\*\*|#{{1,6}}[ \t]*|[-*•>][ \t]+)?)"
    rf"(?P<name>{NAME_CORE})"
    rf"(?P<suffix>\*\*)?"
)
NAME_LABEL_PATTERN = (
    rf"(?P<label>姓名[:：]?\s*|名字[:：]?\s*|Name\s*[:：]?\s*)(?P<name>{NAME_CORE})"
)
JOB_TITLE_PATTERN = r'(?:求职意向|应聘岗位|目标岗位|求职目标)[:：]\s*([^\n]{1,40})'
LOCATION_PATTERN = r'(?:现居地|所在地|所在城市|城市|居住地|现居)[:：]\s*([^\n，,；;]{1,30})'


def anonymize_text(text: str) -> Tuple[str, dict]:
    """Remove PII from resume text. Returns (anonymized_text, pii_map)."""
    pii_found: dict[str, list[str]] = {
        "phones": [],
        "emails": [],
        "names": [],
        "addresses": [],
        "id_numbers": [],
    }

    cleaned = text

    # Detect ID numbers BEFORE phones: an 18-digit ID contains an 11-digit run that
    # the mobile-phone pattern would otherwise match and corrupt (breaking ID detection).
    pii_found["id_numbers"] = re.findall(ID_PATTERN, cleaned)
    cleaned = re.sub(ID_PATTERN, REPLACEMENT, cleaned)

    pii_found["phones"] = re.findall(PHONE_PATTERN, cleaned)
    cleaned = re.sub(PHONE_PATTERN, REPLACEMENT, cleaned)

    pii_found["emails"] = re.findall(EMAIL_PATTERN, cleaned)
    cleaned = re.sub(EMAIL_PATTERN, REPLACEMENT, cleaned)

    pii_found["addresses"] = re.findall(ADDRESS_PATTERN, cleaned)
    cleaned = re.sub(ADDRESS_PATTERN, REPLACEMENT, cleaned)

    # Chinese names — conservative detection to reduce false positives.
    # Matching a surname + 1-2 Han chars *anywhere* destroys body text (e.g. "李" in
    # "我们考虑" or "张" in "张表"). We only treat it as a name when it appears at the
    # start of a line, or right after a name label / colon (姓名：/Name:/：).
    found_names: list[str] = []
    for pattern in (NAME_LINE_PATTERN, NAME_LABEL_PATTERN):
        found_names.extend(
            match.group("name") for match in re.finditer(pattern, cleaned, flags=re.MULTILINE)
        )

    cleaned = re.sub(
        NAME_LINE_PATTERN,
        lambda m: (
            f"{m.group('indent')}{m.group('prefix')}{REPLACEMENT}{m.group('suffix') or ''}"
        ),
        cleaned,
        flags=re.MULTILINE,
    )
    cleaned = re.sub(
        NAME_LABEL_PATTERN,
        lambda m: f"{m.group('label')}{REPLACEMENT}",
        cleaned,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    pii_found["names"] = found_names

    return cleaned, pii_found


def extract_identity(text: str) -> dict[str, str]:
    """从**原文**抽取可本地回填的身份字段（不外发、不落日志）。

    只返回简历里确实出现的字段；缺失的键不出现，调用方据此决定是否回填。
    """
    if not text:
        return {}

    identity: dict[str, str] = {}
    for field, pattern in (
        ("phone", PHONE_STRICT_PATTERN),
        ("email", EMAIL_PATTERN),
        ("job_title", JOB_TITLE_PATTERN),
        ("location", LOCATION_PATTERN),
    ):
        match = re.search(pattern, text, flags=re.MULTILINE)
        if match:
            value = (match.group(1) if match.groups() else match.group(0)).strip()
            if value:
                identity[field] = value

    # 姓名优先取标签形式（姓名：张三），其次取行首（第一行通常就是姓名）
    for pattern in (NAME_LABEL_PATTERN, NAME_LINE_PATTERN):
        match = re.search(pattern, text, flags=re.MULTILINE | re.IGNORECASE)
        if match:
            identity["name"] = match.group("name").strip()
            break

    return identity
