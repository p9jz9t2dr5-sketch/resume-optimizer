import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

// "Workbench" holds the in-progress optimizer state on the home page:
// the pasted JD, the match analysis result, and the polished resume.
// It is persisted to localStorage so navigating away from / or refreshing
// the page does NOT force the user to re-submit the resume and JD.
interface WorkbenchState {
  jdText: string;
  jdResult: any;
  matchReport: any;
  polishedContent: string;
  setJdText: (v: string) => void;
  setJdResult: (v: any) => void;
  setMatchReport: (v: any) => void;
  // Accept either a plain string (overwrite) or an updater function
  // (prev => next), matching the React useState API. This lets callers
  // safely accumulate streaming chunks without a get-then-set race.
  setPolishedContent: (v: string | ((prev: string) => string)) => void;
  clear: () => void;
}

export const useWorkbenchStore = create<WorkbenchState>()(
  persist(
    (set) => ({
      jdText: "",
      jdResult: null,
      matchReport: null,
      polishedContent: "",
      setJdText: (v) => set({ jdText: v }),
      setJdResult: (v) => set({ jdResult: v }),
      setMatchReport: (v) => set({ matchReport: v }),
      setPolishedContent: (v) =>
        set((s) => ({
          polishedContent:
            typeof v === "function"
              ? (v as (prev: string) => string)(s.polishedContent ?? "")
              : typeof v === "string"
              ? v
              : "",
        })),
      clear: () => set({ jdText: "", jdResult: null, matchReport: null, polishedContent: "" }),
    }),
    {
      name: "ro-workbench-store",
      storage: createJSONStorage(() => localStorage),
      // Defer hydration to a client effect to avoid SSR hydration mismatch.
      skipHydration: true,
      partialize: (s) => ({
        jdText: s.jdText,
        jdResult: s.jdResult,
        matchReport: s.matchReport,
        polishedContent: s.polishedContent,
      }),
      // 清理历史脏数据：旧版本可能把非字符串（对象/函数）写进 polishedContent，
      // 直接交给 MarkdownText 会抛 "text.split is not a function"。恢复时兜底重置。
      merge: (persisted, current) => {
        const p = (persisted || {}) as Partial<WorkbenchState>;
        if (typeof p.polishedContent !== "string") {
          p.polishedContent = "";
        }
        return { ...current, ...p };
      },
    }
  )
);
