import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { dataSource } from "@/lib/data";

/**
 * TODO(Track C): the founder flow — "You've been chosen." hero with the paint
 * swirl, consent screen, "Complete your candidacy" (LinkedIn/GitHub/CV/pitch),
 * streaming AI chat, done state. Never the word "apply".
 */
export default function InterviewPage() {
  const { token = "" } = useParams();
  const ds = dataSource();
  const { data: session } = useQuery({
    queryKey: ["interview", token],
    queryFn: () => ds.getInterviewSession(token),
  });

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-paper px-gutter">
      <div className="w-full max-w-[560px]">
        <p className="mono-label mb-4">A message from {session?.fund_name ?? "the fund"}</p>
        <h1 className="font-display text-h1">You've been chosen.</h1>
        <p className="mt-4 text-body text-quiet">{session?.why_contacted}</p>
      </div>
    </div>
  );
}
