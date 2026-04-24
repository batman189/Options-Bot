import { NavLink, Outlet } from 'react-router-dom';
import {
  LayoutDashboard, Users, History, Search, Activity, ChevronRight,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { ExecutionModeBanner } from './ExecutionModeBanner';

const NAV = [
  { to: '/',           icon: LayoutDashboard, label: 'Dashboard'     },
  { to: '/profiles',   icon: Users,            label: 'Profiles'      },
  { to: '/trades',     icon: History,          label: 'Trade History' },
  { to: '/signals',    icon: Search,           label: 'Signal Logs'  },
  { to: '/system',     icon: Activity,         label: 'System Status' },
];

export function Layout() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: api.system.health,
    refetchInterval: 30_000,
    retry: false,
  });

  return (
    <div className="flex h-full min-h-screen">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 bg-surface border-r border-border flex flex-col">
        {/* Logo */}
        <div className="px-5 pt-6 pb-5 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded bg-gold/10 border border-gold/30 flex items-center justify-center">
              <span className="text-gold font-mono text-xs font-bold">OB</span>
            </div>
            <span className="font-semibold text-text tracking-tight">OptionsBot</span>
          </div>
          <div className="mt-2 flex items-center gap-1.5">
            <span className={`h-1.5 w-1.5 rounded-full ${health ? 'bg-profit' : 'bg-muted'}`} />
            <span className="text-2xs text-muted font-mono">
              {health ? `v${health.version} — online` : 'connecting...'}
            </span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-2 py-4 space-y-0.5">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors group
                ${isActive
                  ? 'bg-gold/10 text-gold border border-gold/20'
                  : 'text-muted hover:text-text hover:bg-panel border border-transparent'}`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={15} className={isActive ? 'text-gold' : 'text-muted group-hover:text-text'} />
                  <span>{label}</span>
                  {isActive && <ChevronRight size={12} className="ml-auto text-gold/50" />}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-border">
          <p className="text-2xs text-muted font-mono">
            API: localhost:8000
          </p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 flex flex-col overflow-auto bg-base">
        {/* Shadow Mode banner — renders only when backend reports
            EXECUTION_MODE=shadow. No-op in live mode. */}
        <ExecutionModeBanner />
        <div className="flex-1 p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
