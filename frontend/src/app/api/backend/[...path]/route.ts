import { NextRequest, NextResponse } from "next/server";

/**
 * Server-side proxy to the RiskWeave backend (RIS-31 / ADR-010).
 *
 * The backend gates mutating and Gemini-calling endpoints behind a shared
 * bearer key once `RISKWEAVE_API_KEY` is configured in production. That key
 * must never reach the browser (`RW-SEC-001`), so client components call
 * this same-origin route instead of the backend directly; this handler
 * attaches the key server-side and forwards the request unchanged.
 */

const BACKEND_URL = (
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000"
).replace(/\/$/, "");
const API_KEY = process.env.RISKWEAVE_API_KEY;

const HOP_BY_HOP_HEADERS = new Set([
  "host",
  "connection",
  "content-length",
  "transfer-encoding",
]);

async function proxy(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await params;
  const target = new URL(`${BACKEND_URL}/${path.join("/")}`);
  target.search = req.nextUrl.search;

  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) headers.set(key, value);
  });
  if (API_KEY) headers.set("authorization", `Bearer ${API_KEY}`);

  const hasBody = req.method !== "GET" && req.method !== "HEAD";

  const upstream = await fetch(target, {
    method: req.method,
    headers,
    body: hasBody ? await req.arrayBuffer() : undefined,
  });

  const responseHeaders = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType) responseHeaders.set("content-type", contentType);

  return new NextResponse(await upstream.arrayBuffer(), {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const PATCH = proxy;
