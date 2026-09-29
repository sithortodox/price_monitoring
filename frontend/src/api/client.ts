import type {
  AppSettings,
  Competitor,
  IndexWeight,
  ParserInfo,
  ProductDetail,
  ProxyCheckResult,
  ProductPage,
  ReportPayload,
  RunRow,
  RunStatus,
  TopItem,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {
      /* тело не JSON — оставляем статус */
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string; database: string; time: string }>("/api/health"),
  parsers: () => request<ParserInfo[]>("/api/parsers"),

  competitors: () => request<Competitor[]>("/api/competitors"),
  patchCompetitor: (id: number, payload: Partial<Competitor>) =>
    request<Competitor>(`/api/competitors/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  runCompetitor: (id: number) =>
    request<{ started: boolean; reason?: string }>(`/api/competitors/${id}/run`, { method: "POST" }),
  proxyCheck: (id: number) =>
    request<ProxyCheckResult>(`/api/competitors/${id}/proxy-check`, { method: "POST" }),

  runs: (limit = 50) => request<RunRow[]>(`/api/runs?limit=${limit}`),
  runStatus: () => request<RunStatus>("/api/run/status"),
  startRun: (competitorIds: number[] | null = null) =>
    request<{ started: boolean; reason?: string }>("/api/run", {
      method: "POST",
      body: JSON.stringify({ competitor_ids: competitorIds }),
    }),

  products: (params: Record<string, string | number | undefined>) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    return request<ProductPage>(`/api/products?${query.toString()}`);
  },
  product: (id: number) => request<ProductDetail>(`/api/products/${id}`),

  reportLatest: () => request<{ day: string; payload: ReportPayload }>("/api/report/latest"),
  report: (day: string) => request<{ day: string; payload: ReportPayload }>(`/api/report/${day}`),
  top: (kind: "demand" | "sales" | "competitive", limit = 20) =>
    request<TopItem[]>(`/api/top?kind=${kind}&limit=${limit}`),

  settings: () => request<AppSettings>("/api/settings"),
  weights: () => request<IndexWeight[]>("/api/index-weights"),
  saveWeights: (weights: IndexWeight[]) =>
    request<IndexWeight[]>("/api/index-weights", {
      method: "PUT",
      body: JSON.stringify(weights.map(({ key, weight, enabled }) => ({ key, weight, enabled }))),
    }),

  exportUrl: (day?: string, historyDays = 30) =>
    `/api/export?history_days=${historyDays}${day ? `&day=${day}` : ""}`,
};

export function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("ru-RU", { maximumFractionDigits: 0 }) + " ₽";
}

export function formatNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("ru-RU", { maximumFractionDigits: digits });
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
