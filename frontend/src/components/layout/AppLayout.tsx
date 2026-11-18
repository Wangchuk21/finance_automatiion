"use client";

import * as React from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { useAsOf } from "@/context/AsOfContext";
import { cn } from "@/lib/utils";

export function AppLayout() {
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false);
  const { asOf } = useAsOf();

  return (
    <div className="min-h-screen bg-background">
      <Sidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} />
      <div
        className={cn(
          "transition-all duration-200 min-h-screen",
          sidebarCollapsed ? "lg:ml-16" : "lg:ml-64"
        )}
      >
        <Header onMenuClick={() => setSidebarCollapsed(!sidebarCollapsed)} />
        <main className="w-full p-6">
          {/* Remount the page whenever the cutoff changes so every API call,
              drill-down and detail panel reloads with the new as-of month. */}
          <Outlet key={asOf || "latest"} />
        </main>
      </div>
    </div>
  );
}