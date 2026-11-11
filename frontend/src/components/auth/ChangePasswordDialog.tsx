"use client";

import * as React from "react";
import { Eye, EyeOff, Check, X, AlertCircle, Loader2, KeyRound, CheckCircle2 } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

interface ChangePasswordDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface PasswordRequirement {
  label: string;
  met: boolean;
}

const SPECIAL_CHARS = /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/;

export function ChangePasswordDialog({ open, onOpenChange }: ChangePasswordDialogProps) {
  const { changePassword } = useAuth();

  const [currentPassword, setCurrentPassword] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");
  const [confirmPassword, setConfirmPassword] = React.useState("");
  const [showCurrent, setShowCurrent] = React.useState(false);
  const [showNew, setShowNew] = React.useState(false);
  const [showConfirm, setShowConfirm] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [success, setSuccess] = React.useState(false);

  const resetForm = React.useCallback(() => {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setShowCurrent(false);
    setShowNew(false);
    setShowConfirm(false);
    setError(null);
    setIsSubmitting(false);
    setSuccess(false);
  }, []);

  React.useEffect(() => {
    if (!open) {
      // Reset shortly after closing so the dialog doesn't visibly clear while animating out.
      const t = window.setTimeout(resetForm, 200);
      return () => window.clearTimeout(t);
    }
  }, [open, resetForm]);

  const requirements: PasswordRequirement[] = [
    { label: "At least 12 characters", met: newPassword.length >= 12 },
    { label: "At least one uppercase letter", met: /[A-Z]/.test(newPassword) },
    { label: "At least one lowercase letter", met: /[a-z]/.test(newPassword) },
    { label: "At least one number", met: /\d/.test(newPassword) },
    { label: "At least one special character", met: SPECIAL_CHARS.test(newPassword) },
    {
      label: "Passwords match",
      met: newPassword === confirmPassword && newPassword.length > 0,
    },
  ];

  const allMet = requirements.every((r) => r.met);
  const passwordsMatch = newPassword === confirmPassword && newPassword.length > 0;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!currentPassword) {
      setError("Please enter your current password");
      return;
    }
    if (!allMet) {
      setError("Password does not meet all requirements");
      return;
    }

    setIsSubmitting(true);
    try {
      await changePassword(currentPassword, newPassword, confirmPassword);
      setSuccess(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to change password. Please try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="mx-auto mb-2 flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10">
            <KeyRound className="h-6 w-6 text-primary" />
          </div>
          <DialogTitle className="text-center text-xl">Change Password</DialogTitle>
          <DialogDescription className="text-center">
            {success
              ? "Your password has been updated."
              : "Enter your current password and choose a new one."}
          </DialogDescription>
        </DialogHeader>

        {success ? (
          <div className="space-y-4">
            <Alert className="border-success/20 bg-success/10 text-success" variant="default">
              <CheckCircle2 className="h-4 w-4" />
              <AlertDescription>
                Password changed successfully. Use your new password the next time you sign in.
              </AlertDescription>
            </Alert>
            <DialogFooter>
              <Button className="w-full" onClick={() => onOpenChange(false)}>
                Done
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <Alert variant="destructive" className="text-sm">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-2">
              <Label htmlFor="cp-currentPassword">Current Password</Label>
              <div className="relative">
                <Input
                  id="cp-currentPassword"
                  type={showCurrent ? "text" : "password"}
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  placeholder="Enter current password"
                  autoComplete="current-password"
                  required
                  disabled={isSubmitting}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowCurrent(!showCurrent)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-text-secondary hover:text-text-primary"
                  aria-label={showCurrent ? "Hide password" : "Show password"}
                >
                  {showCurrent ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <Separator />

            <div className="space-y-2">
              <Label htmlFor="cp-newPassword">New Password</Label>
              <div className="relative">
                <Input
                  id="cp-newPassword"
                  type={showNew ? "text" : "password"}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Enter new password"
                  autoComplete="new-password"
                  required
                  disabled={isSubmitting}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowNew(!showNew)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-text-secondary hover:text-text-primary"
                  aria-label={showNew ? "Hide password" : "Show password"}
                >
                  {showNew ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="cp-confirmPassword">Confirm New Password</Label>
              <div className="relative">
                <Input
                  id="cp-confirmPassword"
                  type={showConfirm ? "text" : "password"}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Confirm new password"
                  autoComplete="new-password"
                  required
                  disabled={isSubmitting}
                  className={cn(
                    "pr-10",
                    !passwordsMatch && confirmPassword.length > 0 && "border-critical"
                  )}
                />
                <button
                  type="button"
                  onClick={() => setShowConfirm(!showConfirm)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-text-secondary hover:text-text-primary"
                  aria-label={showConfirm ? "Hide password" : "Show password"}
                >
                  {showConfirm ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {!passwordsMatch && confirmPassword.length > 0 && (
                <p className="text-sm text-critical">Passwords do not match</p>
              )}
            </div>

            <div className="space-y-1.5 rounded-lg bg-neutral-light/50 p-3">
              {requirements.map((req) => (
                <div key={req.label} className="flex items-center gap-2 text-xs">
                  {req.met ? (
                    <Check className="h-3.5 w-3.5 flex-shrink-0 text-success" />
                  ) : (
                    <X className="h-3.5 w-3.5 flex-shrink-0 text-text-secondary" />
                  )}
                  <span className={cn(req.met ? "text-success" : "text-text-secondary")}>
                    {req.label}
                  </span>
                </div>
              ))}
            </div>

            <DialogFooter className="gap-2 sm:gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isSubmitting}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting || !allMet || !currentPassword}>
                {isSubmitting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Updating...
                  </>
                ) : (
                  "Update Password"
                )}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
