import { NextRequest } from "next/server";

const UPSTREAM = process.env.INFRA_INTERNAL_BASE ?? "http://infra:7070";

export async function GET(req: NextRequest) {
  const url = new URL("/infra", UPSTREAM);
  req.nextUrl.searchParams.forEach((v, k) => url.searchParams.set(k, v));

  const upstream = await fetch(url.toString(), { cache: "no-store" });
  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json", "cache-control": "no-store" },
  });
}

