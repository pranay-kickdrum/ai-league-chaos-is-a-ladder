import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Plane, MapPin, Clock, Wallet } from 'lucide-react';
import { listTrips } from '../services/api';
import { formatCurrency } from '../lib/utils';

interface HomePageProps {
  onNewTrip: () => void;
  onLoadTrip: (tripId: string) => void;
  onStartWithPrompt: (prompt: string) => void;
}

interface SampleTrip {
  id: string;
  destination: string;
  duration: number;
  budget: number;
  currency: string;
  style: string;
  image?: string;
}

const SAMPLE_TRIP_DISPLAY: Record<string, { image: string; color: string; subtitle: string }> = {
  Rishikesh: {
    image: '🏔️',
    color: 'from-orange-400 to-amber-500',
    subtitle: 'Adventure & Spiritual',
  },
  Goa: {
    image: '🏖️',
    color: 'from-cyan-400 to-blue-500',
    subtitle: 'Family Beach Vacation',
  },
  Coorg: {
    image: '🌿',
    color: 'from-green-400 to-emerald-500',
    subtitle: 'Weekend Coffee Escape',
  },
};

function buildSamplePrompt(trip: any): string {
  const parts: string[] = [];
  parts.push(`Plan a ${trip.duration_days}-day trip to ${trip.destination}`);
  if (trip.budget) parts.push(`with a budget of ${formatCurrency(trip.budget, trip.currency || 'INR')}`);
  if (trip.style) parts.push(`— ${trip.style}`);
  return parts.join(' ') + '.';
}

export default function HomePage({ onNewTrip, onLoadTrip, onStartWithPrompt }: HomePageProps) {
  const [trips, setTrips] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listTrips()
      .then((res) => setTrips(res.trips || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const sampleTrips = trips.filter((t) => t.is_sample);
  const userTrips = trips.filter((t) => !t.is_sample);

  return (
    <div className="max-w-4xl mx-auto px-4 py-12">
      {/* Hero */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center mb-12"
      >
        <h1 className="text-4xl md:text-5xl font-bold text-slate-800 mb-4">
          Plan Your Perfect Trip
        </h1>
        <p className="text-lg text-slate-500 mb-8 max-w-xl mx-auto">
          AI-powered travel planning that researches, plans, verifies, and books — all through a simple conversation.
        </p>
        <button
          onClick={onNewTrip}
          className="inline-flex items-center gap-2 px-8 py-3.5 bg-sunset text-white text-lg font-semibold rounded-2xl hover:bg-orange-600 transition shadow-lg shadow-orange-200"
        >
          <Plane className="w-5 h-5" /> Start Planning
        </button>
      </motion.div>

      {/* Sample Trips */}
      {sampleTrips.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="mb-12"
        >
          <h2 className="text-xl font-bold text-slate-700 mb-4">Example Trips</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {sampleTrips.map((trip) => {
              const dest = trip.destination || 'Trip';
              const display = SAMPLE_TRIP_DISPLAY[dest] ?? {
                image: '✈️',
                color: 'from-slate-400 to-slate-500',
                subtitle: '',
              };

              return (
                <motion.button
                  key={trip.id}
                  whileHover={{ scale: 1.02 }}
                  onClick={() => onStartWithPrompt(buildSamplePrompt(trip))}
                  className="text-left bg-white rounded-2xl overflow-hidden border border-slate-200 shadow-sm hover:shadow-md transition"
                >
                  <div
                    className={`h-28 bg-gradient-to-br ${display.color} flex items-center justify-center text-5xl`}
                  >
                    {display.image}
                  </div>
                  <div className="p-4">
                    <h3 className="font-semibold text-slate-800">{dest}</h3>
                    <p className="text-xs text-slate-500">{display.subtitle}</p>
                    <div className="flex items-center gap-3 mt-2 text-xs text-slate-400">
                      <span className="flex items-center gap-0.5">
                        <Clock className="w-3 h-3" /> {trip.duration_days || '?'}d
                      </span>
                      <span className="flex items-center gap-0.5">
                        <Wallet className="w-3 h-3" />{' '}
                        {formatCurrency(trip.budget ?? 0, trip.currency ?? 'INR')}
                      </span>
                    </div>
                  </div>
                </motion.button>
              );
            })}
          </div>
        </motion.div>
      )}

      {/* User trips */}
      {userTrips.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <h2 className="text-xl font-bold text-slate-700 mb-4">Your Trips</h2>
          <div className="space-y-2">
            {userTrips.map((trip) => (
                <button
                  key={trip.id}
                  onClick={() => onLoadTrip(trip.id)}
                  className="w-full flex items-center justify-between p-4 bg-white border border-slate-200 rounded-xl hover:bg-slate-50 transition"
                >
                  <div className="flex items-center gap-3">
                    <MapPin className="w-5 h-5 text-ocean" />
                    <div className="text-left">
                      <p className="text-sm font-medium text-slate-800">
                        {trip.destination || 'Unknown'}
                      </p>
                      <p className="text-xs text-slate-400">
                        {trip.status} · {new Date(trip.created_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                  <span className="text-xs text-slate-400">→</span>
                </button>
              ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}
