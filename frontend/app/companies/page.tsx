"use client";

/**
 * 路由：/companies
 *
 * 公司库：浏览内置的 50+ 家公司及常见岗位，点击岗位会带着生成的 JD 草稿跳回工作台。
 */

import { useState, useCallback, useEffect } from "react";
import { companyApi } from "@/lib/api";
import SearchBar from "@/components/company/SearchBar";
import CompanyCard from "@/components/company/CompanyCard";
import { Building2 } from "lucide-react";

interface Company {
  id: number;
  name: string;
  official_site: string | null;
  industry: string | null;
  description: string | null;
  common_positions: string[];
  logo_url: string | null;
}

export default function CompaniesPage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const pageSize = 20;

  const fetchCompanies = useCallback(async (q: string, p: number) => {
    setIsLoading(true);
    try {
      const result: any = await (q ? companyApi.search(q, p, pageSize) : companyApi.list(p, pageSize));
      setCompanies(result.companies);
      setTotal(result.total);
    } catch {
      // Silent
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCompanies(query, 1);
  }, [query]);

  const handleSearch = useCallback((q: string) => {
    setQuery(q);
    setPage(1);
  }, []);

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    fetchCompanies(query, newPage);
  };

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Building2 className="w-6 h-6 text-accent-purple" />
          公司库
        </h1>
        <p className="text-text-secondary text-sm mt-1">浏览知名科技公司及其常见招聘岗位</p>
      </div>

      <div className="mb-6">
        <SearchBar onSearch={handleSearch} isLoading={isLoading} placeholder="搜索公司名称..." />
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <div className="w-8 h-8 border-2 border-accent-purple border-t-transparent rounded-full animate-spin" />
        </div>
      ) : companies.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <Building2 className="w-12 h-12 text-text-muted mx-auto mb-4" />
          <p className="text-text-secondary">未找到匹配的公司</p>
        </div>
      ) : (
        <>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {companies.map((c) => (
              <CompanyCard key={c.id} company={c} />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-8">
              {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                <button
                  key={p}
                  onClick={() => handlePageChange(p)}
                  className={`w-10 h-10 rounded-lg text-sm font-medium transition-all ${
                    p === page
                      ? "bg-gradient-to-r from-purple-600 to-blue-500 text-white"
                      : "glass text-text-secondary hover:text-text-primary"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
