import { MapPin } from 'lucide-react';
import type { MapMarker } from '../../types';

interface TripMapProps {
  markers: MapMarker[];
}

const DAY_COLORS = [
  'text-sunset',
  'text-ocean',
  'text-forest',
  'text-purple-500',
  'text-pink-500',
  'text-amber-500',
  'text-cyan-500',
];

export default function TripMap({ markers }: TripMapProps) {
  if (!markers?.length) {
    return (
      <div className="bg-slate-100 rounded-xl h-48 flex items-center justify-center text-slate-400">
        <div className="text-center">
          <MapPin className="w-8 h-8 mx-auto mb-1" />
          <p className="text-sm">Map will appear here</p>
        </div>
      </div>
    );
  }

  // Static map view — shows marker list (Google Maps JS API integration would go here)
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-1.5">
        <MapPin className="w-4 h-4 text-ocean" /> Trip Locations
      </h3>
      <div className="space-y-1.5 max-h-48 overflow-y-auto">
        {markers.map((m, i) => (
          <div key={i} className="flex items-center gap-2 text-sm">
            <MapPin className={`w-3.5 h-3.5 ${DAY_COLORS[(m.day ?? 1) - 1] ?? 'text-slate-400'}`} />
            <span className="text-slate-700">{m.name}</span>
            {m.day && (
              <span className="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">
                Day {m.day}
              </span>
            )}
          </div>
        ))}
      </div>
      {/* Placeholder for actual Google Maps embed */}
      <div className="mt-3 bg-slate-50 rounded-lg h-32 flex items-center justify-center text-xs text-slate-400">
        Interactive map coming soon
      </div>
    </div>
  );
}
