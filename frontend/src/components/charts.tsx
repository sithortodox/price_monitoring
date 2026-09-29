interface Point {
  x: string;
  y: number | null;
}

export interface Series {
  name: string;
  color: string;
  points: Point[];
}

function niceMax(value: number): number {
  if (value <= 0) return 1;
  const exp = Math.floor(Math.log10(value));
  const base = Math.pow(10, exp);
  const norm = value / base;
  const step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
  return step * base;
}

export function LineChart({
  series,
  height = 220,
  yFormat = (v: number) => String(v),
}: {
  series: Series[];
  height?: number;
  yFormat?: (v: number) => string;
}) {
  const width = 800;
  const padLeft = 56;
  const padRight = 14;
  const padTop = 12;
  const padBottom = 26;

  const allPoints = series.flatMap((s) => s.points);
  if (allPoints.length === 0) {
    return <div className="empty">Нет данных для графика</div>;
  }

  const xs = allPoints.map((p) => p.x);
  const uniqueX = Array.from(new Set(xs)).sort();
  const xIndex = new Map(uniqueX.map((x, i) => [x, i]));
  const maxValue = niceMax(Math.max(...allPoints.map((p) => p.y ?? 0), 1));
  const innerW = width - padLeft - padRight;
  const innerH = height - padTop - padBottom;

  const toX = (x: string) => {
    const i = xIndex.get(x) ?? 0;
    const denom = Math.max(1, uniqueX.length - 1);
    return padLeft + (i / denom) * innerW;
  };
  const toY = (y: number) => padTop + innerH - (y / maxValue) * innerH;

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * maxValue);
  const xStep = Math.max(1, Math.ceil(uniqueX.length / 8));

  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img">
        {yTicks.map((tick) => (
          <g key={tick}>
            <line className="gridline" x1={padLeft} x2={width - padRight} y1={toY(tick)} y2={toY(tick)} />
            <text className="label" x={4} y={toY(tick) + 3}>
              {yFormat(tick)}
            </text>
          </g>
        ))}
        <line className="axis" x1={padLeft} x2={padLeft} y1={padTop} y2={height - padBottom} />
        <line
          className="axis"
          x1={padLeft}
          x2={width - padRight}
          y1={height - padBottom}
          y2={height - padBottom}
        />
        {uniqueX
          .filter((_, i) => i % xStep === 0)
          .map((x) => (
            <text key={x} className="label" x={toX(x)} y={height - 8} textAnchor="middle">
              {x}
            </text>
          ))}
        {series.map((s) => {
          const segments: string[] = [];
          let current: string[] = [];
          s.points.forEach((p) => {
            if (p.y === null) {
              if (current.length) segments.push(current.join(" "));
              current = [];
              return;
            }
            current.push(`${toX(p.x)},${toY(p.y)}`);
          });
          if (current.length) segments.push(current.join(" "));
          return (
            <g key={s.name}>
              {segments.map((seg, i) => (
                <polyline key={i} points={seg} fill="none" stroke={s.color} strokeWidth={2} />
              ))}
            </g>
          );
        })}
      </svg>
      <div className="legend">
        {series.map((s) => (
          <span key={s.name}>
            <span className="dot" style={{ background: s.color }} />
            {s.name}
          </span>
        ))}
      </div>
    </div>
  );
}

export function BarChart({
  data,
  height = 200,
  format = (v: number) => String(v),
}: {
  data: { label: string; value: number; color?: string }[];
  height?: number;
  format?: (v: number) => string;
}) {
  const width = 800;
  const padLeft = 46;
  const padRight = 10;
  const padTop = 10;
  const padBottom = 34;
  if (!data.length) return <div className="empty">Нет данных</div>;

  const max = niceMax(Math.max(...data.map((d) => d.value), 1));
  const innerW = width - padLeft - padRight;
  const innerH = height - padTop - padBottom;
  const slot = innerW / data.length;
  const barW = Math.min(56, slot * 0.6);

  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img">
      <line className="axis" x1={padLeft} x2={padLeft} y1={padTop} y2={height - padBottom} />
      <line
        className="axis"
        x1={padLeft}
        x2={width - padRight}
        y1={height - padBottom}
        y2={height - padBottom}
      />
      {[0, 0.5, 1].map((f) => (
        <text key={f} className="label" x={4} y={padTop + innerH - f * innerH + 3}>
          {format(f * max)}
        </text>
      ))}
      {data.map((d, i) => {
        const h = (d.value / max) * innerH;
        const x = padLeft + i * slot + (slot - barW) / 2;
        const y = padTop + innerH - h;
        return (
          <g key={d.label}>
            <rect
              x={x}
              y={y}
              width={barW}
              height={Math.max(h, d.value > 0 ? 2 : 0)}
              rx={4}
              fill={d.color || "#3b82f6"}
            />
            <text className="label" x={x + barW / 2} y={height - 16} textAnchor="middle">
              {d.label}
            </text>
            <text className="label" x={x + barW / 2} y={y - 4} textAnchor="middle">
              {format(d.value)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
