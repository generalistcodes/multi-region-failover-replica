import { NextRequest } from "next/server";

const UPSTREAM = process.env.ROUTER_INTERNAL_BASE ?? "http://router:8090";

export async function proxyJson(req: NextRequest, path: string) {
  const url = new URL(path, UPSTREAM);
  // preserve query string
  req.nextUrl.searchParams.forEach((v, k) => url.searchParams.set(k, v));

  const method = req.method;
  const body =
    method === "POST" || method === "PUT" || method === "PATCH" ? await req.text() : undefined;

  const upstream = await fetch(url.toString(), {
    method,
    headers: {
      "content-type": req.headers.get("content-type") ?? "application/json",
    },
    body,
    cache: "no-store",
  });

  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });
}

