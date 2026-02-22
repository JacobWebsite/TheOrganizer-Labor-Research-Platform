import { Skeleton } from '@/components/ui/skeleton'

const variants = {
  search: (
    <div className="space-y-4">
      <Skeleton className="h-10 w-full max-w-lg" />
      <div className="space-y-3">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    </div>
  ),
  profile: (
    <div className="space-y-6">
      <Skeleton className="h-8 w-64" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {Array.from({ length: 3 }, (_, i) => (
          <Skeleton key={i} className="h-32 w-full" />
        ))}
      </div>
      <Skeleton className="h-64 w-full" />
    </div>
  ),
  targets: (
    <div className="space-y-4">
      <Skeleton className="h-10 w-full max-w-sm" />
      <div className="space-y-3">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    </div>
  ),
  default: (
    <div className="space-y-4">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-64 w-full" />
    </div>
  ),
}

export function PageSkeleton({ variant = 'default' }) {
  return variants[variant] || variants.default
}
