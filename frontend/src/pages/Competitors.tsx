import { Fragment, useCallback, useState } from "react";
import { api, formatDateTime } from "../api/client";
import { useAsync } from "../api/useAsync";
import type { Competitor, ProxyCheckResult } from "../api/types";
import { StatusBadge } from "../components/badges";
import { RunBanner } from "../components/RunBanner";

export default function Competitors() {
  const load = useCallback(() => api.competitors(), []);
  const { data, error, reload } = useAsync(load, []);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [openId, setOpenId] = useState<number | null>(null);
  const [proxyValue, setProxyValue] = useState("");
  const [proxyBusy, setProxyBusy] = useState(false);
  const [checkResult, setCheckResult] = useState<ProxyCheckResult | null>(null);

  const toggle = async (competitor: Competitor) => {
    setBusyId(competitor.id);
    setMessage(null);
    try {
      await api.patchCompetitor(competitor.id, { enabled: !competitor.enabled });
      await reload();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const runOne = async (competitor: Competitor) => {
    setBusyId(competitor.id);
    setMessage(null);
    try {
      const result = await api.runCompetitor(competitor.id);
      setMessage(result.started ? `Сбор «${competitor.name}» запущен.` : "Сбор уже выполняется.");
      await reload();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const openSettings = (competitor: Competitor) => {
    if (openId === competitor.id) {
      setOpenId(null);
      setCheckResult(null);
      return;
    }
    setOpenId(competitor.id);
    setProxyValue(String(competitor.config.proxy_url ?? ""));
    setCheckResult(null);
    setMessage(null);
  };

  const saveProxy = async (competitor: Competitor): Promise<Competitor | null> => {
    const config = { ...competitor.config };
    const value = proxyValue.trim();
    if (value) config.proxy_url = value;
    else delete config.proxy_url;
    try {
      const updated = await api.patchCompetitor(competitor.id, { config });
      await reload();
      return updated;
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
      return null;
    }
  };

  const saveProxyAction = async (competitor: Competitor) => {
    setBusyId(competitor.id);
    const saved = await saveProxy(competitor);
    if (saved) {
      setMessage(
        proxyValue.trim()
          ? `Прокси для ${competitor.domain} сохранён.`
          : `Прокси для ${competitor.domain} очищен — соединение напрямую.`,
      );
    }
    setBusyId(null);
  };

  const checkProxyAction = async (competitor: Competitor) => {
    setProxyBusy(true);
    setMessage(null);
    setCheckResult(null);
    try {
      const saved = await saveProxy(competitor);
      if (saved) setCheckResult(await api.proxyCheck(competitor.id));
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setProxyBusy(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Конкуренты</h1>
          <p>11 сайтов из ТЗ: включение, прокси, ручной запуск, результаты последнего сбора</p>
        </div>
      </div>

      <RunBanner onFinished={() => void reload()} />

      {error ? <div className="alert error">{error}</div> : null}
      {message ? <div className="alert ok">{message}</div> : null}

      <div className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Сайт</th>
                <th>Парсер</th>
                <th>Включён</th>
                <th>Позиций (всего / сегодня)</th>
                <th>Последний запуск</th>
                <th>Статус</th>
                <th>Ошибка</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((competitor) => (
                <Fragment key={competitor.id}>
                  <tr>
                    <td>
                      <a className="link" href={competitor.base_url} target="_blank" rel="noreferrer">
                        {competitor.name}
                      </a>
                      <div className="muted mono">{competitor.domain}</div>
                    </td>
                    <td className="mono">{competitor.parser_key}</td>
                    <td>
                      <label className="checkline">
                        <input
                          type="checkbox"
                          checked={competitor.enabled}
                          disabled={busyId === competitor.id}
                          onChange={() => void toggle(competitor)}
                        />
                        {competitor.enabled ? "да" : "нет"}
                      </label>
                    </td>
                    <td className="mono">
                      {competitor.offers_total} / {competitor.offers_today}
                    </td>
                    <td className="muted">
                      {formatDateTime(competitor.last_run?.started_at)}
                      {competitor.last_run ? (
                        <div className="muted">
                          {competitor.last_run.items_found} позиций ·{" "}
                          {Math.round(competitor.last_run.duration_ms / 1000)} c
                        </div>
                      ) : null}
                    </td>
                    <td>
                      <StatusBadge status={competitor.last_run?.status} />
                    </td>
                    <td className="muted" style={{ maxWidth: 300 }}>
                      {competitor.last_run?.error_message
                        ? truncate(competitor.last_run.error_message, 140)
                        : "—"}
                    </td>
                    <td>
                      <div className="row-actions">
                        <button
                          className="btn small"
                          disabled={busyId === competitor.id}
                          onClick={() => void runOne(competitor)}
                        >
                          Собрать
                        </button>
                        <button
                          className={`btn small${openId === competitor.id ? " primary" : ""}`}
                          onClick={() => openSettings(competitor)}
                        >
                          Прокси
                        </button>
                      </div>
                    </td>
                  </tr>
                  {openId === competitor.id ? (
                    <tr>
                      <td colSpan={8}>
                        <div className="proxy-settings">
                          <div className="proxy-field">
                            <label htmlFor={`proxy-${competitor.id}`}>
                              Прокси для {competitor.domain}
                            </label>
                            <input
                              id={`proxy-${competitor.id}`}
                              value={proxyValue}
                              placeholder="host:port · http://user:pass@host:port · socks5://host:port"
                              onChange={(e) => setProxyValue(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") void saveProxyAction(competitor);
                              }}
                            />
                          </div>
                          <div className="row-actions">
                            <button
                              className="btn small primary"
                              disabled={busyId === competitor.id || proxyBusy}
                              onClick={() => void saveProxyAction(competitor)}
                            >
                              Сохранить
                            </button>
                            <button
                              className="btn small"
                              disabled={proxyBusy || busyId === competitor.id}
                              onClick={() => void checkProxyAction(competitor)}
                            >
                              {proxyBusy ? "Проверяем…" : "Проверить"}
                            </button>
                          </div>
                          {checkResult ? (
                            <div className={checkResult.ok ? "alert ok" : "alert error"}>
                              {checkResult.ok
                                ? `Сайт отвечает через ${
                                    checkResult.proxy ?? "прямое соединение"
                                  }: HTTP ${checkResult.status} за ${checkResult.elapsed_ms} мс`
                                : `Проверка не прошла${
                                    checkResult.proxy ? ` (прокси ${checkResult.proxy})` : ""
                                  }: ${checkResult.error ?? "неизвестная ошибка"}`}
                            </div>
                          ) : null}
                          <div className="muted">
                            Пустое поле — напрямую.
                            {checkResult?.source === "global"
                              ? " Сейчас действует общий прокси из переменной PROXY_URL."
                              : ""}
                            {" "}Сохраняется для этого сайта; применяется при следующем сборе.
                          </div>
                        </div>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              ))}
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
