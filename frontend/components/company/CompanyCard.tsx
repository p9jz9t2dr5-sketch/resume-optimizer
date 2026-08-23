"use client";

import { ExternalLink, MapPin, Briefcase } from "lucide-react";

interface CompanyCardProps {
  company: {
    id: number;
    name: string;
    official_site: string | null;
    industry: string | null;
    description: string | null;
    common_positions: string[];
    logo_url: string | null;
  };
}

export default function CompanyCard({ company }: CompanyCardProps) {

  const handlePositionClick = (position: string) => {
    const jdTemplate = `岗位名称：${position}\n公司：${company.name}${company.industry ? `\n行业：${company.industry}` : ""}\n\n请在此粘贴或编辑完整的职位描述（JD）...`;
    window.location.href = "/?jd=" + encodeURIComponent(jdTemplate) + "#upload-section";
  };

  return (
    <div className="glass-card p-5 hover:border-accent-purple/30 transition-all group">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-semibold text-text-primary group-hover:text-accent-cyan transition-colors">
            {company.name}
          </h3>
          {company.industry && (
            <p className="text-xs text-text-muted flex items-center gap-1 mt-0.5">
              <MapPin className="w-3 h-3" />
              {company.industry}
            </p>
          )}
        </div>
        {company.official_site && (
          <a
            href={company.official_site}
            target="_blank"
            rel="noopener noreferrer"
            className="text-text-muted hover:text-accent-cyan transition-colors"
            title="访问官网"
          >
            <ExternalLink className="w-4 h-4" />
          </a>
        )}
      </div>

      {company.description && (
        <p className="text-sm text-text-secondary mb-3 line-clamp-2">
          {company.description}
        </p>
      )}

      {company.common_positions.length > 0 && (
        <div>
          <p className="text-xs text-text-muted flex items-center gap-1 mb-1.5">
            <Briefcase className="w-3 h-3" />
            常见岗位（点击可生成 JD 模板）
          </p>
          <div className="flex flex-wrap gap-1.5">
            {company.common_positions.slice(0, 5).map((pos, i) => (
              <button
                key={i}
                onClick={(e) => {
                  e.stopPropagation();
                  handlePositionClick(pos);
                }}
                className="px-2 py-0.5 text-xs rounded-md bg-purple-500/10 text-accent-purple border border-purple-500/15 hover:bg-purple-500/20 hover:border-purple-500/30 transition-colors cursor-pointer"
              >
                {pos}
              </button>
            ))}
            {company.common_positions.length > 5 && (
              <span className="px-2 py-0.5 text-xs text-text-muted">
                +{company.common_positions.length - 5}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
