"use client";

import * as React from "react";
import { Plus, Loader2, Mail, Key, Shield, AlertCircle, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { authApi, type UserListResponse, type UserCreateRequest, type UserCreateResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

type UserRole = "admin" | "finance_uploader" | "viewer";

const roleLabels: Record<UserRole, string> = {
  admin: "Admin",
  finance_uploader: "Finance Uploader",
  viewer: "Viewer",
};

const roleColors: Record<UserRole, string> = {
  admin: "bg-critical/10 text-critical border-critical/20",
  finance_uploader: "bg-warning/10 text-warning border-warning/20",
  viewer: "bg-neutral-light text-neutral dark:bg-neutral-light/20",
};

export function SettingsPage() {
  const [users, setUsers] = React.useState<UserListResponse[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [search, setSearch] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  // Create user modal state
  const [createOpen, setCreateOpen] = React.useState(false);
  const [createLoading, setCreateLoading] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = React.useState<UserCreateResponse | null>(null);
  const [newUser, setNewUser] = React.useState<UserCreateRequest>({
    username: "",
    email: "",
    full_name: "",
    role: "viewer",
  });

  // Reset password modal state
  const [resetOpen, setResetOpen] = React.useState(false);
  const [resetUser, setResetUser] = React.useState<UserListResponse | null>(null);
  const [resetLoading, setResetLoading] = React.useState(false);
  const [resetError, setResetError] = React.useState<string | null>(null);
  const [resetSuccess, setResetSuccess] = React.useState<string | null>(null);

  // Deactivate confirmation
  const [deactivateUser, setDeactivateUser] = React.useState<UserListResponse | null>(null);

  React.useEffect(() => {
    loadUsers();
  }, []);

  const loadUsers = async () => {
    setLoading(true);
    try {
      const data = await authApi.listUsers();
      setUsers(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError(null);
    setCreateLoading(true);
    try {
      const response = await authApi.createUser(newUser);
      setCreateSuccess(response);
      setCreateOpen(false);
      setNewUser({ username: "", email: "", full_name: "", role: "viewer" });
      await loadUsers();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create user");
    } finally {
      setCreateLoading(false);
    }
  };

  const handleResetPassword = async (user: UserListResponse) => {
    setResetUser(user);
    setResetOpen(true);
    setResetError(null);
    setResetSuccess(null);
  };

  const confirmResetPassword = async () => {
    if (!resetUser) return;
    setResetError(null);
    setResetLoading(true);
    try {
      const response = await authApi.resetUserPassword(resetUser.id);
      setResetSuccess(response.temporary_password);
      await loadUsers();
    } catch (err) {
      setResetError(err instanceof Error ? err.message : "Failed to reset password");
    } finally {
      setResetLoading(false);
    }
  };

  const handleDeactivate = async () => {
    if (!deactivateUser) return;
    try {
      await authApi.deactivateUser(deactivateUser.id);
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to deactivate user");
    } finally {
      setDeactivateUser(null);
    }
  };

  const filteredUsers = users.filter(
    (u) =>
      u.username.toLowerCase().includes(search.toLowerCase()) ||
      u.email.toLowerCase().includes(search.toLowerCase()) ||
      u.full_name?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Settings</h1>
          <p className="text-text-secondary mt-1">Manage users and system configuration</p>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" />
              Add User
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Create New User</DialogTitle>
              <DialogDescription>
                A temporary password will be generated and sent to the user's email.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleCreateUser} className="space-y-4">
              {createError && (
                <Alert variant="destructive" className="text-sm">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>{createError}</AlertDescription>
                </Alert>
              )}
              {createSuccess && (
                <Alert className="bg-success/10 border-success/20 text-success" variant="default">
                  <CheckCircle className="h-4 w-4" />
                  <AlertDescription className="space-y-2">
                    <div><strong>User created successfully!</strong></div>
                    <div><strong>Temp Password:</strong> <code>{createSuccess.temporary_password}</code></div>
                    <div className="text-xs">Expires: {new Date(createSuccess.expires_at).toLocaleString()}</div>
                    <p className="text-xs text-text-secondary mt-2">
                      Share these credentials with the user. They will be forced to change password on first login.
                    </p>
                  </AlertDescription>
                </Alert>
              )}
              <div className="space-y-2">
                <Label htmlFor="username">Username *</Label>
                <Input
                  id="username"
                  value={newUser.username}
                  onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
                  placeholder="john.doe"
                  required
                  disabled={createLoading}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email *</Label>
                <Input
                  id="email"
                  type="email"
                  value={newUser.email}
                  onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                  placeholder="john@company.com"
                  required
                  disabled={createLoading}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="full_name">Full Name</Label>
                <Input
                  id="full_name"
                  value={newUser.full_name}
                  onChange={(e) => setNewUser({ ...newUser, full_name: e.target.value })}
                  placeholder="John Doe"
                  disabled={createLoading}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="role">Role *</Label>
                <Select value={newUser.role} onValueChange={(v) => setNewUser({ ...newUser, role: v as UserRole })} disabled={createLoading}>
                  <SelectTrigger id="role">
                    <SelectValue placeholder="Select role" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="admin">Admin</SelectItem>
                    <SelectItem value="finance_uploader">Finance Uploader</SelectItem>
                    <SelectItem value="viewer">Viewer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setCreateOpen(false)} disabled={createLoading}>
                  Cancel
                </Button>
                <Button type="submit" disabled={createLoading}>
                  {createLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
                  Create User
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* SMTP Config Info */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mail className="h-5 w-5" />
            Email Configuration
          </CardTitle>
          <CardDescription>
            Configure SMTP settings in <code>{".env"}</code> to enable email notifications for new users and password resets.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-text-secondary">SMTP Host</p>
              <p className="font-mono text-text-primary">smtp.example.com</p>
            </div>
            <div>
              <p className="text-text-secondary">SMTP Port</p>
              <p className="font-mono text-text-primary">587</p>
            </div>
            <div>
              <p className="text-text-secondary">From Address</p>
              <p className="font-mono text-text-primary">Finance Automation <span>{"notifications@example.com"}</span></p>
            </div>
          </div>
          <p className="text-xs text-text-secondary">
            Update <code>{"SMTP_HOST"}</code>, <code>{"SMTP_PORT"}</code>, <code>{"SMTP_USER"}</code>, <code>{"SMTP_PASSWORD"}</code>, <code>{"SMTP_FROM"}</code> in <code>{".env"}</code> and restart the backend container.
          </p>
        </CardContent>
      </Card>

      {/* Users Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>User Management</CardTitle>
            <div className="flex items-center gap-2">
              <Input
                placeholder="Search users..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-64"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : filteredUsers.length === 0 ? (
            <p className="text-center text-text-secondary py-8">No users found</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>User</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Last Login</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredUsers.map((user) => (
                    <TableRow key={user.id}>
                      <TableCell>
                        <div className="font-medium">{user.username}</div>
                        {user.full_name && <div className="text-sm text-text-secondary">{user.full_name}</div>}
                      </TableCell>
                      <TableCell>{user.email}</TableCell>
                      <TableCell>
                        <Badge className={cn(roleColors[user.role as UserRole] || roleColors.viewer)}>
                          {roleLabels[user.role as UserRole] || user.role}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={user.is_active ? "success" : "neutral"}>
                          {user.is_active ? "Active" : "Inactive"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-text-secondary">
                        {user.last_login ? new Date(user.last_login).toLocaleDateString() : "Never"}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2 justify-end">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleResetPassword(user)}
                            disabled={user.id === 1 || resetLoading}
                          >
                            <Key className="h-4 w-4 mr-1" />
                            Reset Password
                          </Button>
                          {!user.is_active ? (
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-success hover:bg-success/10"
                              onClick={() => setDeactivateUser(user)}
                              disabled={user.id === 1}
                            >
                              <Shield className="h-4 w-4 mr-1" />
                              Activate
                            </Button>
                          ) : (
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-critical hover:bg-critical/10"
                              onClick={() => setDeactivateUser(user)}
                              disabled={user.id === 1}
                            >
                              <Shield className="h-4 w-4 mr-1" />
                              Deactivate
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Reset Password Dialog */}
      <Dialog open={resetOpen} onOpenChange={setResetOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Reset Password</DialogTitle>
            <DialogDescription>
              A new temporary password will be generated for <strong>{resetUser?.username}</strong> and sent to their email.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {resetError && (
              <Alert variant="destructive" className="text-sm">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{resetError}</AlertDescription>
              </Alert>
            )}
            {resetSuccess && (
              <Alert className="bg-success/10 border-success/20 text-success" variant="default">
                <CheckCircle className="h-4 w-4" />
                <AlertDescription className="space-y-2">
                  <div><strong>Password reset successfully!</strong></div>
                  <div><strong>New Temp Password:</strong> <code>{resetSuccess}</code></div>
                  <p className="text-xs text-text-secondary mt-2">
                    The user will receive this via email and must change it on next login.
                  </p>
                </AlertDescription>
              </Alert>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResetOpen(false)} disabled={resetLoading}>
              Cancel
            </Button>
            <Button onClick={confirmResetPassword} disabled={resetLoading || !resetUser}>
              {resetLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Key className="h-4 w-4 mr-2" />}
              Reset Password
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Deactivate Confirm Dialog */}
      <Dialog open={!!deactivateUser} onOpenChange={(open) => !open && setDeactivateUser(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{deactivateUser?.is_active ? "Deactivate User" : "Activate User"}</DialogTitle>
            <DialogDescription>
              Are you sure you want to {deactivateUser?.is_active ? "deactivate" : "activate"} <strong>{deactivateUser?.username}</strong>?
              {deactivateUser?.is_active ? " They will not be able to log in." : " They will be able to log in again."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeactivateUser(null)}>
              Cancel
            </Button>
            <Button
              variant={deactivateUser?.is_active ? "destructive" : "default"}
              onClick={handleDeactivate}
            >
              {deactivateUser?.is_active ? "Deactivate" : "Activate"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}