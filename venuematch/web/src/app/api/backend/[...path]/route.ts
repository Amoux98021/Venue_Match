import type { NextRequest } from "next/server";

type RouteContext = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const backendUrl = (process.env.VENUE_MATCH_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
  const target = new URL(`${backendUrl}/${path.map(encodeURIComponent).join("/")}`);
  target.search = request.nextUrl.search;

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers: {
        accept: "application/json",
        "content-type": request.headers.get("content-type") ?? "application/json",
      },
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.text(),
      cache: "no-store",
    });

    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "application/json",
        "cache-control": "no-store",
      },
    });
  } catch {
    return Response.json(
      { detail: "The VenueMatch API is unavailable. Start FastAPI locally or configure VENUE_MATCH_API_URL." },
      { status: 503 },
    );
  }
}

export const GET = forward;
export const POST = forward;
