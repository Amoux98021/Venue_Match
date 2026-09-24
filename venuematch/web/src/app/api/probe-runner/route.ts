import type { NextRequest } from "next/server";

const form = `<!doctype html><html><body><form method="post">
  <label for="secret">Probe secret</label>
  <input id="secret" name="secret" type="password" required autocomplete="off">
  <button type="submit">Run aggregate batch</button>
</form></body></html>`;

export async function GET(request: NextRequest) {
  if (request.nextUrl.searchParams.get("collect") === "1") {
    const collector = `<!doctype html><html><body><p id="status">Collecting aggregates.</p>
      <script id="collection" type="application/json"></script>
      <script>
        const keys = Object.keys(sessionStorage).filter((key) => key.startsWith("vm-setlist-batch-"));
        const rows = keys.map((key) => JSON.parse(sessionStorage.getItem(key))).sort((a, b) => a.metadata.batch_offset - b.metadata.batch_offset);
        document.getElementById("collection").textContent = JSON.stringify(rows);
        document.getElementById("status").textContent = "Collected " + rows.length + " aggregate batches.";
      </script></body></html>`;
    return new Response(collector, {
      headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
    });
  }
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
  const payload = await upstream.text();
  const safePayload = payload.replaceAll("<", "\\u003c");
  const document = `<!doctype html><html><body><p id="status">Aggregate ready.</p>
    <script id="aggregate" type="application/json">${safePayload}</script>
    <script>
      const payload = document.getElementById("aggregate").textContent;
      sessionStorage.setItem("vm-setlist-batch-${offset}", payload);
      const keys = Object.keys(sessionStorage).filter((key) => key.startsWith("vm-setlist-batch-"));
      const rows = keys.map((key) => JSON.parse(sessionStorage.getItem(key)));
      const requests = rows.reduce((total, row) => total + row.request_metrics.requests, 0);
      const artists = rows.reduce((total, row) => total + row.summary.artists_queried, 0);
      document.getElementById("status").textContent = "Aggregate stored in session. Batches: " + rows.length + ". Artists: " + artists + ". Successful requests: " + requests + ".";
    </script></body></html>`;
  return new Response(document, {
    status: upstream.status,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}
