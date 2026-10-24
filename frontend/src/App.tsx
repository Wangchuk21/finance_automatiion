import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppLayout } from "@/components/layout/AppLayout";
import { Dashboard } from "@/pages/Dashboard";
import { UploadPage } from "@/pages/UploadPage";

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<AppLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="uploads" element={<UploadPage />} />
        <Route path="reports" element={<div className="p-6">Reports page coming soon</div>} />
        <Route path="contracts" element={<div className="p-6">Contracts page coming soon</div>} />
        <Route path="settings" element={<div className="p-6">Settings page coming soon</div>} />
      </Route>
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <TooltipProvider>
        <AppRoutes />
        <Toaster />
      </TooltipProvider>
    </BrowserRouter>
  );
}

export default App;