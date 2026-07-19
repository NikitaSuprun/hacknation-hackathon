import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-paper px-gutter">
      <p className="mono-label mb-2">404</p>
      <h1 className="font-display text-h1">This page doesn't exist.</h1>
      <Link to="/" className="mt-6 text-small text-electric underline-offset-4 hover:underline">
        Back to start
      </Link>
    </div>
  );
}
