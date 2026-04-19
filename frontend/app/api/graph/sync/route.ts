import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL;

export async function GET(req: NextRequest) {
  // IAPが注入するユーザー識別ヘッダ・state Cookieをバックエンドに中継
  const forwardHeaders: Record<string, string> = {};
  const email = req.headers.get("x-goog-authenticated-user-email");
  if (email) forwardHeaders["x-goog-authenticated-user-email"] = email;
  const cookie = req.headers.get("cookie");
  if (cookie) forwardHeaders["cookie"] = cookie;

  const res = await fetch(`${BACKEND_URL}/api/graph/sync`, {
    method: "GET",
    headers: forwardHeaders,
    redirect: "manual",
  });

  const body = await res.text();
  const response = new NextResponse(body, {
    status: res.status,
    headers: {
      "content-type": res.headers.get("content-type") ?? "application/json",
    },
  });
  // バックエンドが立てたSet-Cookie（state）をブラウザに透過
  const setCookie = res.headers.get("set-cookie");
  if (setCookie) response.headers.set("set-cookie", setCookie);
  return response;
}
