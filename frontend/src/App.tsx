import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/context/AuthContext";
import { AsOfProvider } from "@/context/AsOfContext";
import { RouteGuard, PublicOnlyGuard } from "@/components/auth/RouteGuard";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { AppLayout } from "@/components/layout/AppLayout";
import { Dashboard } from "@/pages/Dashboard";
import { UploadPage } from "@/pages/UploadPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { ContractsPage } from "@/pages/ContractsPage";
import { RemindersPage } from "@/pages/RemindersPage";
import { CreditCheckPage } from "@/pages/CreditCheckPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { LoginPage } from "@/pages/LoginPage";
import { SetPasswordPage } from "@/pages/SetPasswordPage";

function AppRoutes() {
  return (
    <Routes>
      {/* Public routes */}
      <Route
        path="/login"
        element={
          <PublicOnlyGuard>
            <LoginPage />
          </PublicOnlyGuard>
        }
      />
      <Route path="/set-password" element={<SetPasswordPage />} />

      {/* Protected app routes */}
      <Route element={<RouteGuard />}>
        <Route path="/" element={<AppLayout />}>
          <Route index element={<Dashboard />} />
          <Route
            path="uploads"
            element={
              <RouteGuard allowedRoles={["admin", "finance_uploader"]}>
                <UploadPage />
              </RouteGuard>
            }
          />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="contracts" element={<ContractsPage />} />
          <Route
            path="reminders"
            element={
              <RouteGuard allowedRoles={["admin", "finance_uploader"]}>
                <RemindersPage />
              </RouteGuard>
            }
          />
          <Route path="credit-check" element={<CreditCheckPage />} />
          <Route
            path="settings"
            element={
              <RouteGuard allowedRoles={["admin"]}>
                <SettingsPage />
              </RouteGuard>
            }
          />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AsOfProvider>
          <TooltipProvider>
            <ErrorBoundary>
              <AppRoutes />
            </ErrorBoundary>
            <Toaster />
          </TooltipProvider>
        </AsOfProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
