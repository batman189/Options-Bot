import { BrowserRouter, Routes, Route } from 'react-router-dom';
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
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
