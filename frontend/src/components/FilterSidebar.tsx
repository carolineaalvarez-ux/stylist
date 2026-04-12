import { useState } from 'react'
import { SlidersHorizontal, X } from 'lucide-react'
import type { MatchFilters } from '../hooks/useMatches'

interface Props {
  filters: MatchFilters
  onChange: (f: MatchFilters) => void
}

// Deep Winter palette for color filter chips
const PALETTE_COLORS = [
  { name: 'Black', hex: '#000000' },
  { name: 'Navy', hex: '#000080' },
  { name: 'Royal Blue', hex: '#4169E1' },
  { name: 'Cobalt', hex: '#0047AB' },
  { name: 'Teal', hex: '#008080' },
  { name: 'Emerald', hex: '#006B3C' },
  { name: 'True Red', hex: '#CC0000' },
  { name: 'Burgundy', hex: '#800020' },
  { name: 'Deep Plum', hex: '#580F41' },
  { name: 'Fuchsia', hex: '#FF0090' },
  { name: 'Charcoal', hex: '#36454F' },
  { name: 'White', hex: '#FFFFFF' },
]

const PRIORITY_BRANDS = [
  'Sézane', 'Equipment', 'Rouje', 'Zimmermann',
  'Doen', 'Maje', 'Vince', 'Theory', 'Toteme',
]

export default function FilterSidebar({ filters, onChange }: Props) {
  const [open, setOpen] = useState(false)

  const update = (patch: Partial<MatchFilters>) => onChange({ ...filters, ...patch, page: 1 })
  const reset = () => onChange({ min_score: 70, page: 1 })

  const hasActive = !!(
    filters.brand ||
    filters.price_min ||
    filters.price_max ||
    (filters.min_score && filters.min_score !== 70) ||
    filters.is_new !== undefined
  )

  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={() => setOpen(v => !v)}
        className="lg:hidden flex items-center gap-2 btn-ghost mb-4"
      >
        <SlidersHorizontal size={16} />
        Filters
        {hasActive && <span className="w-2 h-2 bg-palette-cobalt rounded-full" />}
      </button>

      <aside
        className={`
          lg:block w-full lg:w-56 shrink-0 space-y-6
          ${open ? 'block' : 'hidden'}
        `}
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-700">Filters</h2>
          {hasActive && (
            <button onClick={reset} className="text-xs text-gray-400 hover:text-gray-700 flex items-center gap-1">
              <X size={12} /> Clear
            </button>
          )}
        </div>

        {/* Min score */}
        <div>
          <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Min match score: {filters.min_score ?? 70}
          </label>
          <input
            type="range"
            min={50}
            max={100}
            step={5}
            value={filters.min_score ?? 70}
            onChange={e => update({ min_score: Number(e.target.value) })}
            className="w-full mt-2 accent-palette-navy"
          />
          <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
            <span>50</span><span>100</span>
          </div>
        </div>

        {/* New only */}
        <div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={filters.is_new === true}
              onChange={e => update({ is_new: e.target.checked ? true : undefined })}
              className="rounded accent-palette-navy"
            />
            <span className="text-sm text-gray-700">New today</span>
          </label>
        </div>

        {/* Price range */}
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Price range</p>
          <div className="flex items-center gap-2">
            <input
              type="number"
              placeholder="Min"
              value={filters.price_min ?? ''}
              onChange={e => update({ price_min: e.target.value ? Number(e.target.value) : undefined })}
              className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-palette-cobalt/30"
            />
            <span className="text-gray-400 text-xs">–</span>
            <input
              type="number"
              placeholder="Max"
              value={filters.price_max ?? ''}
              onChange={e => update({ price_max: e.target.value ? Number(e.target.value) : undefined })}
              className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-palette-cobalt/30"
            />
          </div>
        </div>

        {/* Brand quick-picks */}
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Brand</p>
          <div className="flex flex-wrap gap-1.5">
            {PRIORITY_BRANDS.map(b => (
              <button
                key={b}
                onClick={() => update({ brand: filters.brand === b ? undefined : b })}
                className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                  filters.brand === b
                    ? 'bg-palette-navy text-white border-palette-navy'
                    : 'border-gray-200 text-gray-600 hover:border-palette-navy/50'
                }`}
              >
                {b}
              </button>
            ))}
          </div>
          <input
            type="text"
            placeholder="Or type a brand…"
            value={filters.brand && !PRIORITY_BRANDS.includes(filters.brand) ? filters.brand : ''}
            onChange={e => update({ brand: e.target.value || undefined })}
            className="mt-2 w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-palette-cobalt/30"
          />
        </div>

        {/* Palette reference */}
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
            Deep Winter Palette
          </p>
          <div className="flex flex-wrap gap-1.5">
            {PALETTE_COLORS.map(c => (
              <div
                key={c.hex}
                className="w-6 h-6 rounded-full border border-gray-200 shadow-sm cursor-default"
                style={{ backgroundColor: c.hex }}
                title={c.name}
              />
            ))}
          </div>
          <p className="text-[10px] text-gray-400 mt-1.5">Reference only — use for manual spot-checks</p>
        </div>
      </aside>
    </>
  )
}
