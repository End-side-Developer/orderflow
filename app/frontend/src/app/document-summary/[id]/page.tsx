import { redirect } from "next/navigation";

export default async function LegacyDocumentSummaryPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/case/${encodeURIComponent(id)}`);
}

