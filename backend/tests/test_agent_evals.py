"""把离线评测接进 pytest：指标跌破阈值就让测试失败。

这样「Agent 效果是变好还是变差」不靠感觉判断——改完 prompt 或工具，跑一遍测试就有数。
"""

from evals.run_evals import (
    THRESHOLDS,
    check_thresholds,
    evaluate_offline,
    load_dataset,
    score_report_checklist,
)


def test_dataset_is_well_formed():
    dataset = load_dataset()
    assert dataset["version"] >= 1
    for group in ("sections", "keywords", "retrieval", "number_guard"):
        assert dataset[group], f"评测集缺少 {group} 用例"
        assert all(case.get("id") for case in dataset[group]), f"{group} 用例必须有 id"


def test_offline_metrics_meet_thresholds():
    report = evaluate_offline()
    failures = check_thresholds(report)
    assert failures == [], f"离线评测未达标：{failures}"


def test_offline_metrics_have_expected_shape():
    report = evaluate_offline()
    assert set(report["sections"]) >= {"cases", "section_recall", "details"}
    assert report["sections"]["cases"] == len(report["sections"]["details"])
    assert 0.0 <= report["retrieval"]["retrieval_mrr"] <= 1.0
    assert report["keywords"]["cases"] == len(report["keywords"]["details"])


def test_thresholds_can_actually_catch_regressions():
    """阈值表必须真的能卡住退化，而不是形同虚设。"""
    broken = evaluate_offline()
    broken["keywords"]["keyword_accuracy"] = 0.5
    assert check_thresholds(broken) == ["keyword_accuracy = 0.5 < 1.0"]
    assert THRESHOLDS["number_guard_accuracy"] == 1.0


def test_report_checklist_scoring():
    dataset = load_dataset()
    required = dataset["report_checklist"]["required_sections"]
    good = score_report_checklist(dataset["report_checklist"]["sample_report"], required)
    bad = score_report_checklist(dataset["report_checklist"]["failing_report"], required)
    assert good["completeness"] == 1.0 and good["missing"] == []
    assert bad["completeness"] == 0.0
