"use client";

import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Search, User, LogOut, Calendar, KeyRound } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { formatAsOfLabel, useAsOf } from "@/context/AsOfContext";
import { ChangePasswordDialog } from "@/components/auth/ChangePasswordDialog";
import { NotificationBell } from "@/components/notifications/NotificationBell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip";

interface HeaderProps {
  onMenuClick: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const [searchQuery, setSearchQuery] = React.useState("");
  const [changePasswordOpen, setChangePasswordOpen] = React.useState(false);
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { asOf, label, options, canSelect, loading, setAsOf } = useAsOf();

  const handleSignOut = async () => {
    try {
      await logout();
    } finally {
      navigate("/login", { replace: true });
    }
  };

  return (
    <header className="sticky top-0 z-30 h-16 border-b border-border bg-card/80 backdrop-blur-sm">
      <div className="flex h-full items-center justify-between px-4">
        {/* Left: Menu button + Page title (passed via children in practice) */}
        <div className="flex items-center gap-4">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" onClick={onMenuClick} aria-label="Toggle menu">
                  <Search className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">Toggle Menu</TooltipContent>
            </Tooltip>
          </TooltipProvider>

          {/* Global Search */}
          <div className="hidden sm:block w-72">
            <Input
              placeholder="Search reference, customer, CID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-9"
            />
          </div>
        </div>

        {/* Right: As-of date + User menu */}
        <div className="flex items-center gap-3">
          {/* As-of month cutoff */}
          {canSelect ? (
            <div className="flex items-center gap-2 rounded-lg px-2.5 py-1 bg-neutral-light/50">
              <Calendar className="h-4 w-4 shrink-0 text-text-secondary" />
              <select
                aria-label="As-of month"
                title="Show installments due on or before this month"
                value={asOf || ""}
                disabled={loading}
                onChange={(event) => setAsOf(event.target.value || null)}
                className="h-7 max-w-[150px] cursor-pointer bg-transparent text-sm font-medium text-text-primary focus:outline-none disabled:cursor-wait disabled:opacity-60"
              >
                <option value="">Latest (all months)</option>
                {options.map((month) => (
                  <option key={month} value={month}>
                    {formatAsOfLabel(month)}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-2 rounded-lg px-3 py-1.5 bg-neutral-light/50 text-sm text-text-secondary">
                    <Calendar className="h-4 w-4" />
                    <span>As of {label}</span>
                  </div>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  Figures include installments due on or before {label}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}

          {/* Notifications */}
          <NotificationBell />

          {/* User Menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="relative h-8 w-8 rounded-full">
                <div className="h-8 w-8 rounded-full bg-primary flex items-center justify-center">
                  <User className="h-4 w-4 text-primary-foreground" />
                </div>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuItem className="px-2 py-1 text-sm font-medium text-text-secondary">
                {user?.full_name || user?.username || "User"}
              </DropdownMenuItem>
              <DropdownMenuItem className="px-2 py-1 text-sm text-text-secondary">
                {user?.email || ""}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="px-2 py-1 text-sm" onClick={() => navigate("/settings")}>
                Profile
              </DropdownMenuItem>
              <DropdownMenuItem className="px-2 py-1 text-sm" onClick={() => navigate("/settings")}>
                Settings
              </DropdownMenuItem>
              <DropdownMenuItem
                className="px-2 py-1 text-sm"
                onSelect={() => setChangePasswordOpen(true)}
              >
                <KeyRound className="mr-2 h-4 w-4" /> Change password
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="px-2 py-1 text-sm text-critical" onClick={handleSignOut}>
                <LogOut className="mr-2 h-4 w-4" /> Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <ChangePasswordDialog open={changePasswordOpen} onOpenChange={setChangePasswordOpen} />
    </header>
  );
}