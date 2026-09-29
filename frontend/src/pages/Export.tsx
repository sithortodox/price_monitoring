import { useState } from "react";
import { api } from "../api/client";

export default function Export() {
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10));
  const [historyDays, setHistoryDays] = useState(30);

  const download = (date?: string) => {
    const url = api.exportUrl(date, historyDays);
    const link = document.createElement("a");
    link.href = url;
    link.download = `monitoring_${date || new Date().toISOString().slice(0, 10)}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Выгрузка Excel</h1>
          <p>Файл .xlsx с 4 листами: Сводка, Аналитика спроса, Цены конкурентов, Остатки и изменения</p>
        </div>
      </div>

      <div className="card">
        <p className="muted">
          Лист «Остатки и изменения» формируется за выбранный период, лист «Аналитика спроса» —
          срез на дату. В файл попадает подпись: «Предполагаемые продажи рассчитаны по снижению
          остатков и не являются фактическими данными».
        </p>

        <div className="filters">
          <label className="muted">Дата отчёта</label>
          <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
          <label className="muted">История, дней</label>
          <input
            type="number"
            min={1}
            max={365}
            value={historyDays}
            onChange={(e) => setHistoryDays(Number(e.target.value))}
            style={{ minWidth: 90 }}
          />
          <button className="btn primary" onClick={() => download(day)}>
            Скачать .xlsx за дату
          </button>
          <button className="btn" onClick={() => download()}>
            За сегодня
          </button>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Лист</th>
                <th>Содержимое</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Сводка</td>
                <td>Итоги дня, распределение рейтингов, состояние сайтов конкурентов</td>
              </tr>
              <tr>
                <td>Аналитика спроса</td>
                <td>Окна спроса 1/7/14/30/60/90, частота, рейтинг, индекс, цены</td>
              </tr>
              <tr>
                <td>Цены конкурентов</td>
                <td>Позиция × сайт: цена, скидка, наличие, остаток, ссылка</td>
              </tr>
              <tr>
                <td>Остатки и изменения</td>
                <td>Снимки за период: Δостатка, тип изменения, комментарий</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
