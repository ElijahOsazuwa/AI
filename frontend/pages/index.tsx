import Head from 'next/head'
import Link from 'next/link'
import useSWR from 'swr'
import { swrFetcher, ReviewSummary } from '@/lib/api'

/** Map review status to a styled badge */
function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    processing: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    done: 'bg-green-500/20 text-green-400 border-green-500/30',
    failed: 'bg-red-500/20 text-red-400 border-red-500/30',
  }
  return (
    <span className={`px-2 py-0.5 text-xs font-medium rounded-full border ${styles[status] || 'bg-gray-700 text-gray-300'}`}>
      {status}
    </span>
  )
}

/** Format ISO timestamp to a human-readable relative or absolute string */
function formatTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  return d.toLocaleDateString()
}

export default function Dashboard() {
  // Auto-refresh every 30 seconds so the dashboard stays current
  const { data, error, isLoading } = useSWR('/reviews?limit=50&offset=0', swrFetcher, {
    refreshInterval: 30000,
  })

  const reviews: ReviewSummary[] = data?.reviews || []

  return (
    <>
      <Head>
        <title>AI Code Reviewer — Dashboard</title>
      </Head>

      <div className="min-h-screen p-6 max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white">AI Code Reviewer</h1>
          <p className="text-gray-400 mt-1">Recent pull request reviews powered by Ollama</p>
        </div>

        {/* Error state */}
        {error && (
          <div className="mb-4 p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-300">
            Failed to load reviews. Is the backend running?
          </div>
        )}

        {/* Loading state */}
        {isLoading && (
          <div className="text-gray-400 animate-pulse">Loading reviews...</div>
        )}

        {/* Reviews table */}
        {!isLoading && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-gray-400 text-left">
                  <th className="px-4 py-3 font-medium">PR</th>
                  <th className="px-4 py-3 font-medium">Repository</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Approved</th>
                  <th className="px-4 py-3 font-medium">Time</th>
                </tr>
              </thead>
              <tbody>
                {reviews.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-12 text-center text-gray-500">
                      No reviews yet. Open a pull request to get started.
                    </td>
                  </tr>
                )}
                {reviews.map((r) => (
                  <Link key={r.id} href={`/review/${r.id}`} legacyBehavior>
                    <tr className="border-b border-gray-800/50 hover:bg-gray-800/50 cursor-pointer transition-colors">
                      <td className="px-4 py-3">
                        <div className="font-medium text-white">
                          #{r.pr_number}
                        </div>
                        <div className="text-gray-400 text-xs truncate max-w-xs">
                          {r.pr_title || 'Untitled PR'}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-gray-300 font-mono text-xs">
                        {r.repo_full_name}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={r.status} />
                      </td>
                      <td className="px-4 py-3">
                        {r.status === 'done' ? (
                          r.approved ? (
                            <span className="text-green-400">✅ Yes</span>
                          ) : (
                            <span className="text-yellow-400">⚠️ No</span>
                          )
                        ) : (
                          <span className="text-gray-500">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-gray-400 text-xs">
                        {formatTime(r.created_at)}
                      </td>
                    </tr>
                  </Link>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Footer with total count */}
        {data?.total != null && (
          <p className="mt-4 text-gray-500 text-sm">
            Showing {reviews.length} of {data.total} reviews
          </p>
        )}
      </div>
    </>
  )
}
