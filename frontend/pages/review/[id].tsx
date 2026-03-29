import { useRouter } from 'next/router'
import Head from 'next/head'
import Link from 'next/link'
import useSWR from 'swr'
import { swrFetcher, ReviewDetail, ReviewIssue } from '@/lib/api'

/** Severity badge with color coding: high=red, medium=amber, low=blue */
function SeverityBadge({ severity }: { severity: string }) {
  const styles: Record<string, string> = {
    high: 'bg-red-500/20 text-red-400 border-red-500/30',
    medium: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    low: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  }
  return (
    <span className={`px-2 py-0.5 text-xs font-semibold rounded-full border uppercase ${styles[severity] || 'bg-gray-700 text-gray-300'}`}>
      {severity}
    </span>
  )
}

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

export default function ReviewDetailPage() {
  const router = useRouter()
  const { id } = router.query

  // Auto-refresh every 30s while review is still pending/processing
  const { data: review, error, isLoading } = useSWR<ReviewDetail>(
    id ? `/reviews/${id}` : null,
    swrFetcher,
    { refreshInterval: 30000 }
  )

  if (isLoading) {
    return (
      <div className="min-h-screen p-6 max-w-4xl mx-auto">
        <div className="text-gray-400 animate-pulse">Loading review...</div>
      </div>
    )
  }

  if (error || !review) {
    return (
      <div className="min-h-screen p-6 max-w-4xl mx-auto">
        <div className="p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-300">
          Failed to load review. <Link href="/" className="underline">Go back</Link>
        </div>
      </div>
    )
  }

  const resp = review.response_json
  const issues: ReviewIssue[] = resp?.issues || []
  const suggestions: string[] = resp?.suggestions || []

  return (
    <>
      <Head>
        <title>Review #{review.id} — AI Code Reviewer</title>
      </Head>

      <div className="min-h-screen p-6 max-w-4xl mx-auto">
        {/* Back link */}
        <Link href="/" className="text-blue-400 hover:text-blue-300 text-sm mb-6 inline-block">
          ← Back to dashboard
        </Link>

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <h1 className="text-2xl font-bold text-white">
              PR #{review.pr_number}
            </h1>
            <StatusBadge status={review.status} />
            {review.status === 'done' && (
              review.approved ? (
                <span className="text-green-400 text-sm font-medium">✅ Approved</span>
              ) : (
                <span className="text-yellow-400 text-sm font-medium">⚠️ Changes Requested</span>
              )
            )}
          </div>
          <p className="text-gray-400">{review.pr_title || 'Untitled PR'}</p>
          <div className="flex gap-4 mt-2 text-xs text-gray-500">
            <span className="font-mono">{review.repo_full_name}</span>
            <span>Commit: <code className="text-gray-400">{review.commit_sha?.slice(0, 8)}</code></span>
            {review.created_at && <span>Created: {new Date(review.created_at).toLocaleString()}</span>}
            {review.completed_at && <span>Completed: {new Date(review.completed_at).toLocaleString()}</span>}
          </div>
        </div>

        {/* Error message for failed reviews */}
        {review.status === 'failed' && review.error_message && (
          <div className="mb-6 p-4 bg-red-900/20 border border-red-800 rounded-lg">
            <h3 className="text-red-400 font-medium mb-1">Error</h3>
            <p className="text-red-300 text-sm">{review.error_message}</p>
          </div>
        )}

        {/* Processing state */}
        {(review.status === 'pending' || review.status === 'processing') && (
          <div className="mb-6 p-4 bg-blue-900/20 border border-blue-800 rounded-lg">
            <p className="text-blue-300 text-sm animate-pulse">
              Review is {review.status}... This page auto-refreshes every 30 seconds.
            </p>
          </div>
        )}

        {/* Summary */}
        {resp && (
          <>
            <div className="mb-6 p-4 bg-gray-900 border border-gray-800 rounded-lg">
              <h2 className="text-lg font-semibold text-white mb-2">Summary</h2>
              <p className="text-gray-300">{resp.summary}</p>
            </div>

            {/* Issues */}
            {issues.length > 0 && (
              <div className="mb-6">
                <h2 className="text-lg font-semibold text-white mb-3">
                  Issues ({issues.length})
                </h2>
                <div className="space-y-3">
                  {issues.map((issue, i) => (
                    <div
                      key={i}
                      className="p-4 bg-gray-900 border border-gray-800 rounded-lg flex items-start gap-3"
                    >
                      <SeverityBadge severity={issue.severity} />
                      <div className="flex-1">
                        <p className="text-gray-200">{issue.message}</p>
                        {issue.line > 0 && (
                          <p className="text-gray-500 text-xs mt-1">Line {issue.line}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Suggestions */}
            {suggestions.length > 0 && (
              <div className="mb-6">
                <h2 className="text-lg font-semibold text-white mb-3">Suggestions</h2>
                <ul className="space-y-2">
                  {suggestions.map((s, i) => (
                    <li key={i} className="flex items-start gap-2 text-gray-300">
                      <span className="text-blue-400 mt-0.5">→</span>
                      <span>{s}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Raw JSON for debugging */}
            <details className="mb-6">
              <summary className="text-gray-500 text-sm cursor-pointer hover:text-gray-400">
                View raw JSON response
              </summary>
              <pre className="mt-2 p-4 bg-gray-900 border border-gray-800 rounded-lg text-xs text-gray-400 overflow-x-auto">
                {JSON.stringify(resp, null, 2)}
              </pre>
            </details>
          </>
        )}
      </div>
    </>
  )
}
