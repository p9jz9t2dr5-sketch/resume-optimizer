import re
import os
from typing import List, Tuple


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
    # 3. ID card numbers (18 digits)
    id_pattern = r'\b\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b'
    pii_found["id_numbers"] = re.findall(id_pattern, cleaned)
    cleaned = re.sub(id_pattern, REPLACEMENT, cleaned)

    # 1. Phone numbers (Chinese mobile: 1[3-9]xxxxxxxxx, with optional separators)
    phone_pattern = r'1[3-9]\d[-\s]?\d{4}[-\s]?\d{4}'
    pii_found["phones"] = re.findall(phone_pattern, cleaned)
    cleaned = re.sub(phone_pattern, REPLACEMENT, cleaned)

    # 2. Emails
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    pii_found["emails"] = re.findall(email_pattern, cleaned)
    cleaned = re.sub(email_pattern, REPLACEMENT, cleaned)

    # 4. Addresses — require at least one clear address marker
    addr_pattern = (
        r'(?:[一-龥]{2,}(?:省|市|自治区|特别行政区))'
        r'(?:[一-龥]{2,}(?:市|区|县|镇))?'
        r'(?:[一-龥]{2,}(?:街道|路|巷|弄|号|楼|室|单元|村|乡|镇))'
        r'(?:\d{1,6}[号室层楼栋座]?)?'
        r'|'
        r'(?:[一-龥]{2,}(?:区|县|镇))'
        r'(?:[一-龥]{2,}(?:街道|路|巷|弄|号|楼|室|单元|村|乡))\d{0,6}[号室]?'
    )
    pii_found["addresses"] = re.findall(addr_pattern, cleaned)
    cleaned = re.sub(addr_pattern, REPLACEMENT, cleaned)

    # 5. Chinese names — conservative detection to reduce false positives.
    # Matching a surname + 1-2 Han chars *anywhere* destroys body text (e.g. "李" in
    # "我们考虑" or "张" in "张表"). We only treat it as a name when it appears at the
    # start of a line, or right after a name label / colon (姓名：/Name:/：).
    surname_pattern = "|".join(CN_SURNAMES)
    name_core = rf"(?:{surname_pattern})\s*[一-龥]{{1,2}}"

    line_start_pattern = rf"(?m)^(?P<indent>\s*)(?P<name>{name_core})"
    label_pattern = rf"(?P<label>姓名[:：]?\s*|名字[:：]?\s*|Name\s*[:：]?\s*)(?P<name>{name_core})"

    found_names: list[str] = []
    for pat, flags in (
        (line_start_pattern, re.MULTILINE),
        (label_pattern, re.MULTILINE | re.IGNORECASE),
    ):
        found_names.extend(m.group("name") for m in re.finditer(pat, cleaned, flags=flags))

    cleaned = re.sub(
        line_start_pattern,
        lambda m: f"{m.group('indent')}{REPLACEMENT}",
        cleaned,
        flags=re.MULTILINE,
    )
    cleaned = re.sub(
        label_pattern,
        lambda m: f"{m.group('label')}{REPLACEMENT}",
        cleaned,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    pii_found["names"] = found_names

    return cleaned, pii_found
