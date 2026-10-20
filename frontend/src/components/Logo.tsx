// The SME Finance Copilot logo (frontend/public/logo.png, 720 × 190, transparent background).
// The image already contains the name, so the alt text carries it for screen readers.
export default function Logo({ className = "" }: { className?: string }) {
  return <img src="/logo.png" alt="SME Finance Copilot" width={720} height={190} className={`h-auto ${className}`} />;
}
