import GoogleProvider from "next-auth/providers/google";

// NextAuth config shared by the auth route and the token-minting route.
export const authOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    }),
  ],
  session: { strategy: "jwt" },
  callbacks: {
    async session({ session, token }) {
      // Expose the stable user id so /api/token can put it in the backend JWT.
      session.userId = token.sub;
      return session;
    },
  },
};
