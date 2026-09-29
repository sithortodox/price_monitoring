export function RatingBadge({ rating }: { rating: string }) {
  return <span className={`badge rating-${rating}`}>{rating}</span>;
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span className="badge status-neutral">—</span>;
  const label: Record<string, string> = {
    success: "успешно",
    partial: "частично",
    error: "ошибка",
    running: "выполняется",
  };
  return <span className={`badge status-${status}`}>{label[status] || status}</span>;
}

export function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="card stat-card">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub ? <div className="sub">{sub}</div> : null}
    </div>
  );
}
