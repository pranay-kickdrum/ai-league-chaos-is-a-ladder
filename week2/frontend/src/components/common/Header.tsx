import { Plane } from 'lucide-react';

interface HeaderProps {
  onNewTrip: () => void;
  onHome: () => void;
}

export default function Header({ onNewTrip, onHome }: HeaderProps) {
  return (
    <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between sticky top-0 z-50">
      <button onClick={onHome} className="flex items-center gap-2 hover:opacity-80 transition">
        <Plane className="w-6 h-6 text-sunset" />
        <h1 className="text-xl font-bold text-slate-800">TripCraft</h1>
      </button>
      <div className="flex gap-3">
        <button
          onClick={onNewTrip}
          className="px-4 py-2 bg-sunset text-white rounded-lg text-sm font-medium hover:bg-orange-600 transition"
        >
          New Trip
        </button>
      </div>
    </header>
  );
}
