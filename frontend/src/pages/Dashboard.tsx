import { useCallback } from "react";
import { Link } from "react-router-dom";
import { api, formatNumber } from "../api/client";
import { useAsync } from "../api/useAsync";
import type { ReportPayload } from "../api/types";
import { RatingBadge, StatCard, StatusBadge } from "../components/badges";
import { BarChart } from "../components/charts";
import { RunBanner } from "../components/RunBanner";

export default function Dashboard() {
  const load = useCallback(() => api.reportLatest(), []);
  const { data, error, reload } = useAsync(load, []);

  const payload: ReportPayload | null = data?.payload ?? null;
  const totals = payload?.totals ?? {};
  const ratings = payload?.ratings ?? {};

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Главная</h1>
          <p>Сводка за день: цены, остатки, предполагаемый спрос у конкурентов</p>
        </div>
      </div>

      <RunBanner onFinished={() => void reload()} />

      {error && !payload ? (
        <div className="alert info">
          Отчётов пока нет — запустите сбор, чтобы получить первую сводку. ({error})
        </div>
      ) : null}

      {payload ? (
        <>
          <div className="grid cols-4" style={{ marginBottom: 16 }}>
            <StatCard
              label="Товаров в мониторинге"
              value={formatNumber(totals.products)}
              sub={`предложений: ${formatNumber(totals.offers)}`}
            />
            <StatCard
              label="Позиций собрано сегодня"
              value={formatNumber(totals.offers_seen_today)}
              sub={`из них активных: ${formatNumber(totals.active_offers)}`}
            />
            <StatCard
              label="Предполагаемых продаж за день"
              value={formatNumber(totals.sales_events)}
              sub={`единиц товара: ${formatNumber(totals.sales_units)}`}
            />
            <StatCard
              label="Исчезло позиций / новых товаров"
              value={`${formatNumber(totals.disappeared)} / ${formatNumber(totals.new_products)}`}
              sub={`пополнений: ${formatNumber(totals.restock_events)}`}
            />
          </div>

          <div className="grid cols-2">
            <div className="card">
              <h2>Распределение по рейтингу востребованности</h2>
              <BarChart
                data={["A", "B", "C", "D", "NEW"].map((key) => ({
                  label: key,
                  value: ratings[key] || 0,
                  color: ratingColor(key),
                }))}
                format={(v) => String(Math.round(v))}
              />
              <p className="muted" style={{ fontSize: 12 }}>
                A — ходовой товар, D — редкий спрос, NEW — мало дней наблюдения (минимум{" "}
                {"7"} для присвоения рейтинга).
              </p>
            </div>

            <div className="card">
              <h2>Топ-10 по индексу закупки</h2>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Товар</th>
                      <th>Рейтинг</th>
                      <th>Индекс</th>
                      <th>Продажи 30д</th>
                      <th>Конкурентов</th>
                    </tr>
                  </thead>
                  <tbody>
                    {payload.top_demand.slice(0, 10).map((item) => (
                      <tr key={item.id}>
                        <td>
                          <Link className="link" to={`/products/${item.id}`}>
                            {item.title}
                          </Link>
                          <div className="muted mono">{item.oem}</div>
                        </td>
                        <td>
                          <RatingBadge rating={item.rating} />
                        </td>
                        <td>{item.index_score.toFixed(1)}</td>
                        <td>{item.sales_30}</td>
                        <td>{item.competitors_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="card">
            <h2>Состояние сайтов конкурентов ({payload.day})</h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Сайт</th>
                    <th>Состояние</th>
                    <th>Позиций сегодня</th>
                    <th>Последний запуск</th>
                    <th>Ошибка</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.competitors.map((c) => (
                    <tr key={c.id}>
                      <td>
                        <a className="link" href={c.url} target="_blank" rel="noreferrer">
                          {c.name}
                        </a>
                      </td>
                      <td>{c.enabled ? <StatusBadge status={c.last_status} /> : <span className="badge status-neutral">выключен</span>}</td>
                      <td>{c.offers_today}</td>
                      <td className="muted">{c.last_run_at || "—"}</td>
                      <td className="muted" style={{ maxWidth: 420 }}>
                        {c.last_error ? truncate(c.last_error, 160) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>
              {payload.note}
            </p>
          </div>
        </>
      ) : null}
    </>
  );
}

function ratingColor(rating: string): string {
  return (
    { A: "#16a34a", B: "#65a30d", C: "#d97706", D: "#dc2626", NEW: "#2563eb" } as Record<string, string>
  )[rating] || "#3b82f6";
}

function truncate(text: string, size: number): string {
  return text.length > size ? text.slice(0, size) + "…" : text;
}
