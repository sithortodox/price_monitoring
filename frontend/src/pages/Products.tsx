import { useState } from "react";
import { Link } from "react-router-dom";
import { api, formatMoney, formatNumber } from "../api/client";
import { useAsync } from "../api/useAsync";
import { RatingBadge } from "../components/badges";

const SORTS = [
  { key: "index", label: "По индексу закупки" },
  { key: "sales30", label: "По продажам за 30 дней" },
  { key: "sales7", label: "По продажам за 7 дней" },
  { key: "competitors", label: "По числу конкурентов" },
  { key: "price", label: "По минимальной цене" },
  { key: "title", label: "По названию" },
];

export default function Products() {
  const [q, setQ] = useState("");
  const [rating, setRating] = useState("");
  const [sort, setSort] = useState("index");
  const [page, setPage] = useState(1);

  const load = () => api.products({ q, rating, sort, page, page_size: 25 });
  const { data, error, loading } = useAsync(load, [q, rating, sort, page]);

  const search = (value: string) => {
    setQ(value);
    setPage(1);
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Товары</h1>
          <p>Сквозной каталог: один товар — позиции у всех конкурентов</p>
        </div>
        <div className="muted">найдено: {data ? formatNumber(data.total) : "…"}</div>
      </div>

      <div className="card">
        <div className="filters">
          <input
            placeholder="Артикул, OEM или название"
            value={q}
            onChange={(e) => search(e.target.value)}
            style={{ minWidth: 280 }}
          />
          <select value={rating} onChange={(e) => { setRating(e.target.value); setPage(1); }}>
            <option value="">Все рейтинги</option>
            <option value="A">A — ходовой</option>
            <option value="B">B — стабильный</option>
            <option value="C">C — редкий</option>
            <option value="D">D — редкий спрос</option>
            <option value="NEW">NEW — мало данных</option>
          </select>
          <select value={sort} onChange={(e) => { setSort(e.target.value); setPage(1); }}>
            {SORTS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
          {loading ? <span className="muted">загрузка…</span> : null}
        </div>

        {error ? <div className="alert error">{error}</div> : null}

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Товар</th>
                <th>Рейтинг</th>
                <th>Индекс</th>
                <th>Продажи 7/14/30/90</th>
                <th>Частота</th>
                <th>Конкуренты</th>
                <th>Цена min / медиана</th>
                <th>Остаток сегодня</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((item) => (
                <tr key={item.id}>
                  <td style={{ maxWidth: 340 }}>
                    <Link className="link" to={`/products/${item.id}`}>
                      {item.title}
                    </Link>
                    <div className="muted mono">
                      {item.oem}
                      {item.brand ? ` · ${item.brand}` : ""}
                    </div>
                  </td>
                  <td>
                    <RatingBadge rating={item.rating} />
                  </td>
                  <td>{item.index_score.toFixed(1)}</td>
                  <td className="mono">
                    {item.sales_7} / {item.sales_14} / {item.sales_30} / {item.sales_90}
                  </td>
                  <td>{item.frequency_pct.toFixed(1)}%</td>
                  <td>
                    {item.in_stock_competitors}/{item.competitors_count}
                  </td>
                  <td className="mono">
                    {formatMoney(item.min_price)} / {formatMoney(item.median_price)}
                  </td>
                  <td>{formatNumber(item.qty_total)}</td>
                </tr>
              ))}
              {!loading && data?.items.length === 0 ? (
                <tr>
                  <td colSpan={8} className="empty">
                    Ничего не найдено
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <div className="pager">
          <button className="btn small" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            ← Назад
          </button>
          <span className="muted">
            страница {page} из {data?.pages ?? 1}
          </span>
          <button
            className="btn small"
            disabled={!data || page >= data.pages}
            onClick={() => setPage(page + 1)}
          >
            Вперёд →
          </button>
        </div>
      </div>
    </>
  );
}
