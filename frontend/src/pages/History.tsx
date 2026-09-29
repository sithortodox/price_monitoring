import { useCallback } from "react";
import { api, formatDateTime } from "../api/client";
import { useAsync } from "../api/useAsync";
import { StatusBadge } from "../components/badges";

export default function History() {
  const load = useCallback(() => api.runs(100), []);
  const { data, error, loading, reload } = useAsync(load, []);

  const byStatus = (status: string) => (data ?? []).filter((r) => r.status === status).length;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>История запусков</h1>
          <p>Журнал сборщика: что, когда и с каким результатом собиралось (п.24 ТЗ)</p>
        </div>
        <button className="btn" onClick={() => void reload()}>
          Обновить
        </button>
      </div>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="card stat-card">
          <div className="label">Всего запусков</div>
          <div className="value">{data?.length ?? "…"}</div>
        </div>
        <div className="card stat-card">
          <div className="label">Успешно</div>
          <div className="value">{byStatus("success")}</div>
        </div>
        <div className="card stat-card">
          <div className="label">Частично</div>
          <div className="value">{byStatus("partial")}</div>
        </div>
        <div className="card stat-card">
          <div className="label">С ошибками</div>
          <div className="value">{byStatus("error")}</div>
        </div>
      </div>

      <div className="card">
        {error ? <div className="alert error">{error}</div> : null}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Начато</th>
                <th>Сайт</th>
                <th>Триггер</th>
                <th>Статус</th>
                <th>Страниц</th>
                <th>Позиций</th>
                <th>Записано предложений</th>
                <th>Ошибок</th>
                <th>Длительность</th>
                <th>Сообщение</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((run) => (
                <tr key={run.id}>
                  <td className="muted">{formatDateTime(run.started_at)}</td>
                  <td>{run.competitor_name || run.competitor_id}</td>
                  <td>{run.trigger === "auto" ? "плановый" : "ручной"}</td>
                  <td>
                    <StatusBadge status={run.status} />
                  </td>
                  <td>{run.pages_fetched}</td>
                  <td>{run.items_found}</td>
                  <td>{run.offers_written}</td>
                  <td>{run.errors_count}</td>
                  <td>{(run.duration_ms / 1000).toFixed(1)} c</td>
                  <td className="muted" style={{ maxWidth: 360 }}>
                    {run.error_message ? truncate(run.error_message, 180) : "—"}
                  </td>
                </tr>
              ))}
              {!loading && data?.length === 0 ? (
                <tr>
                  <td colSpan={10} className="empty">
                    Запусков ещё не было
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

function truncate(text: string, size: number): string {
  return text.length > size ? text.slice(0, size) + "…" : text;
}
