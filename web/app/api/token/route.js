import { getServerSession } from "next-auth";
import jwt from "jsonwebtoken";
import { authOptions } from "../../../lib/auth";

// Mint a short-lived HS256 JWT the FastAPI backend verifies (shared secret).
// The browser fetches this, then calls the backend with `Authorization: Bearer`.
export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session) {
    return new Response(JSON.stringify({ error: "unauthenticated" }), {
      status: 401,
      headers: { "content-type": "application/json" },
    });
  }
  const token = jwt.sign(
    { sub: session.userId, email: session.user?.email },
    process.env.BACKEND_JWT_SECRET,
    { algorithm: "HS256", expiresIn: "1h" }
  );
  return Response.json({ token });
}
