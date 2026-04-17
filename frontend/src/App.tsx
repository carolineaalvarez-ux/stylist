import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { Bell, Heart, LayoutGrid } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api } from './lib/api'
import Dashboard from './pages/Dashboard'
import Wishlist from './pages/Wishlist'
import Alerts from './pages/Alerts'

export default function App() {
  const { data: alertsData } = useQuery({
    queryKey: ['alerts', 'unread'],
    queryFn: () => api.get('/alerts/?unread_only=true').then(r => r.data),
    refetchInterval: 60_000,
  })
  const unreadCount: number = alertsData?.length ?? 0

  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col">
        {/* Top nav */}
        <header className="bg-white border-b border-gray-100 sticky top-0 z-40">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
            <span className="font-display text-xl font-semibold tracking-tight text-palette-navy">
              Stylist
            </span>
            <nav className="flex items-center gap-1">
              <NavLink
                to="/"
                className={({ isActive }) =>
                  `flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive ? 'bg-palette-navy text-white' : 'text-gray-600 hover:bg-gray-100'
                  }`
                }
                end
              >
                <LayoutGrid size={16} />
                Matches
              </NavLink>
              <NavLink
                to="/wishlist"
                className={({ isActive }) =>
                  `flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive ? 'bg-palette-navy text-white' : 'text-gray-600 hover:bg-gray-100'
                  }`
                }
              >
                <Heart size={16} />
                Wishlist
              </NavLink>
              <NavLink
                to="/alerts"
                className={({ isActive }) =>
                  `relative flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive ? 'bg-palette-navy text-white' : 'text-gray-600 hover:bg-gray-100'
                  }`
                }
              >
                <Bell size={16} />
                Alerts
                {unreadCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 bg-palette-red text-white text-[10px] font-bold w-4 h-4 rounded-full flex items-center justify-center">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </NavLink>
            </nav>
          </div>
        </header>

        {/* Main content */}
        <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/wishlist" element={<Wishlist />} />
            <Route path="/alerts" element={<Alerts />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
