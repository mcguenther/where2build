/** German number, area, price and duration formatting. One place, so the
 *  decimal separator and thousands grouping cannot drift between views. */

const decimal = digits =>
  new Intl.NumberFormat("de-DE", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export const num = (value, digits = 2) =>
  Number.isFinite(value) ? decimal(digits).format(value) : "—";

export const area = (value, digits = 0) => (Number.isFinite(value) ? `${num(value, digits)} m²` : "—");

export const euro = value =>
  Number.isFinite(value)
    ? new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(value)
    : "—";

export const euroPerSqm = value => (Number.isFinite(value) ? `${num(value, 2)} €` : "—");

export const metres = (value, digits = 2) => (Number.isFinite(value) ? `${num(value, digits)} m` : "—");

export const degrees = value =>
  Number.isFinite(value) ? `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(Math.round(value))}°` : "—";

/** Signed percentage, using a real minus sign rather than a hyphen. */
export const percent = (value, digits = 1) =>
  Number.isFinite(value) ? `${value > 0 ? "+" : value < 0 ? "−" : ""}${num(Math.abs(value), digits)} %` : "—";

/**
 * A travel time, from the seconds the routing service returns. Minutes are the
 * unit people compare commutes in; below one minute the number says nothing
 * useful, above an hour it stops being readable.
 */
export const duration = seconds => {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  const min = Math.round(seconds / 60);
  if (min < 1) return "unter 1 min";
  if (min < 90) return `${min} min`;
  return `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")} min`;
};

export const date = iso => {
  const d = iso instanceof Date ? iso : new Date(iso);
  return Number.isNaN(d.valueOf())
    ? "—"
    : d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
};
