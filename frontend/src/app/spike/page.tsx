import { notFound } from "next/navigation";
import SpikePageClient from "./SpikePageClient";

/**
 * RIS-31 / ADR-010: the standalone RIS-15 Cytoscape.js spike page is a
 * superseded dev/demo surface (the root page and `/graph` cover the same
 * ground with real data and full provenance). It stays reachable for local
 * development but is absent from a default production build; set
 * `ENABLE_SPIKE_PAGE=true` to opt back in.
 */
export default function SpikePage() {
  if (process.env.ENABLE_SPIKE_PAGE !== "true") {
    notFound();
  }
  return <SpikePageClient />;
}
