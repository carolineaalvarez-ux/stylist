import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { matchesApi, feedbackApi, type Match } from '../lib/api'

export interface MatchFilters {
  page?: number
  page_size?: number
  min_score?: number
  brand?: string
  price_min?: number
  price_max?: number
  is_new?: boolean
}

export function useMatches(filters: MatchFilters = {}) {
  return useQuery({
    queryKey: ['matches', filters],
    queryFn: () => matchesApi.list(filters).then(r => r.data),
    placeholderData: prev => prev,
  })
}

export function useFeedback() {
  const qc = useQueryClient()

  const mutation = useMutation({
    mutationFn: ({
      matchId,
      action,
      note,
    }: {
      matchId: string
      action: string
      note?: string
    }) => feedbackApi.submit(matchId, action, note),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['matches'] })
      qc.invalidateQueries({ queryKey: ['wishlist'] })
    },
  })

  return mutation
}

export function useWishlist() {
  return useQuery({
    queryKey: ['wishlist'],
    queryFn: () => feedbackApi.wishlist().then(r => r.data),
  })
}
