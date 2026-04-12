import { useState } from 'react'
import { ExternalLink, Heart, X, Bookmark, ChevronDown, ChevronUp, AlertTriangle } from 'lucide-react'
import clsx from 'clsx'
import type { Match } from '../lib/api'
import { useFeedback } from '../hooks/useMatches'
import ColorSwatches from './ColorSwatches'

interface Props {
  match: Match
}

function ScoreBadge({ score }: { score: number }) {
  const cls = score >= 85 ? 'score-high' : score >= 70 ? 'score-medium' : 'score-low'
  return <span className={cls}>{score}</span>
}

export default function ProductCard({ match }: Props) {
  const [expanded, setExpanded] = useState(false)
  const feedback = useFeedback()
  const { product } = match

  const act = (action: string) =>
    feedback.mutate({ matchId: match.id, action })

  const isPending = feedback.isPending

  return (
    <article className={clsx('card flex flex-col transition-all duration-200', match.is_new && 'ring-2 ring-palette-cobalt/40')}>
      {/* Image */}
      <div className="relative aspect-[3/4] bg-gray-100 overflow-hidden">
        {product.image_url ? (
          <img
            src={product.image_url}
            alt={product.name}
            className="w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-gray-300 text-sm">
            No image
          </div>
        )}

        {/* Score overlay */}
        <div className="absolute top-2 left-2 flex gap-1">
          <ScoreBadge score={match.overall_score} />
          {match.is_new && (
            <span className="score-badge bg-palette-cobalt text-white">New</span>
          )}
          {match.is_borderline_color && (
            <span className="score-badge bg-amber-100 text-amber-800">
              <AlertTriangle size={10} className="mr-0.5" />
              Borderline
            </span>
          )}
          {product.is_priority_brand && (
            <span className="score-badge bg-palette-plum/20 text-palette-plum">★</span>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex flex-col flex-1 p-4 gap-3">
        {/* Brand + name */}
        <div>
          {product.brand && (
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-0.5">
              {product.brand}
            </p>
          )}
          <h3 className="text-sm font-medium text-gray-900 line-clamp-2 leading-snug">
            {product.name}
          </h3>
        </div>

        {/* Price + source */}
        <div className="flex items-center justify-between">
          <span className="text-base font-semibold text-palette-navy">
            ${product.price.toFixed(0)}
          </span>
          <span className="text-xs text-gray-400 capitalize">{product.source}</span>
        </div>

        {/* Color swatches */}
        {product.dominant_colors && product.dominant_colors.length > 0 && (
          <ColorSwatches colors={product.dominant_colors} />
        )}

        {/* Fabric pill */}
        {product.fabric_raw && (
          <p className="text-xs text-gray-500 truncate" title={product.fabric_raw}>
            {product.fabric_raw}
          </p>
        )}

        {/* Score breakdown */}
        <div className="grid grid-cols-2 gap-2 text-xs text-gray-500">
          <div className="flex items-center gap-1">
            <span>Color</span>
            <span className="font-semibold text-gray-700">{match.color_score}/100</span>
          </div>
          <div className="flex items-center gap-1">
            <span>Fabric</span>
            <span className="font-semibold text-gray-700">{match.fabric_score}/100</span>
          </div>
        </div>

        {/* Claude analysis (expandable) */}
        {match.claude_style_analysis && (
          <div className="border-t border-gray-100 pt-3">
            <button
              onClick={() => setExpanded(v => !v)}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 transition-colors"
            >
              {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              Stylist analysis
            </button>
            {expanded && (
              <div className="mt-2 space-y-2">
                <p className="text-xs text-gray-600 leading-relaxed">
                  {match.claude_style_analysis}
                </p>
                {match.claude_color_reasoning && (
                  <p className="text-xs text-palette-navy/70 italic leading-relaxed">
                    {match.claude_color_reasoning}
                  </p>
                )}
                {match.claude_flags && match.claude_flags.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {match.claude_flags.map(flag => (
                      <span key={flag} className="px-1.5 py-0.5 bg-gray-100 text-gray-500 text-[10px] rounded-full">
                        {flag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 mt-auto pt-2 border-t border-gray-100">
          <button
            onClick={() => act('rejected')}
            disabled={isPending}
            className="flex-1 flex items-center justify-center gap-1 py-2 rounded-lg text-sm text-gray-500 hover:bg-red-50 hover:text-red-600 transition-colors disabled:opacity-50"
            title="Not for me"
          >
            <X size={15} />
          </button>
          <button
            onClick={() => act('saved')}
            disabled={isPending}
            className="flex-1 flex items-center justify-center gap-1 py-2 rounded-lg text-sm text-gray-500 hover:bg-amber-50 hover:text-amber-600 transition-colors disabled:opacity-50"
            title="Save for later"
          >
            <Bookmark size={15} />
          </button>
          <button
            onClick={() => act('accepted')}
            disabled={isPending}
            className="flex-1 flex items-center justify-center gap-1 py-2 rounded-lg text-sm text-white bg-palette-navy hover:bg-palette-cobalt transition-colors disabled:opacity-50"
            title="Add to wishlist"
          >
            <Heart size={15} />
          </button>
          <a
            href={product.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 flex items-center justify-center gap-1 py-2 rounded-lg text-sm text-gray-500 hover:bg-gray-100 transition-colors"
            title="View on retailer"
          >
            <ExternalLink size={15} />
          </a>
        </div>
      </div>
    </article>
  )
}
