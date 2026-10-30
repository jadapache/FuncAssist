import { Layers } from 'lucide-react'

interface IntegrationLogoProps {
  id: string
  className?: string
}

export const IntegrationLogo = ({ id, className = 'h-6 w-6' }: IntegrationLogoProps) => {
  switch (id.toLowerCase()) {
    case 'jira':
      return (
        <svg viewBox="0 0 24 24" className={className} fill="none">
          <path
            d="M11.53 2c0 5.26 4.27 9.53 9.53 9.53v-9.53h-9.53z"
            fill="#0052CC"
          />
          <path
            d="M2 11.53c0 5.26 4.26 9.53 9.53 9.53v-9.53H2z"
            fill="#2684FF"
          />
          <path
            d="M11.53 11.53c0 5.26 4.27 9.53 9.53 9.53v-9.53h-9.53z"
            fill="#0052CC"
          />
        </svg>
      )

    case 'github':
      return (
        <svg viewBox="0 0 24 24" className={className} fill="currentColor">
          <path
            fillRule="evenodd"
            clipRule="evenodd"
            d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
          />
        </svg>
      )

    case 'gitlab':
      return (
        <svg viewBox="0 0 24 24" className={className} fill="none">
          <path
            d="M22.65 14.39L20.61 8.1a.75.75 0 00-1.43 0l-1.63 5.01H6.45L4.82 8.1a.75.75 0 00-1.43 0L1.35 14.39a1.5 1.5 0 00.54 1.68l9.64 7.01a.75.75 0 00.88 0l9.64-7.01a1.5 1.5 0 00.6-1.68z"
            fill="#E24329"
          />
          <path
            d="M12 23.08l-4.45-13.7h8.9L12 23.08z"
            fill="#FC6D26"
          />
        </svg>
      )

    case 'slack':
      return (
        <svg viewBox="0 0 24 24" className={className} fill="none">
          <path
            d="M5.04 14.43a2.04 2.04 0 11-2.04-2.04h2.04v2.04zm1.02 0a2.04 2.04 0 014.08 0v5.1a2.04 2.04 0 11-4.08 0v-5.1z"
            fill="#E01E5A"
          />
          <path
            d="M9.57 5.04a2.04 2.04 0 11-2.04-2.04v2.04h2.04zm0 1.02a2.04 2.04 0 010 4.08h-5.1a2.04 2.04 0 110-4.08h5.1z"
            fill="#36C5F0"
          />
          <path
            d="M18.96 9.57a2.04 2.04 0 112.04 2.04h-2.04V9.57zm-1.02 0a2.04 2.04 0 01-4.08 0v-5.1a2.04 2.04 0 114.08 0v5.1z"
            fill="#2EB67D"
          />
          <path
            d="M14.43 18.96a2.04 2.04 0 112.04 2.04v-2.04h-2.04zm0-1.02a2.04 2.04 0 010-4.08h5.1a2.04 2.04 0 110 4.08h-5.1z"
            fill="#ECB22E"
          />
        </svg>
      )

    case 'trello':
      return (
        <svg viewBox="0 0 24 24" className={className} fill="none">
          <rect width="24" height="24" rx="4.5" fill="#0079BF" />
          <rect x="4.5" y="4.5" width="6" height="12" rx="1.5" fill="#FFFFFF" />
          <rect x="13.5" y="4.5" width="6" height="8" rx="1.5" fill="#FFFFFF" />
        </svg>
      )

    case 'notion':
      return (
        <svg viewBox="0 0 24 24" className={className} fill="none">
          <rect width="24" height="24" rx="4" fill="#000000" />
          <path
            d="M6 7.5l3.5-.75L18 8.25v9.5l-4 1.5L6 17.5V7.5zm2.5 1.5v6.5l2 .5V9.5l-2-.5zm5 .5v6.5l2 .5V10l-2-.5z"
            fill="#FFFFFF"
          />
        </svg>
      )

    case 'monday':
      return (
        <svg viewBox="0 0 24 24" className={className} fill="none">
          <circle cx="6" cy="12" r="3.5" fill="#FF3D57" />
          <circle cx="12" cy="12" r="3.5" fill="#FFCB00" />
          <circle cx="18" cy="12" r="3.5" fill="#00CA72" />
        </svg>
      )

    case 'asana':
      return (
        <svg viewBox="0 0 24 24" className={className} fill="none">
          <circle cx="12" cy="7" r="3.5" fill="#F06A6A" />
          <circle cx="6.5" cy="16.5" r="3.5" fill="#F06A6A" />
          <circle cx="17.5" cy="16.5" r="3.5" fill="#F06A6A" />
        </svg>
      )

    case 'clickup':
      return (
        <svg viewBox="0 0 24 24" className={className} fill="none">
          <path
            d="M4 15.5l8-6 8 6"
            stroke="#7B68EE"
            strokeWidth="3.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle cx="12" cy="18" r="2.5" fill="#FF007A" />
        </svg>
      )

    case 'confluence':
      return (
        <svg viewBox="0 0 24 24" className={className} fill="none">
          <path
            d="M3 17.5c2.5-4 7-4.5 10.5-2.5l2.5-4.5C11.5 7.5 5.5 8 3 12.5v5z"
            fill="#0052CC"
          />
          <path
            d="M21 6.5c-2.5 4-7 4.5-10.5 2.5L8 13.5c4.5 3 10.5 2.5 13-2v-5z"
            fill="#2684FF"
          />
        </svg>
      )

    case 'linear':
      return (
        <svg viewBox="0 0 24 24" className={className} fill="none">
          <rect width="24" height="24" rx="5" fill="#5E6AD2" />
          <path
            d="M6 18L18 6M6 12L12 6M12 18L18 12"
            stroke="#FFFFFF"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
        </svg>
      )

    default:
      return <Layers className={`${className} text-[#002777]`} />
  }
}
