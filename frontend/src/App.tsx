import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/context/AuthContext";
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
          <Route path="uploads" element={<UploadPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="contracts" element={<ContractsPage />} />
          <Route path="reminders" element={<RemindersPage />} />
          <Route path="credit-check" element={<CreditCheckPage />} />
          <Route path="settings" element={<SettingsPage />} />
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
        <TooltipProvider>
          <ErrorBoundary>
            <AppRoutes />
          </ErrorBoundary>
          <Toaster />
        </TooltipProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
