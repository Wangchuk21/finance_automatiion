"use client";

import * as React from "react";
import { Search, Bell, User, LogOut, Calendar } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";

interface HeaderProps {
  onMenuClick: () => void;
  asOfDate?: string;
  onAsOfDateChange?: (date: string) => void;
}

export function Header({ onMenuClick, asOfDate, onAsOfDateChange }: HeaderProps) {
  const [searchQuery, setSearchQuery] = React.useState("");

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
          {/* As-of Date */}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex items-center gap-2 rounded-lg px-3 py-1.5 bg-neutral-light/50 text-sm text-text-secondary">
                  <Calendar className="h-4 w-4" />
                  <span>{asOfDate || "Select date"}</span>
                </div>
              </TooltipTrigger>
              <TooltipContent side="bottom">As-of date for reports</TooltipContent>
            </Tooltip>
          </TooltipProvider>

          {/* Notifications */}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" aria-label="Notifications">
                  <Bell className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">Notifications</TooltipContent>
            </Tooltip>
          </TooltipProvider>

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
                Admin User
              </DropdownMenuItem>
              <DropdownMenuItem className="px-2 py-1 text-sm text-text-secondary">
                admin@example.com
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="px-2 py-1 text-sm">Profile</DropdownMenuItem>
              <DropdownMenuItem className="px-2 py-1 text-sm">Settings</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="px-2 py-1 text-sm text-critical" onClick={() => {}}>
                <LogOut className="mr-2 h-4 w-4" /> Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
}