"use client";

import * as React from "react";
import { useNavigate } from "react-router-dom";
import {
  Bell,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCheck,
  Send,
  ExternalLink,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { notificationsApi, type InAppNotificationItem } from "@/lib/api";
import { cn } from "@/lib/utils";

export function NotificationBell() {
  const [unreadCount, setUnreadCount] = React.useState(0);
  const [items, setItems] = React.useState<InAppNotificationItem[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [isOpen, setIsOpen] = React.useState(false);
  const navigate = useNavigate();

  const fetchNotifications = React.useCallback(async () => {
    try {
      setLoading(true);
      const data = await notificationsApi.getInApp();
      setUnreadCount(data.unread_count);
      setItems(data.items);
    } catch (err) {
      // Silently catch to not disrupt top bar
      console.error("Failed to load notifications:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Poll notifications periodically (every 60s)
  React.useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 60000);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  const handleOpenChange = (open: boolean) => {
    setIsOpen(open);
    if (open) {
      fetchNotifications();
    }
  };

  const handleMarkAllRead = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await notificationsApi.markInAppRead();
      setUnreadCount(0);
      setItems((prev) => prev.map((item) => ({ ...item, status: "read" })));
    } catch (err) {
      console.error("Failed to mark notifications read:", err);
    }
  };

  const handleItemClick = (item: InAppNotificationItem) => {
    if (item.status === "unread") {
      notificationsApi.markInAppRead([item.id]).catch(() => {});
      setUnreadCount((prev) => Math.max(0, prev - 1));
      setItems((prev) =>
        prev.map((i) => (i.id === item.id ? { ...i, status: "read" } : i))
      );
    }
    if (item.link) {
      setIsOpen(false);
      navigate(item.link);
    }
  };

  const renderIcon = (type: string) => {
    switch (type) {
      case "critical":
        return <AlertCircle className="h-4 w-4 text-critical shrink-0" />;
      case "warning":
        return <AlertTriangle className="h-4 w-4 text-warning shrink-0" />;
      case "success":
        return <CheckCircle2 className="h-4 w-4 text-success shrink-0" />;
      default:
        return <Info className="h-4 w-4 text-primary shrink-0" />;
    }
  };

  const formatTimestamp = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      const now = new Date();
      const diffMs = now.getTime() - d.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins < 1) return "Just now";
      if (diffMins < 60) return `${diffMins}m ago`;
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours}h ago`;
      return d.toLocaleDateString();
    } catch {
      return "";
    }
  };

  return (
    <DropdownMenu open={isOpen} onOpenChange={handleOpenChange}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative text-text-secondary hover:text-text-primary"
          aria-label="Open notifications"
        >
          <Bell className="h-4 w-4" />
          {unreadCount > 0 && (
            <span className="absolute top-1.5 right-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-critical text-[10px] font-bold text-white shadow-sm ring-2 ring-card animate-pulse">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent
        align="end"
        className="w-80 sm:w-96 p-0 shadow-lg border-border"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-card">
          <div className="flex items-center gap-2">
            <h4 className="font-semibold text-sm text-text-primary">Notifications</h4>
            {unreadCount > 0 && (
              <Badge variant="neutral" className="text-xs px-1.5 py-0">
                {unreadCount} new
              </Badge>
            )}
          </div>
          {unreadCount > 0 && (
            <button
              onClick={handleMarkAllRead}
              className="text-xs text-primary hover:underline flex items-center gap-1 font-medium"
            >
              <CheckCheck className="h-3 w-3" />
              Mark all read
            </button>
          )}
        </div>

        {/* Notifications List */}
        <div className="max-h-80 overflow-y-auto divide-y divide-border/50">
          {items.length === 0 ? (
            <div className="p-6 text-center text-sm text-text-secondary">
              {loading ? "Loading alerts..." : "No recent notifications."}
            </div>
          ) : (
            items.map((item) => (
              <div
                key={item.id}
                onClick={() => handleItemClick(item)}
                className={cn(
                  "p-3.5 transition-colors cursor-pointer flex gap-3 text-left",
                  item.status === "unread"
                    ? "bg-primary/5 hover:bg-primary/10"
                    : "hover:bg-neutral-light/50"
                )}
              >
                <div className="mt-0.5">{renderIcon(item.type)}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <p
                      className={cn(
                        "text-xs font-medium truncate",
                        item.status === "unread"
                          ? "text-text-primary font-semibold"
                          : "text-text-secondary"
                      )}
                    >
                      {item.title}
                    </p>
                    <span className="text-[10px] text-text-secondary shrink-0">
                      {formatTimestamp(item.created_at)}
                    </span>
                  </div>
                  <p className="text-xs text-text-secondary mt-0.5 leading-relaxed line-clamp-2">
                    {item.message}
                  </p>
                  {item.link && (
                    <span className="inline-flex items-center gap-1 text-[11px] text-primary font-medium mt-1">
                      View details
                      <ExternalLink className="h-2.5 w-2.5" />
                    </span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>

        <DropdownMenuSeparator className="m-0" />

        {/* Footer Quick Action */}
        <div className="p-2.5 bg-neutral-light/30 flex items-center justify-between">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setIsOpen(false);
              navigate("/reminders");
            }}
            className="w-full justify-center gap-1.5 text-xs font-medium text-primary hover:text-primary-dark h-8"
          >
            <Send className="h-3.5 w-3.5" />
            <span>Open Customer SMS Reminders</span>
          </Button>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
