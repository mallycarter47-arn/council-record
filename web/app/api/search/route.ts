import { search } from "@/lib/record";

export async function GET(request: Request) {
  const p = new URL(request.url).searchParams;
  const q = p.get("q")?.trim();
  if (!q) return Response.json({ query: "", count: 0, results: [] });
  try {
    return Response.json(
      await search({
        q,
        body: p.get("body") || undefined,
        since: p.get("since") || undefined,
        until: p.get("until") || undefined,
        action: p.get("action") || undefined,
      }),
    );
  } catch (e) {
    return Response.json({ error: (e as Error).message }, { status: 400 });
  }
}
