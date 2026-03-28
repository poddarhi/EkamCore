import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { FlagProvider } from "./contexts/FlagContext";
import MainLayout from "./layouts/MainLayout";
import LoginPage from "./pages/LoginPage";
import NotFoundPage from "./pages/NotFoundPage";
import PlaceholderPage from "./pages/PlaceholderPage";
import type { ReactNode } from "react";

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--color-neutral-50)]">
        <div className="animate-spin h-8 w-8 border-4 border-[var(--color-primary-light)] border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!isAuthenticated) {
    const returnTo = window.location.pathname;
    return <Navigate to={`/login?returnTo=${encodeURIComponent(returnTo)}`} replace />;
  }

  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Navigate to="/today" replace />} />
      <Route
        element={
          <ProtectedRoute>
            <MainLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/today" element={<PlaceholderPage title="Today" />} />
        <Route path="/recap" element={<PlaceholderPage title="Recap" />} />
        <Route path="/search" element={<PlaceholderPage title="Search" />} />
        <Route
          path="/people"
          element={<PlaceholderPage title="People" disabled />}
        />
        <Route
          path="/photos"
          element={<PlaceholderPage title="Photos" disabled />}
        />
        <Route
          path="/files"
          element={<PlaceholderPage title="Files" disabled />}
        />
        <Route
          path="/settings"
          element={<PlaceholderPage title="Settings" />}
        />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <FlagProvider>
          <AppRoutes />
        </FlagProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
