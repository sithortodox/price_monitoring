import { useState } from "react";
import { Link } from "react-router-dom";
import { api, formatMoney } from "../api/client";
import { useAsync } from "../api/useAsync";
import { RatingBadge } from "../components/badges";

type Kind = "demand" | "sales" | "competitive";

const TABS: { key: Kind; label: string; hint: string }[] = [
  { key: "demand", label: "Индекс закупки", hint: "Комплексный показатель спроса (0–100)" },
  { key: "sales", label: "Продажи за 30 дней", hint: "Предполагаемые продажи по снижению остатков" },
  { key: "competitive", label: "Конкуренты", hint: "Где товар представлен у большего числа продавцов" },
];

export default function Top() {
  const [kind, setKind] = useState<Kind>("demand");
  const load = () => api.top(kind, 50);
  const { data, error, loading } = useAsync(load, [kind]);
  const active = TABS.find((t) => t.key === kind)!;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>ТОП спроса</h1>
          <p>{active.hint}</p>
        </div>
      </div>

      <div className="tabs">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={`tab${tab.key === kind ? " active" : ""}`}
            onClick={() => setKind(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="card">
        {error ? <div className="alert error">{error}</div> : null}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Товар</th>
                <th>Рейтинг</th>
                <th>Индекс</th>
                <th>Продажи 7д</th>
                <th>Продажи 30д</th>
                <th>Частота</th>
                <th>Конкурентов</th>
                <th>Мин. цена</th>
                <th>Медиана</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((item, index) => (
                <tr key={item.id}>
                  <td className="muted">{index + 1}</td>
                  <td style={{ maxWidth: 360 }}>
                    <Link className="link" to={`/products/${item.id}`}>
                      {item.title}
                    </Link>
                    <div className="muted mono">{item.oem}</div>
                  </td>
                  <td>
                    <RatingBadge rating={item.rating} />
                  </td>
                  <td>{item.index_score.toFixed(1)}</td>
                  <td>{item.sales_7}</td>
                  <td>{item.sales_30}</td>
                  <td>{item.frequency_pct.toFixed(1)}%</td>
                  <td>{item.competitors_count}</td>
                  <td className="mono">{formatMoney(item.min_price)}</td>
                  <td className="mono">{formatMoney(item.median_price)}</td>
                </tr>
              ))}
              {!loading && data?.length === 0 ? (
                <tr>
                  <td colSpan={10} className="empty">
                    Данных пока нет — запустите сбор и дождитесь пересчёта аналитики
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
