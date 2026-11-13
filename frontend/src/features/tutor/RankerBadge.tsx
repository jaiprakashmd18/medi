import { Badge } from "@/components/ui";

/**
 * Shows which ranker ordered the passages the tutor read.
 * - "Ranked by NVIDIA" when NVIDIA reranking was used.
 * - A warning when NVIDIA was enabled but failed and local ranking was used instead.
 * - Nothing when NVIDIA is simply off (no consent / local-only / not configured).
 */
export function RankerBadge({ ranker, note }: { ranker?: string | null; note?: string | null }) {
  if (ranker === "nvidia")
    return <Badge tone="ok" title="Passages were reordered by NVIDIA Nemotron 3.5 Rerank before answering.">Ranked by NVIDIA</Badge>;
  if (note && note.includes("Used local ranking"))
    return <Badge tone="warn" title={note}>NVIDIA unavailable · local ranking</Badge>;
  return null;
}
