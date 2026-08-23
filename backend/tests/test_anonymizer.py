"""Tests for PII anonymization.

These guard against two failure modes:
1. Clearly-structured PII (phone/email/ID) must be removed.
2. Chinese name detection must NOT destroy body text (the original regex matched
   any surname + 1-2 Han chars anywhere, which wiped words like "张表" / "李工").
"""
from app.services.anonymizer import anonymize_text, REPLACEMENT


def test_contact_info_removed():
    text = "电话：13812345678，邮箱：alice@example.com，身份证：110105199003078888"
    cleaned, pii = anonymize_text(text)
    assert "13812345678" not in cleaned
    assert "alice@example.com" not in cleaned
    assert "110105199003078888" not in cleaned
    assert pii["phones"] and pii["emails"] and pii["id_numbers"]


def test_name_at_line_start_is_replaced():
    text = "张三\n工作经验：负责核心系统"
    cleaned, pii = anonymize_text(text)
    assert cleaned.startswith(REPLACEMENT)
    assert "张三" not in cleaned
    assert pii["names"]


def test_name_after_label_is_replaced():
    text = "姓名：李四\n邮箱：x@y.com"
    cleaned, _ = anonymize_text(text)
    assert "李四" not in cleaned
    assert REPLACEMENT in cleaned


def test_inline_name_false_positive_preserved():
    # "张三" appears inline without a name label -> should be kept (conservative).
    text = "张三\n工作经验：张三负责项目交付"
    cleaned, _ = anonymize_text(text)
    assert cleaned.startswith(REPLACEMENT)  # line-start name removed
    # inline occurrence after a non-name colon must be preserved
    assert "张三负责项目交付" in cleaned


def test_body_text_with_surnames_not_destroyed():
    text = "我们考虑了这个方案，张表显示了结果，李工负责跟进。"
    cleaned, pii = anonymize_text(text)
    assert cleaned == text
    assert pii["names"] == []
