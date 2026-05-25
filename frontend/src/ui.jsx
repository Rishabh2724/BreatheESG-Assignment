// Small shared UI atoms: status pills, flag badges, plain-English flag explanations.
// The flag glossary matters for the "non-engineer can use this" goal — an analyst should
// never have to ask an engineer what UNMAPPED_CODE means.

export const FLAG_HELP = {
  MISSING_QTY: "No quantity in the source row — cannot compute emissions.",
  NEGATIVE_QTY: "Quantity is negative (often a reversal/correction posting).",
  MISSING_UNIT: "Unit was missing or unrecognised, so it wasn't normalized.",
  UNMAPPED_CODE: "The site/plant code isn't in the facility lookup — assign a facility.",
  NO_FACTOR: "No emission factor matched this row, so CO2e is blank.",
  OUTLIER: "Value is unusually large for this activity — sanity-check it.",
  POSSIBLE_DUPLICATE: "Same facility, category and period already arrived in another batch.",
  DISTANCE_ESTIMATED: "Flight distance was estimated from airport codes, not given.",
};

const STATUS_COLORS = {
  pending: "#6b7280",
  flagged: "#b45309",
  approved: "#15803d",
  rejected: "#b91c1c",
  locked: "#1d4ed8",
};

export function StatusPill({ status }) {
  return (
    <span className="pill" style={{ background: STATUS_COLORS[status] || "#6b7280" }}>
      {status}
    </span>
  );
}

export function FlagBadge({ flag }) {
  return (
    <span className="flag" title={FLAG_HELP[flag] || flag}>
      {flag}
    </span>
  );
}

export function ScopeTag({ scope }) {
  return <span className={`scope scope-${scope}`}>Scope {scope}</span>;
}

export const fmt = (n) =>
  n == null ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 });
