import { useState } from 'react';
import Header from './components/common/Header';
import ErrorBoundary from './components/ErrorBoundary';
import HomePage from './pages/HomePage';
import TripPage from './pages/TripPage';

type Page = { name: 'home' } | { name: 'trip'; tripId?: string };

export default function App() {
  const [page, setPage] = useState<Page>({ name: 'home' });

  return (
    <div className="min-h-screen bg-slate-50">
      <Header
        onNewTrip={() => setPage({ name: 'trip' })}
        onHome={() => setPage({ name: 'home' })}
      />
      <ErrorBoundary>
        {page.name === 'home' && (
          <HomePage
            onNewTrip={() => setPage({ name: 'trip' })}
            onLoadTrip={(id) => setPage({ name: 'trip', tripId: id })}
          />
        )}
        {page.name === 'trip' && (
          <TripPage
            tripId={page.tripId}
            onBack={() => setPage({ name: 'home' })}
          />
        )}
      </ErrorBoundary>
    </div>
  );
}
