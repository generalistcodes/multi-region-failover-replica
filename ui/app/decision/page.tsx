"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Decision = {
  can_failover: boolean;
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  checks: Record<string, boolean>;
  metrics: Record<string, any>;
};

type Status = {
  active_region: "region-a" | "region-b";
  regions: Record<
    string,
    {
      db_healthy: boolean;
      role?: "primary" | "standby";
      in_recovery?: boolean;
      replica_lag_seconds?: number | null;
      error?: string;
    }
  >;
};

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { ...init, cache: "no-store" });
  const text = await r.text();
  if (!r.ok) throw new Error(text || r.statusText);
  return JSON.parse(text) as T;
}

function pill(bg: string, fg: string) {
  return { display: "inline-block", padding: "2px 8px", borderRadius: 999, background: bg, color: fg, fontWeight: 800, fontSize: 12 };
}

function CheckRow({ label, state }: { label: string; state: "pass" | "fail" | "warn" }) {
  const color =
    state === "pass"
      ? { bg: "#e7f7ee", fg: "#146c2e", icon: "✔" }
      : state === "fail"
        ? { bg: "#fdecec", fg: "#8a1f1f", icon: "✖" }
        : { bg: "#fff7df", fg: "#7a5b00", icon: "⚠" };
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: "6px 8px", borderBottom: "1px solid #f1f1f1" }}>
      <div>
        <span style={{ ...pill(color.bg, color.fg), marginRight: 8 }}>{color.icon}</span>
        <span style={{ fontWeight: 700 }}>{label}</span>
      </div>
      <div style={{ color: color.fg, fontWeight: 800, textTransform: "uppercase", fontSize: 12 }}>{state}</div>
    </div>
  );
}

export default function DecisionPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [error, setError] = useState<string | null>(null);
  const prevSig = useRef<string>("");
  const [changedAt, setChangedAt] = useState<number | null>(null);

  const overview = useMemo(() => {
    const active = status?.active_region;
    const a = status?.regions?.["region-a"];
    const b = status?.regions?.["region-b"];
    return { active, a, b };
  }, [status]);

  function classifyChecks(d: Decision | null) {
    const c = d?.checks ?? {};
    const lagOk = c["replication_lag_ok"];
    const walFresh = c["wal_fresh"];
    const map: Array<{ k: string; label: string; state: "pass" | "fail" | "warn" }> = [
      { k: "primary_reachable", label: "Primary reachable (region-a)", state: c["primary_reachable"] ? "pass" : "fail" },
      { k: "failure_stable", label: "Failure stable for N seconds", state: c["failure_stable"] ? "pass" : "warn" },
      { k: "replica_healthy", label: "Replica healthy (region-b)", state: c["replica_healthy"] ? "pass" : "fail" },
      { k: "replication_lag_ok", label: "Replication lag below threshold", state: lagOk ? "pass" : "fail" },
      { k: "wal_fresh", label: "WAL replay is fresh", state: walFresh ? "pass" : "fail" },
      { k: "no_split_brain", label: "No split brain detected", state: c["no_split_brain"] ? "pass" : "fail" },
    ];
    return map;
  }

  async function refresh() {
    try {
      setError(null);
      const [s, d] = await Promise.all([j<Status>("/api/status"), j<Decision>("/api/decision")]);
      setStatus(s);
      setDecision(d);

      const sig = JSON.stringify({ s, d });
      if (prevSig.current && prevSig.current !== sig) setChangedAt(Date.now());
      prevSig.current = sig;
    } catch (e: any) {
      setError(e?.message ?? String(e));
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);

  const risk = decision?.risk_level ?? "HIGH";
  const riskStyle =
    risk === "LOW" ? pill("#e7f7ee", "#146c2e") : risk === "MEDIUM" ? pill("#fff7df", "#7a5b00") : pill("#fdecec", "#8a1f1f");

  const decisionText = decision?.can_failover ? "SAFE TO FAILOVER" : "BLOCKED — conditions not met";
  const decisionColor = decision?.can_failover ? "#146c2e" : "#8a1f1f";

  return (
    <div style={{ padding: 16, maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 900 }}>Failover Decision Dashboard</div>
          <div style={{ fontSize: 13, color: "#666" }}>
            Auto-refresh every 2s. This explains <b>why failover is allowed or blocked</b>.
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <div>
            <div style={{ color: "#666", fontSize: 12 }}>Risk level</div>
            <div style={riskStyle}>{risk}</div>
          </div>
          <button onClick={refresh} style={{ padding: "8px 10px" }}>
            Refresh now
          </button>
        </div>
      </div>

      {changedAt ? (
        <div style={{ marginTop: 10, padding: 8, border: "1px solid #e6e6e6", borderRadius: 8, background: "#fafafa", fontSize: 12 }}>
          State changed at: <b>{new Date(changedAt).toLocaleTimeString()}</b>
        </div>
      ) : null}

      {error ? (
        <div style={{ marginTop: 12, padding: 10, border: "1px solid #f3c2c2", background: "#fff5f5", borderRadius: 8, color: "#8a1f1f" }}>
          {error}
        </div>
      ) : null}

      <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12 }}>
          <div style={{ fontWeight: 800, marginBottom: 8 }}>A) Status overview</div>
          <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 8, fontSize: 13 }}>
            <div style={{ color: "#666" }}>Active region</div>
            <div style={{ fontWeight: 800 }}>{overview.active ?? "…"}</div>

            <div style={{ color: "#666" }}>Region A role</div>
            <div style={{ fontWeight: 700 }}>
              {overview.a?.role ?? "?"} (in_recovery={String(overview.a?.in_recovery ?? "?")})
            </div>

            <div style={{ color: "#666" }}>Region B role</div>
            <div style={{ fontWeight: 700 }}>
              {overview.b?.role ?? "?"} (in_recovery={String(overview.b?.in_recovery ?? "?")})
            </div>

            <div style={{ color: "#666" }}>Replica lag</div>
            <div style={{ fontWeight: 700 }}>
              {typeof overview.b?.replica_lag_seconds === "number" ? `${overview.b?.replica_lag_seconds.toFixed(2)}s` : "…"}
            </div>
          </div>
        </div>

        <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12 }}>
          <div style={{ fontWeight: 800, marginBottom: 8 }}>D) Failover decision</div>
          <div style={{ fontSize: 18, fontWeight: 900, color: decisionColor }}>{decisionText}</div>
          <div style={{ marginTop: 8, fontSize: 12, color: "#666" }}>
            Failover is allowed only when: primary unreachable for N seconds, replica healthy, lag OK, WAL fresh, no split brain, failure stable.
          </div>
        </div>
      </div>

      <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12 }}>
          <div style={{ fontWeight: 800, marginBottom: 8 }}>B) Criteria checklist</div>
          <div style={{ border: "1px solid #f1f1f1", borderRadius: 8, overflow: "hidden" }}>
            {classifyChecks(decision).map((c) => (
              <CheckRow key={c.k} label={c.label} state={c.state} />
            ))}
          </div>
        </div>

        <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12 }}>
          <div style={{ fontWeight: 800, marginBottom: 8 }}>E) Metrics (explainers, not raw dump)</div>
          <div style={{ fontSize: 13, color: "#333", lineHeight: 1.5 }}>
            <div>
              <b>failure_duration</b>: {decision?.metrics?.failure_duration?.toFixed?.(2) ?? "…"}s (must exceed{" "}
              {decision?.metrics?.failure_stable_seconds ?? "…"}s)
            </div>
            <div>
              <b>wal_lag_bytes</b>: {decision?.metrics?.wal_lag_bytes ?? "…"} (must be ≤ {decision?.metrics?.wal_lag_bytes_threshold ?? "…"})
            </div>
            <div>
              <b>caught_up</b>: {String(decision?.metrics?.caught_up ?? "…")}
            </div>
            <div style={{ color: "#666", marginTop: 8 }}>
              Note: <b>replication_lag_seconds</b> can grow while idle (no new transactions). Promotion gating uses WAL lag bytes instead.
            </div>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 12, fontSize: 12, color: "#666" }}>
        Tip: open <b>/</b> for data replication view, and <b>/decision</b> for the decision transparency panel.
      </div>
    </div>
  );
}

