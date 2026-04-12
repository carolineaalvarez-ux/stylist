import { Bell, CheckCheck, TrendingDown, RefreshCw, ExternalLink } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { alertsApi, type Alert } from '../lib/api'
import clsx from 'clsx'

function AlertIcon({ type }: { type: Alert['alert_type'] }) {
  if (type === 'price_drop') return <TrendingDown size={16} className="text-emerald-600" />
  if (type === 'restock') return <RefreshCw size={16} className="text-palette-cobalt" />
  return <Bell size={16} className="text-palette-plum" />
}

function AlertRow({ alert, onRead }: { alert: Alert; onRead: (id: string) => void }) {
  return (
    <div
      className={clsx(
        'flex items-start gap-4 p-4 rounded-xl border transition-colors',
        alert.is_read
          ? 'bg-white border-gray-100 opacity-60'
          : 'bg-white border-palette-cobalt/20 shadow-sm',
      )}
    >
      <div className="mt-0.5">
        <AlertIcon type={alert.alert_type} />
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 truncate">{alert.product.name}</p>
        {alert.message && (
          <p className="text-sm text-gray-600 mt-0.5">{alert.message}</p>
        )}
        <p className="text-xs text-gray-400 mt-1">
          {new Date(alert.created_at).toLocaleString()}
        </p>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <a
          href={alert.product.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-gray-400 hover:text-palette-navy transition-colors"
        >
          <ExternalLink size={15} />
        </a>
        {!alert.is_read && (
          <button
            onClick={() => onRead(alert.id)}
            className="text-gray-300 hover:text-palette-cobalt transition-colors"
            title="Mark as read"
          >
            <CheckCheck size={15} />
          </button>
        )}
      </div>
    </div>
  )
}

export default function Alerts() {
  const qc = useQueryClient()

  const { data: alerts = [], isLoading } = useQuery({
    queryKey: ['alerts'],
    queryFn: () => alertsApi.list().then(r => r.data),
    refetchInterval: 60_000,
  })

  const markRead = useMutation({
    mutationFn: (id: string) => alertsApi.markRead(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })

  const markAllRead = useMutation({
    mutationFn: () => alertsApi.markAllRead(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })

  const unread = alerts.filter(a => !a.is_read)

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-16 rounded-xl bg-gray-100 animate-pulse" />
        ))}
      </div>
    )
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-display font-semibold text-gray-900">Alerts</h1>
        {unread.length > 0 && (
          <button
            onClick={() => markAllRead.mutate()}
            className="btn-ghost flex items-center gap-1.5 text-sm"
          >
            <CheckCheck size={14} />
            Mark all read
          </button>
        )}
      </div>

      {alerts.length === 0 ? (
        <div className="flex flex-col items-center py-20 text-center">
          <Bell size={48} className="text-gray-200 mb-4" />
          <h2 className="text-lg font-display text-gray-500">No alerts yet</h2>
          <p className="text-sm text-gray-400 mt-1">
            Price drops and restocks on your saved items will appear here.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {alerts.map(alert => (
            <AlertRow key={alert.id} alert={alert} onRead={id => markRead.mutate(id)} />
          ))}
        </div>
      )}
    </div>
  )
}
