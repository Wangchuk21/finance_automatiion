"use client";

import * as React from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { cn } from "@/lib/utils";

export function AppLayout() {
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false);

  return (
    <div className="min-h-screen bg-background">
      <Sidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} />
      <div
        className={cn(
          "transition-all duration-200 min-h-screen",
          sidebarCollapsed ? "lg:ml-16" : "lg:ml-64"
        )}
      >
        <Header onMenuClick={() => setSidebarCollapsed(!sidebarCollapsed)} asOfDate="Oct 2024" />
        <main className="p-6 max-w-[1400px]">
          <Outlet />
        </main>
      </div>
    </div>
  );
}