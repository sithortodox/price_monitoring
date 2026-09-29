import { useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import { api, formatDate, formatMoney } from "../api/client";
import { useAsync } from "../api/useAsync";
import { RatingBadge } from "../components/badges";
import { LineChart } from "../components/charts";

const AVAIL_LABEL: Record<string, string> = {
  in_stock: "в наличии",
  out_of_stock: "нет в наличии",
  on_order: "под заказ",
  many: "много",
  unknown: "неизвестно",
  disappeared: "исчез из каталога",
};

export default function ProductDetail() {
  const { id } = useParams();
  const productId = Number(id);

  const load = useCallback(() => api.product(productId), [productId]);
  const { data, error, loading } = useAsync(load, [productId]);

  if (loading) return <div className="muted">Загрузка карточки…</div>;
  if (error) return <div className="alert error">{error}</div>;
  if (!data) return null;

  const { product, stats, offers, series, note } = data;
  const qtySeries = series.map((p) => ({ x: shortDate(p.day), y: p.qty_total }));
  const priceSeries = series.map((p) => ({ x: shortDate(p.day), y: p.min_price }));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{product.title}</h1>
          <p>
            <Link className="link" to="/products">
              ← к списку товаров
            </Link>{" "}
            · {product.category || "категория неизвестна"}
            {product.brand ? ` · ${product.brand}` : ""}
            {product.manufacturer ? ` · ${product.manufacturer}` : ""}
          </p>
        </div>
        {stats ? <RatingBadge rating={stats.rating} /> : null}
      </div>

      <div className="card">
        <h2>Карточка товара</h2>
        <dl className="kv">
          <dt>OEM / артикул</dt>
          <dd className="mono">{product.oem || product.article || "—"}</dd>
          <dt>Кросс-номера</dt>
          <dd className="mono">{product.alt_numbers?.join(", ") || "—"}</dd>
          <dt>Применимость</dt>
          <dd>{product.applicability || "—"}</dd>
          <dt>Впервые обнаружен</dt>
          <dd>{formatDate(product.first_seen_at)}</dd>
          <dt>Статус</dt>
          <dd>{product.vanished ? "исчез у всех конкурентов" : "присутствует в каталогах"}</dd>
        </dl>
      </div>

      {stats ? (
        <>
          <div className="grid cols-4" style={{ margin: "16px 0" }}>
            <div className="card stat-card">
              <div className="label">Индекс закупки</div>
              <div className="value">{stats.index_score.toFixed(1)}</div>
              <div className="sub">из 100, настраиваемые веса</div>
            </div>
            <div className="card stat-card">
              <div className="label">Предполагаемые продажи</div>
              <div className="value">
                {stats.sales_7} / {stats.sales_30}
              </div>
              <div className="sub">за 7 / 30 дней</div>
            </div>
            <div className="card stat-card">
              <div className="label">Частота снижения остатка</div>
              <div className="value">{stats.frequency_pct.toFixed(1)}%</div>
              <div className="sub">
                дней наблюдения: {stats.days_observed}, дней с продажами: {stats.sale_days}
              </div>
            </div>
            <div className="card stat-card">
              <div className="label">Конкуренты с товаром</div>
              <div className="value">
                {stats.in_stock_competitors}/{stats.competitors_count}
              </div>
              <div className="sub">мин. цена: {formatMoney(stats.min_price)}</div>
            </div>
          </div>

          <div className="card">
            <h2>Окна спроса (предполагаемые продажи)</h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>1 день</th>
                    <th>7 дней</th>
                    <th>14 дней</th>
                    <th>30 дней</th>
                    <th>60 дней</th>
                    <th>90 дней</th>
                    <th>Пополнений за 30 дней</th>
                    <th>В среднем в день</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>{stats.sales_1}</td>
                    <td>{stats.sales_7}</td>
                    <td>{stats.sales_14}</td>
                    <td>{stats.sales_30}</td>
                    <td>{stats.sales_60}</td>
                    <td>{stats.sales_90}</td>
                    <td>{stats.restocks_30}</td>
                    <td>{stats.avg_daily_sales.toFixed(2)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="muted" style={{ fontSize: 12 }}>
              {note}
            </p>
          </div>
        </>
      ) : (
        <div className="alert info" style={{ marginTop: 16 }}>
          Аналитика появится после первого пересчёта — нужно минимум несколько дневных снимков.
        </div>
      )}

      <div className="grid cols-2">
        <div className="card">
          <h2>Остаток у всех конкурентов</h2>
          <LineChart series={[{ name: "Суммарный остаток", color: "#3b82f6", points: qtySeries }]} />
        </div>
        <div className="card">
          <h2>Минимальная цена</h2>
          <LineChart
            series={[{ name: "Мин. цена", color: "#22c55e", points: priceSeries }]}
            yFormat={(v) => formatMoney(v)}
          />
        </div>
      </div>

      <div className="card">
        <h2>Позиции у конкурентов</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Конкурент</th>
                <th>Цена</th>
                <th>Скидка</th>
                <th>Остаток</th>
                <th>Наличие</th>
                <th>Срок поставки</th>
                <th>Ссылка</th>
              </tr>
            </thead>
            <tbody>
              {offers.map((offer) => (
                <tr key={`${offer.competitor_id}-${offer.url}`}>
                  <td>{offer.competitor_name}</td>
                  <td className="mono">{formatMoney(offer.price)}</td>
                  <td>{offer.discount_pct ? `${offer.discount_pct}%` : "—"}</td>
                  <td>{offer.qty ?? (offer.qty_text || "—")}</td>
                  <td>{AVAIL_LABEL[offer.availability] || offer.availability}</td>
                  <td>{offer.delivery_time || "—"}</td>
                  <td>
                    <a className="link" href={offer.url} target="_blank" rel="noreferrer">
                      открыть
                    </a>
                  </td>
                </tr>
              ))}
              {offers.length === 0 ? (
                <tr>
                  <td colSpan={7} className="empty">
                    Позиции ещё не собраны
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

function shortDate(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${day}.${month}`;
}
