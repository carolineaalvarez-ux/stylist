import { Heart } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { feedbackApi } from '../lib/api'
import ProductCard from '../components/ProductCard'

export default function Wishlist() {
  const { data: items = [], isLoading } = useQuery({
    queryKey: ['wishlist'],
    queryFn: () => feedbackApi.wishlist().then(r => r.data),
  })

  const saved = items.filter(i => i.action === 'saved')
  const accepted = items.filter(i => i.action === 'accepted')

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-5">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card aspect-[3/5] animate-pulse bg-gray-100" />
        ))}
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <Heart size={48} className="text-gray-200 mb-4" />
        <h2 className="text-xl font-display font-semibold text-gray-600 mb-2">
          Your wishlist is empty
        </h2>
        <p className="text-sm text-gray-400 max-w-xs">
          Head to the Matches tab and hit the heart icon on items you love.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-10">
      <h1 className="text-2xl font-display font-semibold text-gray-900">Wishlist</h1>

      {accepted.length > 0 && (
        <section>
          <h2 className="text-base font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Heart size={16} className="text-palette-burgundy" />
            Saved to wishlist ({accepted.length})
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-5">
            {accepted.map(item => (
              <ProductCard key={item.id} match={item.match} />
            ))}
          </div>
        </section>
      )}

      {saved.length > 0 && (
        <section>
          <h2 className="text-base font-semibold text-gray-700 mb-4">
            Saved for later ({saved.length})
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-5">
            {saved.map(item => (
              <ProductCard key={item.id} match={item.match} />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
