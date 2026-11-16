import type { MetadataRoute } from "next";

import { SITE } from "@/lib/legal";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      disallow: ["/dashboard", "/api/", "/invite/", "/room/"],
    },
    sitemap: new URL("/sitemap.xml", SITE.url).href,
  };
}
