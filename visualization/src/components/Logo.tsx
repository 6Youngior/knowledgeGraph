export function LogoMark({ size = 36 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      aria-hidden="true"
      className="logo-mark"
    >
      <defs>
        <linearGradient id="fg-logo-gradient" x1="4" y1="4" x2="36" y2="36">
          <stop stopColor="#67e8f9" />
          <stop offset="0.55" stopColor="#38bdf8" />
          <stop offset="1" stopColor="#6366f1" />
        </linearGradient>
      </defs>
      <rect
        x="1"
        y="1"
        width="38"
        height="38"
        rx="11"
        fill="#0b1424"
        stroke="url(#fg-logo-gradient)"
        strokeWidth="1.4"
      />
      <path
        d="M12.5 27.5 20 10.5l7.5 17"
        stroke="url(#fg-logo-gradient)"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M15.5 22.5h9"
        stroke="url(#fg-logo-gradient)"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      <circle cx="20" cy="10.5" r="2.2" fill="#e0f7ff" />
      <circle cx="12.5" cy="27.5" r="2.2" fill="#67e8f9" />
      <circle cx="27.5" cy="27.5" r="2.2" fill="#818cf8" />
    </svg>
  );
}
