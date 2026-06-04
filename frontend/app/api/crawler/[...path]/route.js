export const dynamic = "force-dynamic";

const DEFAULT_API_BASE = "http://127.0.0.1:8000";

export async function GET(request, context) {
  return proxyCrawlerApi(request, context);
}

export async function POST(request, context) {
  return proxyCrawlerApi(request, context);
}

async function proxyCrawlerApi(request, context) {
  const { path = [] } = await context.params;
  const upstream = upstreamUrl(request, path);
  const headers = new Headers();
  headers.set("Accept", request.headers.get("Accept") || "application/json");
  headers.set("X-Analyst-Id", process.env.ANALYST_ID || "next-ui");
  const contentType = request.headers.get("Content-Type");
  if (contentType) headers.set("Content-Type", contentType);
  const token = process.env.CRAWLER_API_TOKEN;
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const init = {
    method: request.method,
    headers,
    cache: "no-store"
  };
  if (!["GET", "HEAD"].includes(request.method)) {
    init.body = await request.text();
  }

  const response = await fetch(upstream, init);
  const body = await response.arrayBuffer();
  const responseHeaders = new Headers(response.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");
  return new Response(body, {
    status: response.status,
    headers: responseHeaders
  });
}

function upstreamUrl(request, path) {
  const base = (
    process.env.CRAWLER_API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    DEFAULT_API_BASE
  ).replace(/\/$/, "");
  const url = new URL(`${base}/${path.map(encodeURIComponent).join("/")}`);
  url.search = new URL(request.url).search;
  return url;
}
