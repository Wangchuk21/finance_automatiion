"use client";

import * as React from "react";
import Link from "react-router-dom";
import { useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  FileText,
  Upload,
  Settings,
  BarChart2,
  Menu,
  X,
  ChevronLeft,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

const navigation = [
  { name: "Dashboard", href: "/", icon: LayoutDashboard },
  { name: "Reports", href: "/reports", icon: BarChart2 },
  { name: "Contracts", href: "/contracts", icon: FileText },
  { name: "Uploads", href: "/uploads", icon: Upload },
  { name: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const location = useLocation();

  return (
    <TooltipProvider>
      <aside
        className={cn(
          "fixed left-0 top-0 z-40 h-full border-r border-border bg-card transition-all duration-200",
          collapsed ? "w-16" : "w-64"
        )}
      >
        <div className="flex h-full flex-col">
          {/* Logo / Brand */}
          <div className={cn("flex h-16 items-center justify-between px-4 border-b border-border", collapsed && "justify-center")}>
            {!collapsed && (
              <Link to="/" className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
                  <BarChart2 className="h-5 w-5 text-primary-foreground" />
                </div>
                <span className="font-semibold text-text-primary">Finance</span>
              </Link>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={onToggle}
              className={cn("h-8 w-8", collapsed && "ml-auto")}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {collapsed ? <ChevronLeft className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </Button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
            {navigation.map((item) => {
              const isActive = location.pathname === item.href || (item.href !== "/" && location.pathname.startsWith(item.href));
              return (
                <Tooltip key={item.name} disabled={!collapsed}>
                  <TooltipTrigger asChild>
                    <Link
                      to={item.href}
                      className={cn(
                        "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                        isActive
                          ? "bg-primary/10 text-primary"
                          : "text-text-secondary hover:bg-neutral-light hover:text-text-primary",
                        collapsed && "justify-center"
                      )}
                    >
                      <item.icon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
                      {!collapsed && <span>{item.name}</span>}
                    </Link>
                  </TooltipTrigger>
                  <TooltipContent side="right">
                    <p>{item.name}</p>
                  </TooltipContent>
                </Tooltip>
              );
            })}
          </nav>

          {/* Footer */}
          <div className="p-4 border-t border-border">
            {!collapsed && (
              <div className="text-xs text-text-secondary text-center">
                Finance Automation v0.1.0
              </div>
            )}
          </div>
        </div>
      </aside>
    </TooltipProvider>
  );
}