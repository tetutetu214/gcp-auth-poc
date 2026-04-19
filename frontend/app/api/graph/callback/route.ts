import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL;

export async function GET(req: NextRequest) {
  const { search } = new URL(req.url);

  const forwardHeaders: Record<string, string> = {};
  const email = req.headers.get("x-goog-authenticated-user-email");
  if (email) forwardHeaders["x-goog-authenticated-user-email"] = email;
  const jwt = req.headers.get("x-goog-iap-jwt-assertion");
  if (jwt) forwardHeaders["x-goog-iap-jwt-assertion"] = jwt;
  const cookie = req.headers.get("cookie");
  if (cookie) forwardHeaders["cookie"] = cookie;

  const res = await fetch(`${BACKEND_URL}/api/graph/callback${search}`, {
    method: "GET",
    headers: forwardHeaders,
    redirect: "manual",
  });

  // FastAPIからのレスポンス（リダイレクトかJSON）をそのまま返す
  const body = await res.text();
  const response = new NextResponse(body, {
    status: res.status,
    headers: {
      "content-type": res.headers.get("content-type") ?? "application/json",
    },
  });
  // 302のLocationヘッダ・Cookie削除ヘッダを透過
  const location = res.headers.get("location");
  if (location) response.headers.set("location", location);
  const setCookie = res.headers.get("set-cookie");
  if (setCookie) response.headers.set("set-cookie", setCookie);
  return response;
}
