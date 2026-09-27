function Icon({ children, ...props }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...props}>
      {children}
    </svg>
  )
}

export function WifiIcon() {
  return (
    <Icon fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 18.5a1.35 1.35 0 1 1 0-2.7 1.35 1.35 0 0 1 0 2.7Z" fill="#ffffff" />
      <path d="M8.2 13.9a5.3 5.3 0 0 1 7.6 0" stroke="#ffffff" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M5.1 10.7a9.7 9.7 0 0 1 13.8 0" stroke="#ffffff" strokeWidth="1.8" strokeLinecap="round" />
    </Icon>
  )
}

export function VoucherIcon() {
  return (
    <Icon>
      <path d="M4 7.5A2.5 2.5 0 0 1 6.5 5h11A2.5 2.5 0 0 1 20 7.5V9a3 3 0 0 0 0 6v1.5a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 16.5V15a3 3 0 0 0 0-6V7.5Z" />
      <path d="M12 8v8" />
    </Icon>
  )
}

export function RefreshIcon() {
  return <Icon><path d="M20 11A8 8 0 1 0 18.3 16" /><path d="M20 5v6h-6" /></Icon>
}

export function DataUsedIcon() {
  return <Icon><path d="M12 3v12m0 0-4-4m4 4 4-4" /><path d="M5 19h14" /></Icon>
}

export function DataLeftIcon() {
  return <Icon><rect x="2" y="7" width="18" height="10" rx="2" /><path d="M22 10v4" /></Icon>
}

export function PlanIcon() {
  return <Icon><path d="m12 3 2.6 5.9L21 9.6l-4.6 4.2L17.6 21 12 17.6 6.4 21l1.2-7.2L3 9.6l6.4-.7Z" /></Icon>
}

export function DevicesIcon() {
  return <Icon><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></Icon>
}

export function AccountIcon() {
  return <Icon><path d="M20 21a8 8 0 0 0-16 0M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z" /></Icon>
}

export function PhoneIcon() {
  return <Icon><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.68 2.8a2 2 0 0 1-.45 2.11L8.07 9.9a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.9.32 1.84.55 2.8.68A2 2 0 0 1 22 16.92Z" /></Icon>
}

export function ChatIcon() {
  return <Icon><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v8Z" /><path d="M8 10h.01M12 10h.01M16 10h.01" /></Icon>
}

export function GlobeIcon() {
  return <Icon><path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z" /><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" /></Icon>
}

export function LockIcon() {
  return <Icon><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></Icon>
}

export function ShieldIcon() {
  return <Icon><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></Icon>
}

export function CloseIcon() {
  return <Icon><path d="m6 6 12 12M18 6 6 18" /></Icon>
}

export function WarningIcon() {
  return <Icon><path d="M12 9v4" /><path d="M12 17h.01" /><path d="M10.29 3.86 1.82 18a1.5 1.5 0 0 0 1.3 2.25h17.76a1.5 1.5 0 0 0 1.3-2.25L13.71 3.86a1.5 1.5 0 0 0-2.42 0Z" /></Icon>
}

export function CheckIcon() {
  return <Icon><path d="m5 13 4 4L19 7" /></Icon>
}

export function DotIcon() {
  return <Icon style={{ fill: 'currentColor', stroke: 'none' }}><circle cx="12" cy="12" r="6" /></Icon>
}

export function DeviceTypeIcon({ type }) {
  switch (String(type || '').trim().toLowerCase()) {
    case 'phone':
      return <Icon><rect x="7" y="2" width="10" height="20" rx="2" /><path d="M11 18h2" /></Icon>
    case 'pc':
      return <DevicesIcon />
    case 'chromebook':
      return <Icon><rect x="4" y="4" width="16" height="12" rx="1.5" /><path d="M2 19h20" /></Icon>
    case 'tablet':
      return <Icon><rect x="4" y="2" width="16" height="20" rx="2" /><path d="M11 18h2" /></Icon>
    case 'linux device':
      return <Icon><rect x="3" y="4" width="18" height="16" rx="2" /><path d="m7 9 3 3-3 3M13 15h4" /></Icon>
    default:
      return <Icon><circle cx="12" cy="12" r="9" /><path d="M9.8 9a2.4 2.4 0 1 1 3.4 2.2c-.8.4-1.2.9-1.2 1.8M12 17h.01" /></Icon>
  }
}
