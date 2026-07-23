"use client";

import { useEffect, useState, useCallback } from "react";

interface ServiceStatus {
  name: string;
  displayName: string;
  status: "healthy" | "unavailable";
  version: string | null;
  checkedAt: string;
}

interface PlatformHealthResponse {
  timestamp: string;
  services: ServiceStatus[];
}

export default function Home() {
  const [data, setData] = useState<PlatformHealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [generalError, setGeneralError] = useState<string | null>(null);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    setGeneralError(null);
    try {
      const res = await fetch("/api/platform-health", {
        cache: "no-store",
      });
      if (!res.ok) {
        throw new Error(`HTTP Error: ${res.status}`);
      }
      const json: PlatformHealthResponse = await res.json();
      setData(json);
    } catch (err: unknown) {
      setGeneralError(
        err instanceof Error ? err.message : "Genel bağlantı hatası oluştu"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  const hasUnavailableService =
    data?.services.some((s) => s.status === "unavailable") ?? false;

  return (
    <main className="container">
      <header className="header">
        <h1 className="title">FraudCell Platform Status</h1>
        <button
          onClick={fetchHealth}
          disabled={loading}
          className="refresh-btn"
          type="button"
        >
          {loading && (
            <div
              className="spinner"
              style={{ width: 14, height: 14, borderWidth: 2 }}
            />
          )}
          Yenile
        </button>
      </header>

      {generalError && (
        <div className="banner banner-error">
          ⚠️ <strong>Bağlantı Hatası:</strong> Health API ile iletişim kurulanamadı ({generalError}).
        </div>
      )}

      {!generalError && hasUnavailableService && (
        <div className="banner banner-warning">
          ⚡ <strong>Servis Kesintisi:</strong> Bir veya daha fazla mikroservis erişilemez durumda.
        </div>
      )}

      {loading && !data && (
        <div className="loading-container">
          <div className="spinner" /> Servis durumları kontrol ediliyor...
        </div>
      )}

      {data && (
        <div className="grid">
          {data.services.map((svc) => (
            <div key={svc.name} className="card">
              <div className="card-header">
                <div>
                  <h2 className="service-name">{svc.displayName}</h2>
                  <p className="service-id">{svc.name}</p>
                </div>
                <span
                  className={`badge ${
                    svc.status === "healthy" ? "badge-healthy" : "badge-unavailable"
                  }`}
                >
                  {svc.status === "healthy" ? "Healthy" : "Unavailable"}
                </span>
              </div>

              <div className="card-details">
                <div className="detail-row">
                  <span className="detail-label">Versiyon:</span>
                  <span className="detail-value">{svc.version || "—"}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Son Kontrol:</span>
                  <span className="detail-value">
                    {svc.checkedAt
                      ? new Date(svc.checkedAt).toLocaleTimeString("tr-TR")
                      : "—"}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
