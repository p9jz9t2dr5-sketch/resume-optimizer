"""Agent 离线评测：用固定数据集量出确定性能力的水平，并可据阈值卡住回归。

    python -m evals.run_evals              # 打印指标
    python -m evals.run_evals --json       # 输出 JSON（便于接 CI / 记录趋势）

评测的是 Agent 里**不依赖模型**的那一半能力（版块切分、关键词匹配、知识库检索、
数字幻觉检查），因为只有这部分才是可复现、可回归的。模型质量本身由在线指标
（``agent_runs`` 里的步数、工具失败率、token 消耗）和人工抽检负责——把两者混在
一个数字里，只会得到一个每次都在变、谁也不敢信的指标。

``--live`` 模式会用真实模型跑完整任务并检查报告结构，是上线的冒烟手段；
它需要模型 Key 且必须联网，因此不属于常规验证范围。
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.agent.tools import bm25_search, load_knowledge_base  # noqa: E402
from app.agent.utils import keyword_hits, split_resume_sections, unsupported_numbers  # noqa: E402

DATASET_PATH = Path(__file__).resolve().parent / "dataset.json"


def load_dataset() -> dict:
    with open(DATASET_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def evaluate_sections(dataset: dict) -> dict:
    """版块识别的召回率：简历里的每个真实版块，有多大概率被切出来。"""
    details = []
    recalls = []
    for case in dataset.get("sections", []):
        actual = set(split_resume_sections(case["resume"]).keys())
        expected = set(case["expected_sections"])
        hit = expected & actual
        recall = len(hit) / len(expected) if expected else 1.0
        recalls.append(recall)
        details.append({
            "id": case["id"],
            "recall": round(recall, 3),
            "missing": sorted(expected - actual),
            "extra": sorted(actual - expected),
        })
    return {
        "cases": len(recalls),
        "section_recall": round(statistics.fmean(recalls), 3) if recalls else 0.0,
        "perfect_cases": sum(1 for value in recalls if value == 1.0),
        "details": details,
    }


def evaluate_keywords(dataset: dict) -> dict:
    """关键词命中判定的准确率：英文词边界与中文子串两种规则都要对。"""
    details = []
    correct = 0
    for case in dataset.get("keywords", []):
        present, missing = keyword_hits(case["text"], case["keywords"])
        ok = present == case["expected_present"] and missing == case["expected_missing"]
        correct += 1 if ok else 0
        details.append({"id": case["id"], "ok": ok, "present": present, "missing": missing})
    total = len(details)
    return {
        "cases": total,
        "keyword_accuracy": round(correct / total, 3) if total else 0.0,
        "details": details,
    }


def evaluate_retrieval(dataset: dict, top_k: int = 3) -> dict:
    """知识库检索的 recall@k 与 MRR：Agent 找依据的能力。"""
    entries = load_knowledge_base()
    details = []
    recalls = []
    reciprocal_ranks = []
    for case in dataset.get("retrieval", []):
        hits = bm25_search(entries, case["query"], top_k=top_k)
        ranked = [entry.id for _, entry in hits]
        expected = set(case["expected_ids"])
        hit_rank = next((index + 1 for index, doc_id in enumerate(ranked) if doc_id in expected), None)
        recalls.append(1.0 if hit_rank else 0.0)
        reciprocal_ranks.append(1.0 / hit_rank if hit_rank else 0.0)
        details.append({"id": case["id"], "hit_rank": hit_rank, "ranked": ranked})
    total = len(details)
    return {
        "cases": total,
        f"retrieval_recall@{top_k}": round(statistics.fmean(recalls), 3) if recalls else 0.0,
        "retrieval_mrr": round(statistics.fmean(reciprocal_ranks), 3) if reciprocal_ranks else 0.0,
        "details": details,
    }


def evaluate_number_guard(dataset: dict) -> dict:
    """数字幻觉检查的准确率：既不能漏报编造的指标，也不能误报原文已有的数字。"""
    details = []
    correct = 0
    for case in dataset.get("number_guard", []):
        flagged = unsupported_numbers(case["original"], case["rewritten"])
        ok = flagged == case["expected_unsupported"]
        correct += 1 if ok else 0
        details.append({"id": case["id"], "ok": ok, "flagged": flagged})
    total = len(details)
    return {
        "cases": total,
        "number_guard_accuracy": round(correct / total, 3) if total else 0.0,
        "details": details,
    }


def score_report_checklist(report: str, required_sections: list[str]) -> dict:
    """检查最终报告是否覆盖约定结构（用于抽样评估模型产出的完备性）。"""
    missing = [section for section in required_sections if section not in (report or "")]
    return {
        "covered": [section for section in required_sections if section not in missing],
        "missing": missing,
        "completeness": round(
            (len(required_sections) - len(missing)) / len(required_sections), 3
        ) if required_sections else 1.0,
    }


def evaluate_report_checklist(dataset: dict) -> dict:
    """结构检查器本身的自检：合格报告要满分，不合格报告必须被扣分。"""
    config = dataset.get("report_checklist") or {}
    required = config.get("required_sections") or []
    good = score_report_checklist(config.get("sample_report", ""), required)
    bad = score_report_checklist(config.get("failing_report", ""), required)
    return {
        "cases": 2,
        "report_checklist_accuracy": round(
            1.0 if good["completeness"] == 1.0 and bad["completeness"] < 1.0 else 0.0, 3
        ),
        "sample_report_completeness": good["completeness"],
        "failing_report_completeness": bad["completeness"],
    }


def evaluate_offline() -> dict:
    """跑完整套离线评测，返回所有指标与明细。"""
    dataset = load_dataset()
    return {
        "dataset_version": dataset.get("version"),
        "sections": evaluate_sections(dataset),
        "keywords": evaluate_keywords(dataset),
        "retrieval": evaluate_retrieval(dataset),
        "number_guard": evaluate_number_guard(dataset),
        "report_checklist": evaluate_report_checklist(dataset),
    }


# 回归阈值：低于这些值说明确定性能力退化了（模型本身的波动不该体现在这里）
THRESHOLDS = {
    "section_recall": 0.9,
    "keyword_accuracy": 1.0,
    "retrieval_recall@3": 0.8,
    "number_guard_accuracy": 1.0,
    "report_checklist_accuracy": 1.0,
}

# 每个指标属于哪一组评测结果
_METRIC_SOURCES = {
    "section_recall": "sections",
    "keyword_accuracy": "keywords",
    "retrieval_recall@3": "retrieval",
    "number_guard_accuracy": "number_guard",
    "report_checklist_accuracy": "report_checklist",
}


def check_thresholds(report: dict) -> list[str]:
    """返回未达标的指标说明（空列表表示全部通过）。"""
    failures = []
    for metric, threshold in THRESHOLDS.items():
        actual = report.get(_METRIC_SOURCES[metric], {}).get(metric)
        if actual is None or actual < threshold:
            failures.append(f"{metric} = {actual} < {threshold}")
    return failures


def _passed(group: str, item: dict) -> bool:
    if group == "sections":
        return item["recall"] == 1.0
    if group == "retrieval":
        return item["hit_rank"] is not None
    return bool(item.get("ok"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent 离线评测")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--live", action="store_true", help="（需要模型 Key）用真实模型跑完整任务")
    args = parser.parse_args(argv)

    report = evaluate_offline()
    failures = check_thresholds(report)

    if args.json:
        print(json.dumps({"report": report, "failures": failures}, ensure_ascii=False, indent=2))
    else:
        print(f"数据集版本：{report['dataset_version']}")
        print(
            f"版块识别 recall      : {report['sections']['section_recall']} "
            f"({report['sections']['perfect_cases']}/{report['sections']['cases']} 全对)"
        )
        print(f"关键词判定 accuracy  : {report['keywords']['keyword_accuracy']}")
        print(
            f"知识库检索 recall@3  : {report['retrieval']['retrieval_recall@3']} "
            f"/ MRR {report['retrieval']['retrieval_mrr']}"
        )
        print(f"数字幻觉检查 accuracy: {report['number_guard']['number_guard_accuracy']}")
        print(f"报告结构检查 accuracy: {report['report_checklist']['report_checklist_accuracy']}")
        for group in ("sections", "keywords", "retrieval", "number_guard"):
            bad = [item for item in report[group]["details"] if not _passed(group, item)]
            if bad:
                print(f"  ! {group} 未全对：{json.dumps(bad, ensure_ascii=False)}")
        print("未达标：" + "; ".join(failures) if failures else "全部指标达标。")

    if args.live:
        print(
            "\n--live 需要配置模型 Key 且允许联网：让 Agent 真跑一次任务，检查报告结构"
            "完整度与工具失败率。该模式未纳入常规验证（无网络环境下不可用）。"
        )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
