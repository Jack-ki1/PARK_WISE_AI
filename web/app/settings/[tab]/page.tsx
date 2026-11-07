import { redirect } from "next/navigation";

export default async function SettingsTabPage({
  params,
}: {
  params: Promise<{ tab: string }>;
}) {
  const { tab } = await params;
  redirect(`/dashboard?page=settings&tab=${encodeURIComponent(tab)}`);
}
