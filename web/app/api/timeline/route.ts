import { timeline } from "@/lib/record";

export async function GET(request: Request) {
  const q = new URL(request.url).searchParams.get("q")?.trim();
  if (!q) return Response.json([]);
  try {
    return Response.json(await timeline(q));
  } catch (e) {
    return Response.json({ error: (e as Error).message }, { status: 400 });
  }
}
