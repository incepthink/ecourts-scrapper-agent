import "./globals.css";
import { Inter, Fraunces } from "next/font/google";
import Providers from "./providers";

// UI / body — clean, neutral sans.
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

// Display / headings — editorial serif that gives the product its "legal premium" voice.
const fraunces = Fraunces({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-serif",
  style: ["normal", "italic"],
});

export const metadata = {
  title: "Advocate Profiles — eCourts",
  description: "Search any advocate and see their full case portfolio from public court records.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${inter.variable} ${fraunces.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
