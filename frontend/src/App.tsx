import { Suspense, lazy, useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes, useNavigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { CandidacySentOverlay } from "@/components/celebration/CandidacySentOverlay";
import { DemoMount } from "@/demo/DemoMount";
import LandingPage from "@/pages/LandingPage";
import LoginPage from "@/pages/LoginPage";
import ThesisPage from "@/pages/ThesisPage";
import RankingPage from "@/pages/RankingPage";
import VenturePage from "@/pages/VenturePage";
import IdealEditorPage from "@/pages/IdealEditorPage";
import WeightsPage from "@/pages/WeightsPage";
import OutreachBoardPage from "@/pages/OutreachBoardPage";
import InterviewPage from "@/pages/interview/InterviewPage";
import IntakePage from "@/pages/chosen/IntakePage";
import NotFoundPage from "@/pages/NotFoundPage";

// Lazy: the admin graph pulls d3-force — keep it out of the main bundle.
const AdminPage = lazy(() => import("@/pages/admin/AdminPage"));

/**
 * Outreach emails link to {base}/#/interview/{token} (the upstream app's hash
 * convention) — translate to our path route on boot.
 */
function HashInterviewRedirect() {
  const navigate = useNavigate();
  useEffect(() => {
    const match = window.location.hash.match(/^#\/interview\/([A-Za-z0-9_-]+)/);
    if (match) navigate(`/interview/${match[1]}`, { replace: true });
  }, [navigate]);
  return null;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The mock store mutates in place — always refetch on invalidation,
      // never on window focus (would fight the demo autopilot).
      staleTime: 0,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <HashInterviewRedirect />
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/interview/:token" element={<InterviewPage />} />
          <Route path="/chosen" element={<IntakePage />} />
          <Route
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route path="/thesis" element={<ThesisPage />} />
            <Route path="/t/:thesisId/ranking" element={<RankingPage />} />
            <Route path="/t/:thesisId/venture/:ventureId" element={<VenturePage />} />
            <Route path="/t/:thesisId/ideal" element={<IdealEditorPage />} />
            <Route path="/t/:thesisId/weights" element={<WeightsPage />} />
            <Route path="/t/:thesisId/outreach" element={<OutreachBoardPage />} />
            <Route
              path="/admin"
              element={
                <Suspense fallback={<div className="skeleton mt-gutter-lg h-64 w-full" />}>
                  <AdminPage />
                </Suspense>
              }
            />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
        <CandidacySentOverlay />
        <DemoMount />
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: "var(--paper)",
              color: "var(--ink)",
              border: "1px solid var(--line-strong)",
              borderRadius: "4px",
              fontFamily: '"DM Sans", system-ui, sans-serif',
            },
          }}
        />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
