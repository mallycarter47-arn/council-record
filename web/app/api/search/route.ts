import { search } from "@/lib/record";
import { logSearch } from "@/lib/stats";

export async function GET(request: Request) {
  const p = new URL(request.url).searchParams;
  const q = p.get("q")?.trim();
  if (!q) return Response.json({ query: "", count: 0, results: [] });
  const filters = {
    body: p.get("body") || undefined,
    since: p.get("since") || undefined,
    until: p.get("until") || undefined,
    action: p.get("action") || undefined,
  };
  try {
    const result = await search({ q, ...filters });
    logSearch(q, filters, result.count);
    return Response.json(result);
  } catch (e) {
    // The real reason goes to the logs; people get one plain sentence.
    console.error("[search]", (e as Error).message);
    return Response.json({ error: "Couldn't run that search" }, { status: 400 });
  }
}
