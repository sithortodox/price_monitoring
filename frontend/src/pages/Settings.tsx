import { useCallback, useState } from "react";
import { api } from "../api/client";
import { useAsync } from "../api/useAsync";
import type { IndexWeight, ParserInfo } from "../api/types";

export default function Settings() {
  const loadWeights = useCallback(() => api.weights(), []);
  const loadParsers = useCallback(() => api.parsers(), []);
  const loadSettings = useCallback(() => api.settings(), []);

  const weights = useAsync(loadWeights, []);
  const parsers = useAsync(loadParsers, []);
  const settings = useAsync(loadSettings, []);

  const [draft, setDraft] = useState<IndexWeight[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const list = draft ?? weights.data ?? [];

  const update = (key: string, patch: Partial<IndexWeight>) => {
    setDraft(list.map((item) => (item.key === key ? { ...item, ...patch } : item)));
  };

  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await api.saveWeights(list);
      setDraft(null);
      await weights.reload();
      setMessage("Веса индекса сохранены. Пересчитайте аналитику на Главной или вручную.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const app = settings.data;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Настройки</h1>
          <p>Веса индекса закупки, расписание и параметры сборщика</p>
        </div>
      </div>

      {message ? <div className="alert ok">{message}</div> : null}
      {weights.error ? <div className="alert error">{weights.error}</div> : null}

      <div className="grid cols-2">
        <div className="card">
          <h2>Веса факторов индекса спроса (п.12 ТЗ)</h2>
          <p className="muted" style={{ fontSize: 12 }}>
            Итоговый индекс 0–100 = взвешенная сумма нормализованных факторов. Отключённые факторы
            не участвуют.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Фактор</th>
                  <th>Вес</th>
                  <th>Учитывать</th>
                </tr>
              </thead>
              <tbody>
                {list.map((item) => (
                  <tr key={item.key}>
                    <td>{item.label}</td>
                    <td>
                      <input
                        type="number"
                        min={0}
                        max={10}
                        step={0.1}
                        value={item.weight}
                        onChange={(e) => update(item.key, { weight: Number(e.target.value) })}
                      />
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={item.enabled}
                        onChange={(e) => update(item.key, { enabled: e.target.checked })}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="row-actions" style={{ marginTop: 12 }}>
            <button className="btn primary" onClick={() => void save()} disabled={saving}>
              {saving ? "Сохраняем…" : "Сохранить веса"}
            </button>
            <button className="btn" onClick={() => setDraft(null)} disabled={!draft}>
              Отменить правки
            </button>
          </div>
        </div>

        <div className="card">
          <h2>Расписание и параметры</h2>
          {app ? (
            <dl className="kv">
              <dt>Плановый сбор</dt>
              <dd>
                {app.scheduler_enabled
                  ? `ежедневно в ${String(app.schedule_hour).padStart(2, "0")}:${String(
                      app.schedule_minute,
                    ).padStart(2, "0")} (${app.timezone})`
                  : "выключен"}
              </dd>
              <dt>Пауза между запросами</dt>
              <dd>{app.http_delay_sec} c</dd>
              <dt>Лимит страниц на сайт</dt>
              <dd>{app.max_pages_per_site}</dd>
              <dt>Срок «исчезновения»</dt>
              <dd>{app.vanished_grace_days} дня без данных до пометки «исчез»</dd>
              <dt>Дней наблюдения для рейтинга</dt>
              <dd>{app.history_days_required_for_rating} (до этого рейтинг NEW)</dd>
            </dl>
          ) : (
            <div className="muted">Загрузка…</div>
          )}

          <h2 style={{ marginTop: 20 }}>Реестр парсеров</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Ключ</th>
                  <th>Название</th>
                  <th>URL</th>
                  <th>Браузер</th>
                </tr>
              </thead>
              <tbody>
                {(parsers.data ?? []).map((parser: ParserInfo) => (
                  <tr key={parser.key}>
                    <td className="mono">{parser.key}</td>
                    <td>{parser.name}</td>
                    <td className="muted" style={{ maxWidth: 320 }}>
                      {parser.urls}
                    </td>
                    <td>{parser.use_browser === "True" ? "да" : "нет"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
