export interface Competitor {
  id: number;
  name: string;
  domain: string;
  base_url: string;
  parser_key: string;
  enabled: boolean;
  detail_enabled: boolean;
  config: Record<string, unknown>;
  categories: string[];
  note: string | null;
  sort_order: number;
  last_run: {
    id: number;
    status: string;
    started_at: string | null;
    duration_ms: number;
    items_found: number;
    errors_count: number;
    error_message: string | null;
  } | null;
  offers_total: number;
  offers_today: number;
}

export interface ProxyCheckResult {
  ok: boolean;
  source: "site" | "global" | "none";
  proxy: string | null;
  status: number | null;
  elapsed_ms: number;
  error: string | null;
}

export interface RunRow {
  id: number;
  competitor_id: number;
  competitor_name: string | null;
  trigger: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  pages_fetched: number;
  items_found: number;
  offers_written: number;
  errors_count: number;
  error_message: string | null;
  duration_ms: number;
}

export interface ProductListItem {
  id: number;
  title: string;
  brand: string | null;
  oem: string | null;
  category: string | null;
  rating: string;
  index_score: number;
  sales_7: number;
  sales_14: number;
  sales_30: number;
  sales_90: number;
  frequency_pct: number;
  days_observed: number;
  competitors_count: number;
  in_stock_competitors: number;
  min_price: number | null;
  median_price: number | null;
  max_price: number | null;
  price_delta: number | null;
  qty_total: number | null;
}

export interface ProductPage {
  total: number;
  page: number;
  page_size: number;
  pages: number;
  items: ProductListItem[];
}

export interface OfferRow {
  competitor_id: number;
  competitor_name: string;
  url: string;
  price: number | null;
  old_price: number | null;
  discount_pct: number | null;
  qty: number | null;
  qty_text: string | null;
  availability: string;
  status_text: string | null;
  warehouse: string | null;
  delivery_time: string | null;
  snapshot_date: string | null;
}

export interface SeriesPoint {
  day: string;
  qty_total: number | null;
  offers_total: number;
  min_price: number | null;
  avg_price: number | null;
  max_price: number | null;
  delta: number | null;
  change_kind: string;
}

export interface ProductStats {
  rating: string;
  index_score: number;
  index_parts: Record<string, number>;
  days_observed: number;
  sale_days: number;
  frequency_pct: number;
  sales_1: number;
  sales_7: number;
  sales_14: number;
  sales_30: number;
  sales_60: number;
  sales_90: number;
  restocks_30: number;
  avg_daily_sales: number;
  competitors_count: number;
  in_stock_competitors: number;
  min_price: number | null;
  max_price: number | null;
  avg_price: number | null;
  median_price: number | null;
  price_delta: number | null;
  price_changed_at: string | null;
}

export interface ProductDetail {
  product: {
    id: number;
    title: string;
    brand: string | null;
    manufacturer: string | null;
    oem: string | null;
    article: string | null;
    alt_numbers: string[];
    applicability: string | null;
    category: string | null;
    vanished: boolean;
    first_seen_at: string | null;
  };
  stats: ProductStats | null;
  offers: OfferRow[];
  series: SeriesPoint[];
  note: string;
}

export interface TopItem {
  id: number;
  title: string;
  brand: string | null;
  oem: string | null;
  category: string | null;
  rating: string;
  index_score: number;
  sales_7: number;
  sales_30: number;
  frequency_pct: number;
  competitors_count: number;
  min_price: number | null;
  median_price: number | null;
}

export interface ReportPayload {
  day: string;
  generated_at: string;
  totals: Record<string, number>;
  ratings: Record<string, number>;
  top_demand: TopItem[];
  top_sales_30: TopItem[];
  top_competitive: TopItem[];
  competitors: {
    id: number;
    name: string;
    url: string;
    enabled: boolean;
    offers_today: number;
    last_status: string | null;
    last_error: string | null;
    last_run_at: string | null;
  }[];
  note: string;
}

export interface RunStatus {
  running: boolean;
  trigger: string | null;
  started_at: string | null;
  finished_at: string | null;
  result: unknown;
  error: string | null;
}

export interface IndexWeight {
  key: string;
  label: string;
  weight: number;
  enabled: boolean;
}

export interface ParserInfo {
  key: string;
  name: string;
  urls: string;
  use_browser: string;
}

export interface AppSettings {
  schedule_hour: number;
  schedule_minute: number;
  timezone: string;
  scheduler_enabled: boolean;
  vanished_grace_days: number;
  history_days_required_for_rating: number;
  max_pages_per_site: number;
  http_delay_sec: number;
}
