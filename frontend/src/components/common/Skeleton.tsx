import React from 'react'

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string
}

/** Base Skeleton element with modern shimmer animation */
export const Skeleton: React.FC<SkeletonProps> = ({ className = '', ...props }) => {
  return (
    <div
      className={`animate-shimmer rounded-lg bg-gradient-to-r from-slate-200 via-slate-100 to-slate-200 ${className}`}
      style={{
        backgroundSize: '200% 100%',
        animation: 'shimmer 1.8s infinite linear',
      }}
      aria-hidden="true"
      {...props}
    />
  )
}

/** Skeleton for the Integrations tab (Jira, GitHub, GitLab) */
export const IntegrationsSkeleton: React.FC = () => {
  return (
    <div className="space-y-6">
      {/* OAuth Setup card skeleton */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <Skeleton className="h-5 w-44" />
            <Skeleton className="h-3.5 w-80" />
          </div>
          <Skeleton className="h-8 w-24 rounded-lg" />
        </div>
        <div className="grid gap-3 sm:grid-cols-2 pt-2">
          <Skeleton className="h-10 w-full rounded-lg" />
          <Skeleton className="h-10 w-full rounded-lg" />
        </div>
      </div>

      {/* Integration cards skeletons (3 cards: Jira, GitHub, GitLab) */}
      {[1, 2, 3].map((idx) => (
        <div key={idx} className="card p-6 space-y-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <Skeleton className="h-8 w-8 rounded-lg" />
                <Skeleton className="h-6 w-36" />
              </div>
              <Skeleton className="h-4 w-72" />
            </div>
            <Skeleton className="h-6 w-24 rounded-full" />
          </div>

          <div className="space-y-2 pt-2 border-t border-slate-100">
            <Skeleton className="h-3.5 w-56" />
            <Skeleton className="h-3.5 w-48" />
          </div>

          <div className="flex gap-3 pt-2">
            <Skeleton className="h-9 w-32 rounded-lg" />
            <Skeleton className="h-9 w-28 rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  )
}

/** Skeleton for AI Models tab */
export const AiModelsSkeleton: React.FC = () => {
  return (
    <div className="space-y-6">
      {/* Summary card skeleton */}
      <div className="card p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <Skeleton className="h-6 w-52" />
            <Skeleton className="h-3.5 w-96" />
          </div>
          <Skeleton className="h-9 w-36 rounded-xl" />
        </div>

        {/* Provider selector grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2.5 pt-2">
          {[1, 2, 3, 4, 5, 6].map((p) => (
            <Skeleton key={p} className="h-16 w-full rounded-xl" />
          ))}
        </div>
      </div>

      {/* Collapsible Model Card Skeleton */}
      <div className="card p-6 space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Skeleton className="h-9 w-9 rounded-xl" />
            <div className="space-y-1.5">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-3.5 w-72" />
            </div>
          </div>
          <Skeleton className="h-6 w-6 rounded-md" />
        </div>

        <div className="space-y-4 pt-2">
          <Skeleton className="h-10 w-full rounded-lg" />
          <div className="grid gap-3 sm:grid-cols-2">
            <Skeleton className="h-24 w-full rounded-xl" />
            <Skeleton className="h-24 w-full rounded-xl" />
          </div>
        </div>
      </div>
    </div>
  )
}

/** Skeleton for User Approvals tab */
export const UserApprovalsSkeleton: React.FC = () => {
  return (
    <div className="card p-6 md:p-8 space-y-6">
      <div className="flex items-center justify-between border-b border-slate-100 pb-4">
        <div className="flex items-center gap-3">
          <Skeleton className="h-7 w-7 rounded-lg" />
          <div className="space-y-1.5">
            <Skeleton className="h-5 w-60" />
            <Skeleton className="h-3.5 w-80" />
          </div>
        </div>
        <Skeleton className="h-8 w-24 rounded-lg" />
      </div>

      <div className="space-y-3">
        {[1, 2, 3].map((u) => (
          <div
            key={u}
            className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-xl border border-slate-100 bg-white p-4 shadow-sm"
          >
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-4 w-20 rounded-full" />
              </div>
              <Skeleton className="h-3 w-48" />
              <Skeleton className="h-2.5 w-32" />
            </div>
            <div className="flex items-center gap-2">
              <Skeleton className="h-8 w-28 rounded-lg" />
              <Skeleton className="h-8 w-24 rounded-lg" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Skeleton for Dashboard Overview widgets */
export const DashboardSkeleton: React.FC = () => {
  return (
    <div className="space-y-8">
      {/* Stat cards skeleton */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="card p-5 space-y-3">
            <div className="flex items-center justify-between">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-8 w-8 rounded-lg" />
            </div>
            <Skeleton className="h-7 w-20" />
            <Skeleton className="h-3.5 w-36" />
          </div>
        ))}
      </div>

      {/* Main content grid */}
      <div className="grid gap-6 xl:grid-cols-5">
        <div className="space-y-4 xl:col-span-2">
          <Skeleton className="h-6 w-40" />
          <div className="space-y-3">
            {[1, 2, 3].map((t) => (
              <Skeleton key={t} className="h-24 w-full rounded-2xl" />
            ))}
          </div>
        </div>
        <div className="space-y-4 xl:col-span-3">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-64 w-full rounded-2xl" />
        </div>
      </div>
    </div>
  )
}

/** Skeleton for Chat view */
export const ChatSkeleton: React.FC = () => {
  return (
    <div className="flex flex-col h-full w-full p-4 md:p-6 space-y-6">
      <div className="flex items-center justify-between border-b border-slate-100 pb-4">
        <div className="space-y-2">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-3.5 w-72" />
        </div>
        <Skeleton className="h-9 w-28 rounded-xl" />
      </div>

      <div className="flex-1 space-y-4 py-4">
        <div className="flex items-start gap-3 max-w-xl">
          <Skeleton className="h-8 w-8 rounded-full shrink-0" />
          <Skeleton className="h-16 w-full rounded-2xl" />
        </div>
        <div className="flex items-start justify-end gap-3 max-w-xl ml-auto">
          <Skeleton className="h-14 w-full rounded-2xl" />
          <Skeleton className="h-8 w-8 rounded-full shrink-0" />
        </div>
        <div className="flex items-start gap-3 max-w-2xl">
          <Skeleton className="h-8 w-8 rounded-full shrink-0" />
          <Skeleton className="h-28 w-full rounded-2xl" />
        </div>
      </div>

      <div className="pt-2">
        <Skeleton className="h-14 w-full rounded-2xl" />
      </div>
    </div>
  )
}

/** Skeleton for Knowledge Page document catalog */
export const KnowledgeDocsSkeleton: React.FC = () => {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {[1, 2, 3, 4, 5, 6].map((i) => (
        <div key={i} className="card p-5 space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <Skeleton className="h-10 w-10 rounded-xl" />
              <div className="space-y-1.5">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-20" />
              </div>
            </div>
            <Skeleton className="h-6 w-16 rounded-full" />
          </div>
          <Skeleton className="h-3 w-full" />
          <div className="flex items-center justify-between pt-2 border-t border-slate-100">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-7 w-16 rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  )
}

/** Skeleton for Transcripciones list */
export const TranscriptionsSkeleton: React.FC = () => {
  return (
    <div className="space-y-3">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="card p-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3.5 min-w-0 flex-1">
            <Skeleton className="h-10 w-10 rounded-xl shrink-0" />
            <div className="space-y-1.5 min-w-0 flex-1">
              <Skeleton className="h-4 w-44" />
              <Skeleton className="h-3 w-64" />
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Skeleton className="h-8 w-24 rounded-lg" />
            <Skeleton className="h-8 w-8 rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  )
}
