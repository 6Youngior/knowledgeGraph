export function LogoMark({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" aria-hidden="true" className="logo-mark">
      <rect width="40" height="40" rx="8" fill="#234f78" />
      <path d="M12 30V11H29M12 21H25" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="12" cy="30" r="2.4" fill="white" /><circle cx="12" cy="11" r="2.4" fill="white" />
      <circle cx="29" cy="11" r="2.4" fill="white" /><circle cx="25" cy="21" r="2.4" fill="white" />
    </svg>
  );
}
