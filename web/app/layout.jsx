import "./globals.css";
import Providers from "./providers";

export const metadata = {
  title: "Advocate Profiles — eCourts",
  description: "Search any advocate and see their full case portfolio from public court records.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
