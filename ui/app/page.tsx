"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type KvRow = { k: string; v: string; updated_at: string };

type Status = {
  active_region: string;
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
  replication?: any[];
  replication_error?: string;
};

type Dashboard = {
  status: Status;
  rows: Record<string, KvRow[] | { error: string }>;
  limit: number;
};

type Infra = {
  regions: Record<
    string,
    {
      region: string;
      compose?: { service?: string; container?: string };
      network?: { network?: string; ip?: string | null };
      resources?: { cpu_percent?: number | null; mem_usage_bytes?: number | null; mem_limit_bytes?: number | null };
      mounts?: Array<{ type?: string; name?: string; destination?: string; source?: string }>;
      ports?: any;
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

function bytes(n?: number | null) {
  if (n === null || n === undefined) return "—";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i === 0 ? 0 : 2)} ${units[i]}`;
}

function RegionPanel({ region, rows, infra }: { region: string; rows: KvRow[]; infra?: Infra["regions"][string] }) {
  const ip = infra?.network?.ip ?? "—";
  const cpu = infra?.resources?.cpu_percent;
  const memU = infra?.resources?.mem_usage_bytes;
  const memL = infra?.resources?.mem_limit_bytes;
  const vol = (infra?.mounts ?? []).find((m) => m.destination === "/var/lib/postgresql/data");

  return (
    <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12 }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>{region}</div>
      <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>
        Latest {rows.length} rows (sorted by updated_at desc)
      </div>
      <div style={{ maxHeight: 360, overflow: "auto" }}>
        {rows.length === 0 ? (
          <div style={{ color: "#888" }}>No rows yet.</div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", borderBottom: "1px solid #eee", padding: "6px 4px" }}>k</th>
                <th style={{ textAlign: "left", borderBottom: "1px solid #eee", padding: "6px 4px" }}>v</th>
                <th style={{ textAlign: "left", borderBottom: "1px solid #eee", padding: "6px 4px" }}>updated_at</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.k}>
                  <td style={{ borderBottom: "1px solid #f3f3f3", padding: "6px 4px", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
                    {r.k}
                  </td>
                  <td style={{ borderBottom: "1px solid #f3f3f3", padding: "6px 4px" }}>{r.v}</td>
                  <td style={{ borderBottom: "1px solid #f3f3f3", padding: "6px 4px", color: "#666" }}>{r.updated_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid #eee", fontSize: 12, color: "#444" }}>
        <div style={{ fontWeight: 800, marginBottom: 6 }}>Region specs (container)</div>
        {infra?.error ? (
          <div style={{ color: "#8a1f1f" }}>{infra.error}</div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: 6 }}>
            <div style={{ color: "#666" }}>compose</div>
            <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
              {infra?.compose?.service ?? "—"} / {infra?.compose?.container ?? "—"}
            </div>
            <div style={{ color: "#666" }}>ip</div>
            <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>{ip}</div>
            <div style={{ color: "#666" }}>cpu</div>
            <div>{cpu === null || cpu === undefined ? "—" : `${cpu.toFixed(1)}%`}</div>
            <div style={{ color: "#666" }}>ram</div>
            <div>
              {bytes(memU)} / {bytes(memL)}
            </div>
            <div style={{ color: "#666" }}>storage</div>
            <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>{vol?.name ?? vol?.source ?? "—"}</div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  const [status, setStatus] = useState<Status | null>(null);
  const [rowsByRegion, setRowsByRegion] = useState<Record<string, KvRow[]>>({});
  const [infra, setInfra] = useState<Infra | null>(null);
  const [visibleRegions, setVisibleRegions] = useState<Record<string, boolean>>({});
  const [key, setKey] = useState("hello");
  const [value, setValue] = useState(`v-${Date.now()}`);
  const [error, setError] = useState<string | null>(null);
  const [lastWrite, setLastWrite] = useState<{ region: string; updated_at: string } | null>(null);

  const visibleRegionsRef = useRef<Record<string, boolean>>({});
  useEffect(() => {
    visibleRegionsRef.current = visibleRegions;
  }, [visibleRegions]);

  const lag = useMemo(() => status?.regions?.["region-b"]?.replica_lag_seconds, [status]);
  const regionNames = useMemo(() => Object.keys(status?.regions ?? {}).sort(), [status]);
  const shownRegions = useMemo(
    () => regionNames.filter((r) => visibleRegions[r] ?? true),
    [regionNames, visibleRegions]
  );

  const refreshStatusAndRows = useCallback(async () => {
    try {
      setError(null);
      const d = await j<Dashboard>("/api/dashboard");
      const s = d.status;
      setStatus(s);
      const regions = Object.keys(s.regions ?? {});
      setVisibleRegions((prev) => {
        const next = { ...prev };
        for (const r of regions) if (next[r] === undefined) next[r] = true;
        return next;
      });

      const currentVisible = visibleRegionsRef.current;
      const m: Record<string, KvRow[]> = {};
      for (const r of regions) {
        if (!(currentVisible[r] ?? true)) continue;
        const payload = d.rows?.[r];
        if (Array.isArray(payload)) m[r] = payload;
      }
      setRowsByRegion((prev) => ({ ...prev, ...m }));
    } catch (e: any) {
      setError(e?.message ?? String(e));
    }
  }, []);

  const refreshInfra = useCallback(async () => {
    try {
      const inf = await j<Infra>("/api/infra");
      setInfra(inf);
    } catch {
      // infra is best-effort; don't block data updates
    }
  }, []);

  useEffect(() => {
    refreshStatusAndRows();
    const t = setInterval(() => refreshStatusAndRows(), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    refreshInfra();
    const t = setInterval(() => refreshInfra(), 5000);
    return () => clearInterval(t);
  }, []);

  async function doWrite() {
    try {
      setError(null);
      const res = await j<{ region: string; row?: KvRow; active_region?: string }>("/api/write", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ key, value }),
      });
      if (res?.region && res?.row?.updated_at) setLastWrite({ region: res.region, updated_at: res.row.updated_at });

      // Show primary write immediately (no waiting for polling)
      if (res?.region && res?.row) {
        setRowsByRegion((prev) => {
          const cur = prev[res.region] ?? [];
          const next = [res.row, ...cur.filter((r) => r.k !== res.row!.k)].slice(0, 20);
          return { ...prev, [res.region]: next };
        });
      }

      // Then refresh from server to reconcile + catch replica
      await refreshStatusAndRows();
      setTimeout(() => refreshStatusAndRows(), 1200);
    } catch (e: any) {
      setError(e?.message ?? String(e));
    }
  }

  async function switchActive(region: string) {
    try {
      setError(null);
      await j(`/api/admin/switch?region=${region}`, { method: "POST" });
      await refreshStatusAndRows();
    } catch (e: any) {
      setError(e?.message ?? String(e));
    }
  }

  return (
    <div style={{ padding: 16, maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 800 }}>Failover-safe dashboard</div>
          <div style={{ fontSize: 13, color: "#666" }}>
            Polling every 1s. Watch Region A → Region B replication converge.
          </div>
          <div style={{ fontSize: 13, marginTop: 6 }}>
            <a href="/decision">Open Failover Decision Dashboard →</a>
          </div>
        </div>
        <div style={{ fontSize: 13 }}>
          <div>
            <span style={{ color: "#666" }}>Active region:</span>{" "}
            <b>{status?.active_region ?? "…"}</b>
          </div>
          <div>
            <span style={{ color: "#666" }}>Replica lag (region-b):</span>{" "}
            <b>{lag === undefined ? "…" : lag === null ? "n/a" : `${lag.toFixed(2)}s`}</b>
          </div>
        </div>
      </div>

      {error ? (
        <div style={{ marginTop: 12, padding: 10, border: "1px solid #f3c2c2", background: "#fff5f5", borderRadius: 8, color: "#8a1f1f" }}>
          {error}
        </div>
      ) : null}

      {lastWrite ? (
        <div style={{ marginTop: 12, padding: 10, border: "1px solid #d7f1e1", background: "#f3fff7", borderRadius: 8, color: "#146c2e", fontSize: 13 }}>
          Last write accepted by <b>{lastWrite.region}</b> at <b>{lastWrite.updated_at}</b>
        </div>
      ) : null}

      <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
        {regionNames.map((r) => (
          <button key={r} onClick={() => switchActive(r)} style={{ padding: "8px 10px" }}>
            Switch active → {r}
          </button>
        ))}
        <button onClick={() => refreshStatusAndRows()} style={{ padding: "8px 10px" }}>
          Refresh now
        </button>
      </div>

      <div style={{ marginTop: 10, border: "1px solid #eee", borderRadius: 8, padding: 10 }}>
        <div style={{ fontWeight: 800, marginBottom: 6 }}>Regions shown (UI toggle)</div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 13 }}>
          {regionNames.map((r) => (
            <label key={r} style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={visibleRegions[r] ?? true}
                onChange={(e) => setVisibleRegions((p) => ({ ...p, [r]: e.target.checked }))}
              />
              {r}
            </label>
          ))}
        </div>
        <div style={{ marginTop: 6, fontSize: 12, color: "#666" }}>
          Hiding regions reduces UI polling load (fewer per-region queries).
        </div>
      </div>

      <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>Write</div>
          <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: 8, alignItems: "center" }}>
            <div style={{ color: "#666" }}>key</div>
            <input value={key} onChange={(e) => setKey(e.target.value)} style={{ padding: 8 }} />
            <div style={{ color: "#666" }}>value</div>
            <input value={value} onChange={(e) => setValue(e.target.value)} style={{ padding: 8 }} />
          </div>
          <div style={{ marginTop: 10 }}>
            <button onClick={doWrite} style={{ padding: "8px 10px", fontWeight: 700 }}>
              POST /write (to active)
            </button>
          </div>
          <div style={{ marginTop: 8, fontSize: 12, color: "#666" }}>
            Tip: write a new value and watch it appear in Region B shortly after (depending on lag).
          </div>
        </div>

        <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>Health</div>
          {status ? (
            <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 12, color: "#222" }}>
{JSON.stringify(status, null, 2)}
            </pre>
          ) : (
            <div style={{ fontSize: 12, color: "#666" }}>Loading…</div>
          )}
        </div>
      </div>

      <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 12 }}>
        {shownRegions.map((r) => (
          <RegionPanel key={r} region={r} rows={rowsByRegion[r] ?? []} infra={infra?.regions?.[r]} />
        ))}
      </div>
    </div>
  );
}

