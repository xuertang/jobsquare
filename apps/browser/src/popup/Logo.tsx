export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect width="32" height="32" rx="8" fill="#6366f1" />
      <rect x="8" y="8" width="16" height="3" rx="1.5" fill="white" opacity="0.95" />
      <rect x="8" y="14.5" width="16" height="3" rx="1.5" fill="white" opacity="0.7" />
      <rect x="8" y="21" width="10" height="3" rx="1.5" fill="white" opacity="0.5" />
      <path
        d="M22.5 19.5l1.4 1.4 2.6-2.8"
        stroke="white"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
