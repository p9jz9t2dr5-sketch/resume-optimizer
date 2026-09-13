"use client";

/** 评分圆环：按分数区间换色（与 lib/utils 的 getMatchScoreColor 保持一致）。 */

import { getMatchScoreColor } from "@/lib/utils";

interface ScoreRingProps {
  score: number;
  size?: number;
}

export default function ScoreRing({ score, size = 160 }: ScoreRingProps) {
  const radius = (size - 12) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (score / 100) * circumference;
  const color = getMatchScoreColor(score);

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative" style={{ width: size, height: size }}>
        {/* Background ring */}
        <svg width={size} height={size} className="-rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="rgba(51,65,85,0.3)"
            strokeWidth="10"
          />
          {/* Progress ring */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{ transition: "stroke-dashoffset 1s ease-out" }}
          />
        </svg>
        {/* Score text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-bold" style={{ color }}>
            {score}
          </span>
          <span className="text-xs text-text-muted">匹配度</span>
        </div>
      </div>
      <span className="text-xs text-text-muted" style={{ color }}>
        {score >= 80 ? "优秀匹配" : score >= 60 ? "良好匹配" : score >= 40 ? "部分匹配" : "匹配较低"}
      </span>
    </div>
  );
}
