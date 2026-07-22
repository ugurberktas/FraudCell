import { NextResponse } from "next/server";

export const revalidate = 0; // dynamic route

interface ServiceHealthResult {
  name: string;
  displayName: string;
  status: "healthy" | "unavailable";
  version: string | null;
  checkedAt: string;
}

const SERVICE_CONFIGS = [
  { name: "identity-service", displayName: "Identity Service", path: "/api/v1/auth/health" },
  { name: "transaction-service", displayName: "Transaction Service", path: "/api/v1/transactions/health" },
  { name: "ai-service", displayName: "AI Service", path: "/api/v1/ai/health" },
  { name: "gamification-service", displayName: "Gamification Service", path: "/api/v1/game/health" },
];

async function checkServiceHealth(
  baseUrl: string,
  config: (typeof SERVICE_CONFIGS)[number]
): Promise<ServiceHealthResult> {
  const checkedAt = new Date().toISOString();
  const url = `${baseUrl}${config.path}`;

  try {
    const res = await fetch(url, {
      method: "GET",
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });

    if (!res.ok) {
      return {
        name: config.name,
        displayName: config.displayName,
        status: "unavailable",
        version: null,
        checkedAt,
      };
    }

    const json = await res.json();
    // Envelope structure: { success: true, data: { status: "healthy", version: "0.1.0" }, error: null }
    const healthData = json?.data || json;

    if (healthData && healthData.status === "healthy") {
      return {
        name: config.name,
        displayName: config.displayName,
        status: "healthy",
        version: healthData.version || "0.1.0",
        checkedAt,
      };
    }

    return {
      name: config.name,
      displayName: config.displayName,
      status: "unavailable",
      version: null,
      checkedAt,
    };
  } catch {
    return {
      name: config.name,
      displayName: config.displayName,
      status: "unavailable",
      version: null,
      checkedAt,
    };
  }
}

export async function GET() {
  const baseUrl = process.env.INTERNAL_API_BASE_URL || "http://kong:8000";

  try {
    const results = await Promise.all(
      SERVICE_CONFIGS.map((config) => checkServiceHealth(baseUrl, config))
    );

    return NextResponse.json(
      {
        timestamp: new Date().toISOString(),
        services: results,
      },
      { status: 200 }
    );
  } catch {
    const fallbackResults: ServiceHealthResult[] = SERVICE_CONFIGS.map((c) => ({
      name: c.name,
      displayName: c.displayName,
      status: "unavailable",
      version: null,
      checkedAt: new Date().toISOString(),
    }));

    return NextResponse.json(
      {
        timestamp: new Date().toISOString(),
        services: fallbackResults,
      },
      { status: 200 }
    );
  }
}
