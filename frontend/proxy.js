import { NextResponse } from "next/server";

export function proxy(request) {
  const expectedUser = process.env.ANALYST_UI_USERNAME;
  const expectedPassword = process.env.ANALYST_UI_PASSWORD;
  if (!expectedUser && !expectedPassword) return NextResponse.next();

  const header = request.headers.get("authorization") || "";
  const [scheme, encoded] = header.split(" ");
  if (scheme !== "Basic" || !encoded) return unauthorized();

  let decoded = "";
  try {
    decoded = atob(encoded);
  } catch {
    return unauthorized();
  }
  const separator = decoded.indexOf(":");
  const user = separator >= 0 ? decoded.slice(0, separator) : decoded;
  const password = separator >= 0 ? decoded.slice(separator + 1) : "";
  if (user === expectedUser && password === expectedPassword) {
    return NextResponse.next();
  }
  return unauthorized();
}

function unauthorized() {
  return new NextResponse("Authentication required", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="Azerbaijan Energy Intelligence"'
    }
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"]
};
