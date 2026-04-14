import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { Profiles } from './pages/Profiles';
import { ProfileDetail } from './pages/ProfileDetail';
import { Trades } from './pages/Trades';
import { SignalLogs } from './pages/SignalLogs';
import { System } from './pages/System';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,       // 10s — data is fresh for 10s
      refetchOnWindowFocus: true,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="profiles" element={<Profiles />} />
            <Route path="profiles/:id" element={<ProfileDetail />} />
            <Route path="trades" element={<Trades />} />
            <Route path="signals" element={<SignalLogs />} />
            <Route path="system" element={<System />} />
            <Route path="*" element={
              <div className="flex flex-col items-center justify-center h-64 gap-4">
                <h1 className="text-xl font-semibold text-text">Page not found</h1>
                <p className="text-sm text-muted">The page you are looking for does not exist.</p>
                <Link to="/" className="text-sm text-gold hover:text-gold/80 transition-colors">
                  Back to Dashboard
                </Link>
              </div>
            } />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
