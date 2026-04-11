import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { FlagProvider } from "./contexts/FlagContext";
import { NotificationProvider } from "./contexts/NotificationContext";
import MainLayout from "./layouts/MainLayout";
import LoginPage from "./pages/LoginPage";
import NotFoundPage from "./pages/NotFoundPage";
import PlaceholderPage from "./pages/PlaceholderPage";
import TodayPage from "./pages/TodayPage";
import SearchPage from "./pages/SearchPage";
import SystemStatusPage from "./pages/SystemStatusPage";
import RecapPage from "./pages/RecapPage";
import FilesPage from "./pages/FilesPage";
import PhotosPage from "./pages/PhotosPage";
import JobsPage from "./pages/admin/JobsPage";
import StoragePage from "./pages/admin/StoragePage";
import SettingsLayout from "./pages/settings/SettingsLayout";
import GeneralSettings from "./pages/settings/GeneralSettings";
import SourcesSettings from "./pages/settings/SourcesSettings";
import PhotoIntelligenceSettings from "./pages/settings/PhotoIntelligenceSettings";
import AccountSettings from "./pages/settings/AccountSettings";
import AboutSettings from "./pages/settings/AboutSettings";
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
        <Route path="/today" element={<TodayPage />} />
        <Route path="/recap" element={<RecapPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route
          path="/people"
          element={<PlaceholderPage title="People" disabled />}
        />
        <Route path="/photos" element={<PhotosPage />} />
        <Route path="/files" element={<FilesPage />} />
        <Route path="/settings" element={<Navigate to="/settings/general" replace />} />
        <Route path="/settings" element={<SettingsLayout />}>
          <Route path="general" element={<GeneralSettings />} />
          <Route path="sources" element={<SourcesSettings />} />
          <Route path="photo-intelligence" element={<PhotoIntelligenceSettings />} />
          <Route path="account" element={<AccountSettings />} />
          <Route path="about" element={<AboutSettings />} />
        </Route>
        <Route path="/admin/system" element={<SystemStatusPage />} />
        <Route path="/admin/jobs" element={<JobsPage />} />
        <Route path="/admin/storage" element={<StoragePage />} />
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
          <NotificationProvider>
            <AppRoutes />
          </NotificationProvider>
        </FlagProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
