const API_BASE = "/api/v1";

/** Convert a FastAPI error detail to a safe, readable string.
 *  - string  → returned as-is
 *  - list    → "field: message" per item (field = last segment of loc), no submitted values
 *  - other   → generic fallback
 */
export function formatError(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item: { loc?: string[]; msg?: string }) => {
        const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : "field";
        const msg = typeof item.msg === "string" ? item.msg : "invalid value";
        return `${field}: ${msg}`;
      })
      .join("; ");
  }
  return "Something went wrong. Please try again.";
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    credentials: "include", // Include cookies for session auth
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    // Error bodies are usually JSON, but proxies and unhandled server errors
    // return HTML/plain text. Fall back to the status so the UI never shows a
    // bare "Request failed" with no clue about what happened.
    const text = await response.text().catch(() => "");
    let detail: unknown;
    try {
      detail = JSON.parse(text).detail;
    } catch {
      detail = undefined;
    }
    const status = response.statusText
      ? `HTTP ${response.status} ${response.statusText}`
      : `HTTP ${response.status}`;
    throw new Error(detail ? formatError(detail) : `Request failed (${status})`);
  }

  return response.json();
}

export interface KPIData {
  title: string;
  value: string;
  rawValue?: number;
  secondaryValue?: string;
  secondaryLabel?: string;
  change: number;
  changeLabel: string;
  trend: "up" | "down" | "neutral";
}

export interface RegionData {
  region: string;
  receivable: number;
  collected: number;
  overdue: number;
}

export interface CostCenterData {
  cost_center: string;
  contracts: number;
  receivable: number;
  collected: number;
  balance_due: number;
}

export interface AgingData {
  bucket: string;
  amount: number;
  count: number;
}

export interface TrendData {
  month: string;
  internal: number;
  external: number;
  total: number;
}

export interface AttentionItem {
  id: string;
  type: "missing_contract" | "validation_warning" | "pending_review";
  title: string;
  description: string;
  count: number;
  actionLabel: string;
}

export interface UploadRowData {
  id: number;
  file_name: string;
  date: string;
  status: string;
  contracts: number;
}

export interface CostCenterContractData {
  id: number;
  reference: string;
  customer: string;
  cid: string;
  mobile: string;
  item: string;
  brand: string;
  ministry_agency: string;
  region: string;
  cost_center: string;
  payment_type: string;
  emi_months: number | null;
  months_left: number | null;
  monthly_deduction: number;
  sales_amount: number;
  gst: number;
  received: number;
  outstanding: number;
  collected: number;
  balance_due: number;
  start_date: string | null;
  end_date: string | null;
  status: string;
}

export interface ContractListItem {
  id: number;
  reference: string;
  customer: string;
  cid: string;
  mobile: string;
  item: string;
  brand: string;
  ministry_agency: string;
  region: string;
  cost_center: string;
  payment_type: string;
  emi_months: number | null;
  months_left: number | null;
  monthly_deduction: number;
  sales_amount: number;
  gst: number;
  receivable: number;
  received: number;
  collected: number;
  total_due: number;
  outstanding: number;
  balance_due: number;
  start_date: string | null;
  end_date: string | null;
  status: string;
}

export interface ContractUpdateRequest {
  customer?: string | null;
  cid?: string | null;
  mobile?: string | null;
  item?: string | null;
  brand?: string | null;
  region?: string | null;
  cost_center?: string | null;
  ministry_agency?: string | null;
  payment_type?: string | null;
  emi_months?: number | null;
  monthly_deduction?: number | null;
  sales_amount?: number | null;
  gst?: number | null;
  start_date?: string | null;
  end_date?: string | null;
}

export interface ContractSummary {
  contracts: number;
  monthly_deduction: number;
  receivable: number;
  outstanding: number;
  collected: number;
  balance_due: number;
}

export interface ContractListResponse {
  items: ContractListItem[];
  total: number;
  skip: number;
  limit: number;
  summary: ContractSummary;
}

export interface ContractFacets {
  regions: string[];
  cost_centers: Array<{ region: string; name: string }>;
  brands: string[];
}

export interface ContractInstallment {
  id: number;
  due_month: string;
  due_amount: number;
  received_amount: number;
  balance: number;
  salary_amount: number;
  external_amount: number;
  cell_status: string | null;
  status: string;
}

export interface ContractListParams {
  search?: string;
  state?: string;
  channel?: string;
  region?: string;
  cost_center?: string;
  brand?: string;
  emi_left?: string;
  ending?: string;
  overdue?: boolean;
  cycle_ended_due?: boolean;
  cycle_ended_paid?: boolean;
  sort?: string;
  order?: "asc" | "desc";
  skip?: number;
  limit?: number;
}

export interface DashboardFilterParams {
  preset?: string;
  from?: string;
  to?: string;
  region?: string;
  channel?: string;
  cost_center?: string;
}

export interface DashboardData {
  kpis: KPIData[];
  summary?: {
    due: number;
    collected: number;
    overdue: number;
    outstanding: number;
    total_outstanding_all_time: number;
  };
  regions: RegionData[];
  aging: AgingData[];
  trend: TrendData[];
  attention: AttentionItem[];
  recentUploads: UploadRowData[];
  asOfDate: string;
  lastUploadAt: string | null;
  filters?: DashboardFilterParams;
}

function buildQuery(params?: DashboardFilterParams): string {
  if (!params) return "";
  const query = new URLSearchParams();
  if (params.preset) query.set("preset", params.preset);
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);
  if (params.region) query.set("region", params.region);
  if (params.channel) query.set("channel", params.channel);
  if (params.cost_center) query.set("cost_center", params.cost_center);
  const qs = query.toString();
  return qs ? `?${qs}` : "";
}

export const dashboardApi = {
  async getDashboard(params?: DashboardFilterParams): Promise<DashboardData> {
    return fetchJson<DashboardData>(`/dashboard/${buildQuery(params)}`);
  },

  async getKPIs(params?: DashboardFilterParams): Promise<KPIData[]> {
    return fetchJson<KPIData[]>(`/dashboard/kpis${buildQuery(params)}`);
  },

  async getRegions(params?: DashboardFilterParams): Promise<RegionData[]> {
    return fetchJson<RegionData[]>(`/dashboard/regions${buildQuery(params)}`);
  },

  async getCostCenters(params?: DashboardFilterParams): Promise<CostCenterData[]> {
    return fetchJson<CostCenterData[]>(`/dashboard/cost-centers${buildQuery(params)}`);
  },

  async getCostCenterContracts(
    params: DashboardFilterParams
  ): Promise<CostCenterContractData[]> {
    return fetchJson<CostCenterContractData[]>(
      `/dashboard/cost-centers/contracts${buildQuery(params)}`
    );
  },

  async getAging(params?: DashboardFilterParams): Promise<AgingData[]> {
    return fetchJson<AgingData[]>(`/dashboard/aging${buildQuery(params)}`);
  },

  async getTrend(params?: DashboardFilterParams): Promise<TrendData[]> {
    return fetchJson<TrendData[]>(`/dashboard/trend${buildQuery(params)}`);
  },

  async getAttention(): Promise<AttentionItem[]> {
    return fetchJson<AttentionItem[]>("/dashboard/attention");
  },

  async getRecentUploads(): Promise<UploadRowData[]> {
    return fetchJson<UploadRowData[]>("/dashboard/uploads");
  },
};

export const uploadsApi = {
  async upload(file: File, asOfDate: string, sheetName?: string, headerRow?: number) {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("as_of_date", asOfDate);
    if (sheetName) formData.append("sheet_name", sheetName);
    if (headerRow) formData.append("header_row", String(headerRow));

    const response = await fetch(`${API_BASE}/uploads`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Upload failed" }));
      throw new Error(formatError(error.detail) || `HTTP ${response.status}`);
    }

    return response.json();
  },

  async getPreview(uploadId: number) {
    return fetchJson(`/uploads/${uploadId}/preview`);
  },

  async confirm(uploadId: number, totpCode: string) {
    return fetchJson(`/uploads/${uploadId}/confirm`, {
      method: "POST",
      body: JSON.stringify({ totp_code: totpCode, code: totpCode }),
    });
  },

  async rollback(uploadId: number) {
    return fetchJson(`/uploads/${uploadId}/rollback`, { method: "POST" });
  },

  async list(skip = 0, limit = 50, status?: string) {
    const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (status) params.append("status_filter", status);
    return fetchJson(`/uploads?${params}`);
  },
};

export interface ReportOverdueItem {
  id: number;
  reference: string;
  customer: string;
  cid: string;
  mobile: string;
  region: string;
  cost_center: string;
  brand: string;
  payment_type: string;
  monthly_deduction: number;
  emi_months: number | null;
  months_left: number | null;
  outstanding: number;
  balance_due: number;
  overdue_amount: number;
  start_date: string | null;
  end_date: string | null;
  status: string;
}

export interface ReportOverdueResponse {
  items: ReportOverdueItem[];
  total: number;
  total_overdue: number;
}

export interface ReportByRegionItem {
  region: string;
  cost_center: string;
  contracts: number;
  monthly_deduction: number;
  outstanding: number;
  collected: number;
  balance_due: number;
}

export interface ReportByRegionResponse {
  items: ReportByRegionItem[];
}

export interface ReportByBrandItem {
  brand: string;
  contracts: number;
  monthly_deduction: number;
  outstanding: number;
  collected: number;
  balance_due: number;
}

export interface ReportByBrandResponse {
  items: ReportByBrandItem[];
}

export interface ReportDueItem {
  installment_id: number;
  contract_id: number;
  reference: string;
  customer: string;
  region: string;
  cost_center: string;
  brand: string;
  payment_type: string;
  due_month: string | null;
  due_amount: number;
  received_amount: number;
  balance: number;
  status: string;
  contract_status: string;
}

export interface ReportDueResponse {
  items: ReportDueItem[];
  total: number;
  total_due: number;
  total_balance: number;
}

export interface ReportParams {
  region?: string;
  cost_center?: string;
  channel?: string;
  brand?: string;
  state?: string;
  from_month?: string;
  to_month?: string;
  limit?: number;
}

export const reportsApi = {
  async overdue(params?: ReportParams): Promise<ReportOverdueResponse> {
    const sp = new URLSearchParams();
    if (params?.region) sp.append("region", params.region);
    if (params?.cost_center) sp.append("cost_center", params.cost_center);
    if (params?.channel) sp.append("channel", params.channel);
    if (params?.brand) sp.append("brand", params.brand);
    if (params?.state) sp.append("state", params.state);
    if (params?.limit) sp.append("limit", String(params.limit));
    return fetchJson<ReportOverdueResponse>(`/dashboard/reports/overdue?${sp.toString()}`);
  },

  async byRegion(params?: ReportParams): Promise<ReportByRegionResponse> {
    const sp = new URLSearchParams();
    if (params?.region) sp.append("region", params.region);
    if (params?.channel) sp.append("channel", params.channel);
    if (params?.brand) sp.append("brand", params.brand);
    if (params?.state) sp.append("state", params.state);
    return fetchJson<ReportByRegionResponse>(`/dashboard/reports/by-region?${sp.toString()}`);
  },

  async byBrand(params?: ReportParams): Promise<ReportByBrandResponse> {
    const sp = new URLSearchParams();
    if (params?.region) sp.append("region", params.region);
    if (params?.cost_center) sp.append("cost_center", params.cost_center);
    if (params?.channel) sp.append("channel", params.channel);
    if (params?.brand) sp.append("brand", params.brand);
    if (params?.state) sp.append("state", params.state);
    return fetchJson<ReportByBrandResponse>(`/dashboard/reports/by-brand?${sp.toString()}`);
  },

  async dues(params?: ReportParams): Promise<ReportDueResponse> {
    const sp = new URLSearchParams();
    if (params?.region) sp.append("region", params.region);
    if (params?.cost_center) sp.append("cost_center", params.cost_center);
    if (params?.channel) sp.append("channel", params.channel);
    if (params?.brand) sp.append("brand", params.brand);
    if (params?.state) sp.append("state", params.state);
    if (params?.from_month) sp.append("from_month", params.from_month);
    if (params?.to_month) sp.append("to_month", params.to_month);
    if (params?.limit) sp.append("limit", String(params.limit));
    return fetchJson<ReportDueResponse>(`/dashboard/reports/dues?${sp.toString()}`);
  },
};

export const contractsApi = {
  async list(params?: ContractListParams): Promise<ContractListResponse> {
    const searchParams = new URLSearchParams();
    if (params?.search) searchParams.append("search", params.search);
    if (params?.state) searchParams.append("state", params.state);
    if (params?.channel) searchParams.append("channel", params.channel);
    if (params?.region) searchParams.append("region", params.region);
    if (params?.cost_center) searchParams.append("cost_center", params.cost_center);
    if (params?.brand) searchParams.append("brand", params.brand);
    if (params?.emi_left) searchParams.append("emi_left", params.emi_left);
    if (params?.ending) searchParams.append("ending", params.ending);
    if (params?.overdue) searchParams.append("overdue", "true");
    if (params?.cycle_ended_due) searchParams.append("cycle_ended_due", "true");
    if (params?.cycle_ended_paid) searchParams.append("cycle_ended_paid", "true");
    if (params?.sort) searchParams.append("sort", params.sort);
    if (params?.order) searchParams.append("order", params.order);
    if (params?.skip) searchParams.append("skip", String(params.skip));
    if (params?.limit) searchParams.append("limit", String(params.limit));
    return fetchJson<ContractListResponse>(`/contracts?${searchParams.toString()}`);
  },

  async facets(): Promise<ContractFacets> {
    return fetchJson<ContractFacets>("/contracts/facets");
  },

  async get(id: number): Promise<ContractListItem> {
    return fetchJson<ContractListItem>(`/contracts/${id}`);
  },

  async update(
    id: number,
    data: ContractUpdateRequest
  ): Promise<ContractListItem> {
    return fetchJson<ContractListItem>(`/contracts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  async getInstallments(contractId: number): Promise<ContractInstallment[]> {
    return fetchJson<ContractInstallment[]>(`/contracts/${contractId}/installments`);
  },

  async closeContract(
    contractId: number,
    data: { code: string; reason?: string; note?: string }
  ): Promise<{ contract_id: number; status: string; message: string }> {
    return fetchJson<{ contract_id: number; status: string; message: string }>(
      `/contracts/${contractId}/close`,
      {
        method: "POST",
        body: JSON.stringify(data),
      }
    );
  },
};

export interface LoginResponse {
  user: {
    id: number;
    username: string;
    email: string;
    full_name: string | null;
    role: string;
    is_active: boolean;
    must_change_password: boolean;
    last_login: string | null;
  };
  must_change_password: boolean;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

export interface ChangePasswordResponse {
  message: string;
  user: {
    id: number;
    username: string;
    email: string;
    full_name: string | null;
    role: string;
    is_active: boolean;
    must_change_password: boolean;
    last_login: string | null;
  };
}

export interface MeResponse {
  id: number;
  username: string;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  must_change_password: boolean;
  password_changed_at: string | null;
  last_login: string | null;
}

export interface UserCreateRequest {
  username: string;
  email: string;
  full_name?: string;
  role: "admin" | "finance_uploader" | "viewer";
}

export interface UserCreateResponse {
  user: {
    id: number;
    username: string;
    email: string;
    full_name: string | null;
    role: string;
    is_active: boolean;
    must_change_password: boolean;
    last_login: string | null;
  };
  temporary_password: string;
  expires_at: string;
}

export interface UserResetPasswordResponse {
  message: string;
  temporary_password: string;
  expires_at: string;
}

export interface UserDeactivateResponse {
  message: string;
}

export interface UserListResponse {
  id: number;
  username: string;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  must_change_password: boolean;
  last_login: string | null;
  created_at: string;
}

export interface CreditContract {
  reference: string;
  item: string;
  brand: string;
  start_date: string;
  end_date: string;
  status: string;
  monthly_emi: number;
  outstanding: number;
  balance_due: number;
  months_left: number;
  is_overdue: boolean;
  overdue_amount: number;
}

export interface CreditCheckResponse {
  cid: string;
  customer_name: string;
  mobile: string | null;
  total_contracts: number;
  active_contracts: number;
  closed_contracts: number;
  overdue_contracts: number;
  total_outstanding: number;
  total_balance_due: number;
  total_monthly_emi: number;
  total_collected: number;
  total_installments: number;
  paid_installments: number;
  overdue_installments: number;
  partial_installments: number;
  payment_rate: number;
  max_days_overdue: number;
  has_overdue: boolean;
  multiple_active_loans: boolean;
  high_balance_due_ratio: boolean;
  credit_score: number;
  risk_level: "low" | "medium" | "high" | "critical";
  recommendation: string;
  contracts: CreditContract[];
}

export const authApi = {
  async login(credentials: { username: string; password: string }): Promise<LoginResponse> {
    return fetchJson<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(credentials),
    });
  },

  async changePassword(params: ChangePasswordRequest): Promise<ChangePasswordResponse> {
    return fetchJson<ChangePasswordResponse>("/auth/change-password", {
      method: "POST",
      body: JSON.stringify(params),
    });
  },

  async creditCheck(cid: string): Promise<CreditCheckResponse> {
    return fetchJson<CreditCheckResponse>(`/credit-check/check/${cid}`);
  },

  async logout(): Promise<void> {
    await fetchJson("/auth/logout", { method: "POST" });
  },

  async me(): Promise<MeResponse> {
    return fetchJson<MeResponse>("/auth/me");
  },

  async refresh(): Promise<MeResponse> {
    return fetchJson<MeResponse>("/auth/refresh", { method: "POST" });
  },

  // Admin endpoints
  async createUser(userData: UserCreateRequest): Promise<UserCreateResponse> {
    return fetchJson<UserCreateResponse>("/auth/users", {
      method: "POST",
      body: JSON.stringify(userData),
    });
  },

  async resetUserPassword(userId: number): Promise<UserResetPasswordResponse> {
    return fetchJson<UserResetPasswordResponse>(`/auth/users/${userId}/reset-password`, {
      method: "POST",
    });
  },

  async deactivateUser(userId: number): Promise<UserDeactivateResponse> {
    return fetchJson<UserDeactivateResponse>(`/auth/users/${userId}/deactivate`, {
      method: "POST",
    });
  },

  async listUsers(): Promise<UserListResponse[]> {
    return fetchJson<UserListResponse[]>("/auth/users");
  },
};

// ---------------------------------------------------------------------------
// Notifications & Customer SMS Reminders
// ---------------------------------------------------------------------------

export interface InAppNotificationItem {
  id: string;
  title: string;
  message: string;
  type: "info" | "warning" | "critical" | "success";
  status: "unread" | "read";
  link?: string;
  created_at: string;
}

export interface InAppNotificationListResponse {
  unread_count: number;
  items: InAppNotificationItem[];
}

export interface NotificationTemplate {
  id: number;
  name: string;
  channel: string;
  subject?: string;
  body_template: string;
  variables?: string;
  is_active: boolean;
}

export interface ReminderCandidate {
  contract_id: number;
  reference: string;
  customer: string;
  cid?: string;
  mobile?: string;
  region?: string;
  cost_center?: string;
  item?: string;
  brand?: string;
  balance_due: number;
  overall_outstanding: number;
  months_left?: number;
  aging_bucket: string;
  alert: string;
  rendered_message: string;
}

export interface ReminderPreviewResponse {
  total_eligible: number;
  with_mobile_count: number;
  missing_mobile_count: number;
  total_balance_due: number;
  candidates: ReminderCandidate[];
  templates: NotificationTemplate[];
}

export interface SendRemindersRequest {
  contract_ids: number[];
  template_id?: number;
  custom_message_template?: string;
}

export interface SendRemindersResponse {
  total_targeted: number;
  sent_count: number;
  failed_count: number;
  skipped_no_phone: number;
  message: string;
}

export interface NotificationHistoryItem {
  id: number;
  recipient_type: string;
  recipient_id: string;
  channel: string;
  subject?: string;
  body: string;
  status: string;
  sent_at?: string;
  error?: string;
  meta?: Record<string, any>;
  created_at: string;
}

export interface NotificationHistoryResponse {
  total: number;
  items: NotificationHistoryItem[];
}

export const notificationsApi = {
  async getInApp(): Promise<InAppNotificationListResponse> {
    return fetchJson<InAppNotificationListResponse>("/notifications/in-app");
  },

  async markInAppRead(notificationIds?: string[]): Promise<{ message: string; updated_count: number }> {
    return fetchJson<{ message: string; updated_count: number }>("/notifications/in-app/mark-read", {
      method: "POST",
      body: JSON.stringify({ notification_ids: notificationIds || null }),
    });
  },

  async getTemplates(): Promise<NotificationTemplate[]> {
    return fetchJson<NotificationTemplate[]>("/notifications/templates");
  },

  async getReminderCandidates(params?: {
    aging_bucket?: string;
    region?: string;
    channel?: string;
    min_balance?: number;
    template_id?: number;
  }): Promise<ReminderPreviewResponse> {
    const qs = new URLSearchParams();
    if (params?.aging_bucket) qs.set("aging_bucket", params.aging_bucket);
    if (params?.region) qs.set("region", params.region);
    if (params?.channel) qs.set("channel", params.channel);
    if (params?.min_balance !== undefined) qs.set("min_balance", params.min_balance.toString());
    if (params?.template_id) qs.set("template_id", params.template_id.toString());
    const query = qs.toString();
    return fetchJson<ReminderPreviewResponse>(`/notifications/reminders/candidates${query ? `?${query}` : ""}`);
  },

  async sendReminders(payload: SendRemindersRequest): Promise<SendRemindersResponse> {
    return fetchJson<SendRemindersResponse>("/notifications/reminders/send", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getHistory(params?: { channel?: string; limit?: number; offset?: number }): Promise<NotificationHistoryResponse> {
    const qs = new URLSearchParams();
    if (params?.channel) qs.set("channel", params.channel);
    if (params?.limit) qs.set("limit", params.limit.toString());
    if (params?.offset) qs.set("offset", params.offset.toString());
    const query = qs.toString();
    return fetchJson<NotificationHistoryResponse>(`/notifications/history${query ? `?${query}` : ""}`);
  },
};