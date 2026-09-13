"use client";

/** 匹配度报告卡片：评分、命中/缺失关键词、能力差距与改进建议（数据来自 POST /jd/parse）。 */

import { CheckCircle, AlertTriangle, Lightbulb, XCircle } from "lucide-react";

interface MatchReportProps {
  report: {
    overall_score: number;
    matched_keywords: string[];
    missing_keywords: string[];
    skill_gaps: string[];
    suggestions: string[];
  };
}

export default function MatchReport({ report }: MatchReportProps) {
  return (
    <div className="space-y-6">
      {/* Matched Keywords */}
      <div className="glass-card p-4">
        <h4 className="flex items-center gap-2 text-sm font-semibold text-green-400 mb-3">
          <CheckCircle className="w-4 h-4" />
          已匹配技能 ({report.matched_keywords?.length || 0})
        </h4>
        <div className="flex flex-wrap gap-2">
          {report.matched_keywords?.map((kw, i) => (
            <span
              key={i}
              className="px-2.5 py-1 text-xs rounded-full bg-green-500/10 text-green-400 border border-green-500/20"
            >
              {kw}
            </span>
          ))}
        </div>
      </div>

      {/* Missing Keywords */}
      <div className="glass-card p-4">
        <h4 className="flex items-center gap-2 text-sm font-semibold text-red-400 mb-3">
          <XCircle className="w-4 h-4" />
          缺失技能 ({report.missing_keywords?.length || 0})
        </h4>
        <div className="flex flex-wrap gap-2">
          {report.missing_keywords?.map((kw, i) => (
            <span
              key={i}
              className="px-2.5 py-1 text-xs rounded-full bg-red-500/10 text-red-400 border border-red-500/20"
            >
              {kw}
            </span>
          ))}
        </div>
      </div>

      {/* Skill Gaps */}
      {report.skill_gaps?.length > 0 && (
        <div className="glass-card p-4">
          <h4 className="flex items-center gap-2 text-sm font-semibold text-yellow-400 mb-3">
            <AlertTriangle className="w-4 h-4" />
            技能差距
          </h4>
          <ul className="space-y-1.5">
            {report.skill_gaps.map((gap, i) => (
              <li key={i} className="text-sm text-text-secondary flex items-start gap-2">
                <span className="text-yellow-400 mt-1">•</span>
                {gap}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Suggestions */}
      {report.suggestions?.length > 0 && (
        <div className="glass-card p-4 border-accent-cyan/20">
          <h4 className="flex items-center gap-2 text-sm font-semibold text-accent-cyan mb-3">
            <Lightbulb className="w-4 h-4" />
            优化建议
          </h4>
          <ul className="space-y-1.5">
            {report.suggestions.map((s, i) => (
              <li key={i} className="text-sm text-text-secondary flex items-start gap-2">
                <span className="text-accent-cyan mt-1">•</span>
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
