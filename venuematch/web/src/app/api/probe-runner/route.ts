import type { NextRequest } from "next/server";

const form = `<!doctype html><html><body><form method="post">
  <label for="secret">Probe secret</label>
  <input id="secret" name="secret" type="password" required autocomplete="off">
  <button type="submit">Run aggregate batch</button>
</form></body></html>`;

export async function GET() {
  return new Response(form, {
    headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
  });
}

export async function POST(request: NextRequest) {
  const body = await request.formData();
  const secret = String(body.get("secret") ?? "");
  const offset = Math.max(Number(request.nextUrl.searchParams.get("offset") ?? 0), 0);
  const batchSize = Math.min(
    Math.max(Number(request.nextUrl.searchParams.get("batch_size") ?? 4), 1),
    4,
  );
  const maxPages = Math.min(
    Math.max(Number(request.nextUrl.searchParams.get("max_pages") ?? 8), 1),
    8,
  );
  if (secret.length < 48 || !Number.isInteger(offset)) {
    return Response.json({ detail: "Invalid probe request" }, { status: 400 });
  }

  const backendUrl = (process.env.VENUE_MATCH_API_URL ?? "").replace(/\/$/, "");
  if (!backendUrl) {
    return Response.json({ detail: "Backend unavailable" }, { status: 503 });
  }
  const target = new URL(`${backendUrl}/evaluation/setlist-probe-batch`);
  target.searchParams.set("offset", String(offset));
  target.searchParams.set("batch_size", String(batchSize));
  target.searchParams.set("max_pages", String(maxPages));

  const upstream = await fetch(target, {
    headers: { accept: "application/json", authorization: `Bearer ${secret}` },
    cache: "no-store",
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });
}
