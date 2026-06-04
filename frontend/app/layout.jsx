import "./globals.css";
import "maplibre-gl/dist/maplibre-gl.css";

export const metadata = {
  title: "Azerbaijan Energy Intelligence",
  description: "Analyst UI POC for crawler-backed Azerbaijan energy intelligence."
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
