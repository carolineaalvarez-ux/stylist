import { useState } from 'react'
import { RefreshCw, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
import { useMutation } from '@tanstack/react-query'
import { useMatches, type MatchFilters } from '../hooks/useMatches'
import { scraperApi } from '../lib/api'
import ProductCard from '../components/ProductCard'
import FilterSidebar from '../components/FilterSidebar'

export default function Dashboard() {
  const [filters, setFilters] = useState<MatchFilters>({
    min_score: 70,
    page: 1,
    page_size: 24,
  })

  const { data, isLoading, isFetching } = useMatches(filters)

  const runScraper = useMutation({
    mutationFn: () => scraperApi.run(),
  })

  const totalPages = data ? Math.ceil(data.total / (filters.page_size ?? 24)) : 0
  const currentPage = filters.page ?? 1

  return (
    <div className="flex flex-col gap-6">
      {/* Page header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-display font-semibold text-gray-900">Today's Matches</h1>
          {data && (
            <p className="text-sm text-gray-500 mt-1">
              {data.total} item{data.total !== 1 ? 's' : ''} matching your Deep Winter profile
            </p>
          )}
        </div>
        <button
          onClick={() => runScraper.mutate()}
          disabled={runScraper.isPending}
          className="btn-primary flex items-center gap-2"
          title="Run scraper now"
        >
          {runScraper.isPending ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <RefreshCw size={15} />
          )}
          {runScraper.isPending ? 'Scanning…' : 'Scan now'}
        </button>
      </div>

      {runScraper.isSuccess && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3 text-sm text-emerald-800">
          Scrape started — new matches will appear in a few minutes.
        </div>
      )}

      {/* Body: sidebar + grid */}
      <div className="flex gap-8">
        <FilterSidebar filters={filters} onChange={setFilters} />

        <div className="flex-1 min-w-0">
          {/* Loading state */}
          {isLoading && (
            <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-5">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="card aspect-[3/5] animate-pulse bg-gray-100" />
              ))}
            </div>
          )}

          {/* Results */}
          {!isLoading && data && data.items.length > 0 && (
            <div
              className={`grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-5 transition-opacity ${
                isFetching ? 'opacity-60' : ''
              }`}
            >
              {data.items.map(match => (
                <ProductCard key={match.id} match={match} />
              ))}
            </div>
          )}

          {/* Empty state */}
          {!isLoading && data && data.items.length === 0 && (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="text-5xl mb-4">✨</div>
              <h3 className="text-lg font-display font-semibold text-gray-700 mb-2">
                No matches yet
              </h3>
              <p className="text-sm text-gray-500 max-w-sm mb-6">
                Hit "Scan now" to start scraping ASOS and Nordstrom for items
                that match your Deep Winter palette.
              </p>
              <button onClick={() => runScraper.mutate()} className="btn-primary">
                Run first scan
              </button>
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-3 mt-8">
              <button
                onClick={() => setFilters(f => ({ ...f, page: Math.max(1, (f.page ?? 1) - 1) }))}
                disabled={currentPage <= 1}
                className="btn-ghost"
              >
                <ChevronLeft size={16} />
              </button>
              <span className="text-sm text-gray-500">
                Page {currentPage} of {totalPages}
              </span>
              <button
                onClick={() => setFilters(f => ({ ...f, page: (f.page ?? 1) + 1 }))}
                disabled={currentPage >= totalPages}
                className="btn-ghost"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
