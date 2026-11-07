import { redirect } from "next/navigation";

export default function LivePage() {
  redirect("/dashboard?page=live");
}
