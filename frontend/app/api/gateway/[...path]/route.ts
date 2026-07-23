import { NextRequest, NextResponse } from "next/server";

const BASE_URL = process.env.INTERNAL_API_BASE_URL || "http://kong:8000";
const ALLOWED_PREFIXES = ["auth/", "transactions/", "game/"];

async function proxy(request: NextRequest, context: { params: { path: string[] } }) {
  const path = context.params.path.join("/");
  if (!ALLOWED_PREFIXES.some((prefix) => path.startsWith(prefix))) {
    return NextResponse.json({ success: false, data: null, error: { code: "FORBIDDEN", message: "Route is not allowed", details: {} } }, { status: 403 });
  }
  const target = new URL(`/api/v1/${path}`, BASE_URL);
  target.search = request.nextUrl.search;
  const headers: Record<string, string> = {
    "Content-Type": request.headers.get("content-type") || "application/json",
    "X-Request-ID": request.headers.get("x-request-id") || crypto.randomUUID(),
  };
  const authorization = request.headers.get("authorization");
  if (authorization) headers.Authorization = authorization;
  const response = await fetch(target, {
    method: request.method,
    headers,
    body: request.method === "GET" ? undefined : await request.text(),
    cache: "no-store",
  });
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { "Content-Type": "application/json", "X-Request-ID": response.headers.get("x-request-id") || headers["X-Request-ID"] },
  });
}

export const GET = proxy;
export const POST = proxy;
