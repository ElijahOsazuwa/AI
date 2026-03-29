/**
 * Fetch wrapper for the backend API.
 * Centralizes the base URL and error handling for all API calls.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface ReviewSummary {
  id: number
  repo_full_name: string
  pr_number: number
  pr_title: string | null
  commit_sha: string
  status: 'pending' | 'processing' | 'done' | 'failed'
  summary: string | null
  approved: boolean | null
  created_at: string | null
  completed_at: string | null
}

export interface ReviewIssue {
  severity: 'high' | 'medium' | 'low'
  line: number
  message: string
}

export interface ReviewDetail extends ReviewSummary {
  response_json: {
    summary: string
    issues: ReviewIssue[]
    suggestions: string[]
    approved: boolean
  } | null
  error_message: string | null
}

export interface ReviewsResponse {
  total: number
  limit: number
  offset: number
  reviews: ReviewSummary[]
}

/** Fetch paginated list of reviews for the dashboard table */
export async function fetchReviews(limit = 20, offset = 0): Promise<ReviewsResponse> {
  const res = await fetch(`${API_BASE}/reviews?limit=${limit}&offset=${offset}`)
  if (!res.ok) throw new Error(`Failed to fetch reviews: ${res.status}`)
  return res.json()
}

/** Fetch a single review by ID — includes full Ollama response */
export async function fetchReview(id: number): Promise<ReviewDetail> {
  const res = await fetch(`${API_BASE}/reviews/${id}`)
  if (!res.ok) throw new Error(`Failed to fetch review ${id}: ${res.status}`)
  return res.json()
}

/** SWR-compatible fetcher — SWR passes the URL key as the argument */
export const swrFetcher = (url: string) =>
  fetch(`${API_BASE}${url}`).then((res) => {
    if (!res.ok) throw new Error(`API error: ${res.status}`)
    return res.json()
  })
