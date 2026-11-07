import { redirect } from "next/navigation";

export default function VideosPage() {
  redirect("/dashboard?page=live&mode=recorded");
}
