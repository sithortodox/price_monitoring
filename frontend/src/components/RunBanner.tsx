import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { RunStatus } from "../api/types";

export function useRunStatus(pollMs = 3000) {
  const [status, setStatus] = useState<RunStatus | null>(null);

  const refresh = async () => {
    try {
      setStatus(await api.runStatus());
    } catch {
      /* статус недоступен — не блокируем интерфейс */
    }
  };

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), pollMs);
    return () => clearInterval(timer);
  }, [pollMs]);

  return { status, refresh };
}

export function RunBanner({ onFinished }: { onFinished?: () => void }) {
  const { status, refresh } = useRunStatus();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const prevRunning = useRef(false);

  useEffect(() => {
    const running = Boolean(status?.running);
    if (prevRunning.current && !running) {
      onFinished?.();
    }
    prevRunning.current = running;
  }, [status, onFinished]);

  const start = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.startRun(null);
      if (!result.started) setMessage("Сбор уже выполняется — дождитесь окончания.");
      await refresh();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="alert info"
      style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}
    >
      {status?.running ? (
        <>
          <span className="spinner" />
          <span>
            Идёт сбор данных: {status.trigger === "auto" ? "плановый запуск" : "ручной запуск"}
            {status.started_at ? ` с ${status.started_at}` : ""}
          </span>
        </>
      ) : (
        <span>
          {status?.error
            ? `Последняя ошибка: ${status.error}`
            : status?.finished_at
              ? `Сбор не выполняется. Последнее завершение: ${status.finished_at}`
              : "Сбор сейчас не выполняется."}
        </span>
      )}
      <button className="btn primary" onClick={() => void start()} disabled={busy || status?.running}>
        {busy || status?.running ? "Собираем…" : "Запустить сбор"}
      </button>
      <button className="btn" onClick={() => void refresh()}>
        Обновить статус
      </button>
      {message ? <span className="muted">{message}</span> : null}
    </div>
  );
}
