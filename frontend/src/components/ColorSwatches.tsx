interface Color {
  hex: string
  percentage: number
}

interface Props {
  colors: Color[]
  maxSwatches?: number
}

export default function ColorSwatches({ colors, maxSwatches = 5 }: Props) {
  const sorted = [...colors]
    .sort((a, b) => b.percentage - a.percentage)
    .slice(0, maxSwatches)

  return (
    <div className="flex gap-1 items-center">
      {sorted.map((c, i) => (
        <div
          key={i}
          className="w-5 h-5 rounded-full border border-white shadow-sm ring-1 ring-gray-200"
          style={{ backgroundColor: c.hex }}
          title={`${c.hex} (${(c.percentage * 100).toFixed(0)}%)`}
        />
      ))}
    </div>
  )
}
