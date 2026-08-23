import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { resumeApi } from "@/lib/api";

export interface Resume {
  id: string;
  version_name: string;
  original_filename: string;
  content: string | null;
  anonymized_text: string | null;
  original_file_url: string | null;
  avatar_url: string | null;
  parsed_data: any;
  created_at: string;
}

interface ResumeState {
  resumes: Resume[];
  selectedResume: Resume | null;
  isLoading: boolean;
  parsingIds: Set<string>;
  uploadResume: (file: File, versionName?: string) => Promise<Resume>;
  fetchResumes: () => Promise<void>;
  selectResume: (resume: Resume | null) => void;
  parseResume: (id: string) => Promise<void>;
  refreshResume: (id: string) => Promise<void>;
  /** Apply an optimized structured resume (from the polish stream) directly to state. */
  applyPolishedStructured: (id: string, structured: any) => void;
  deleteResume: (id: string) => Promise<void>;
  clearResumes: () => Promise<void>;
}

export const useResumeStore = create<ResumeState>()(
  persist(
    (set, get) => ({
      resumes: [],
      selectedResume: null,
      isLoading: false,
      parsingIds: new Set<string>(),

      uploadResume: async (file, versionName) => {
        set({ isLoading: true });
        try {
          const result = (await resumeApi.upload(file, versionName)) as Resume;
          set((s) => ({ resumes: [result, ...s.resumes], selectedResume: result, isLoading: false }));
          // Fire-and-forget structured parsing; don't block the upload success toast
          get().parseResume(result.id).catch(() => {});
          return result;
        } catch (e) {
          set({ isLoading: false });
          throw e;
        }
      },

      fetchResumes: async () => {
        set({ isLoading: true });
        try {
          const data = await resumeApi.list();
          set({ resumes: data.resumes as Resume[], isLoading: false });
        } catch {
          set({ isLoading: false });
        }
      },

      selectResume: (resume) => set({ selectedResume: resume }),

      refreshResume: async (id) => {
        try {
          const updated = (await resumeApi.get(id)) as Resume;
          set((s) => ({
            resumes: s.resumes.map((r) => (r.id === id ? { ...r, ...updated } : r)),
            selectedResume:
              s.selectedResume?.id === id
                ? { ...s.selectedResume, ...updated }
                : s.selectedResume,
          }));
        } catch {
          // Non-fatal: the polished preview still works off the streamed text.
        }
      },

      applyPolishedStructured: (id, structured) =>
        set((s) => ({
          resumes: s.resumes.map((r) =>
            r.id === id
              ? { ...r, parsed_data: { ...(r.parsed_data || {}), structured } }
              : r
          ),
          selectedResume:
            s.selectedResume?.id === id
              ? { ...s.selectedResume, parsed_data: { ...(s.selectedResume.parsed_data || {}), structured } }
              : s.selectedResume,
        })),

      parseResume: async (id) => {
        set((s) => ({ parsingIds: new Set(s.parsingIds).add(id) }));
        try {
          const updated = (await resumeApi.parse(id)) as Resume;
          set((s) => ({
            resumes: s.resumes.map((r) =>
              r.id === id ? { ...r, parsed_data: updated.parsed_data } : r
            ),
            selectedResume:
              s.selectedResume?.id === id
                ? { ...s.selectedResume, parsed_data: updated.parsed_data }
                : s.selectedResume,
          }));
        } finally {
          set((s) => {
            const next = new Set(s.parsingIds);
            next.delete(id);
            return { parsingIds: next };
          });
        }
      },

      deleteResume: async (id) => {
        await resumeApi.deleteResume(id);
        set((s) => ({
          resumes: s.resumes.filter((r) => r.id !== id),
          selectedResume: s.selectedResume?.id === id ? null : s.selectedResume,
        }));
      },

      clearResumes: async () => {
        await resumeApi.clearResumes();
        set({ resumes: [], selectedResume: null });
      },
    }),
    {
      name: "ro-resume-store",
      storage: createJSONStorage(() => localStorage),
      // Defer hydration to a client effect to avoid SSR hydration mismatch
      // (server render has no localStorage; first client render must match).
      skipHydration: true,
      // Only persist the currently selected resume; the list is always
      // re-fetched from the backend so it never goes stale.
      partialize: (s) => ({ selectedResume: s.selectedResume }),
    }
  )
);
