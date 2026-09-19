import { facets } from "@/lib/record";

export const dynamic = "force-dynamic";

export function GET() {
  return Response.json(facets());
}
