import { ReactNode } from "react";
import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/", label: "Главная", end: true },
  { to: "/products", label: "Товары" },
  { to: "/top", label: "ТОП спроса" },
  { to: "/competitors", label: "Конкуренты" },
  { to: "/history", label: "История запусков" },
  { to: "/export", label: "Выгрузка Excel" },
  { to: "/settings", label: "Настройки" },
];

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          Мониторинг запчастей
          <small>цены · остатки · спрос конкурентов</small>
        </div>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
          >
            {item.label}
          </NavLink>
        ))}
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
