import type { MetadataRoute } from "next";

import { SITE } from "@/lib/legal";

export default function sitemap(): MetadataRoute.Sitemap {
  return ["/", "/tutors", "/groups", "/library", "/news"].map((path) => ({
    url: new URL(path, SITE.url).href,
  }));
}
