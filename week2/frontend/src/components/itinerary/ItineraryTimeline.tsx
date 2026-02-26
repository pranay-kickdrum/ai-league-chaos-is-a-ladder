import { useState } from 'react';
import { Calendar } from 'lucide-react';
import DayCard from './DayCard';
import type { Itinerary } from '../../types';

interface ItineraryTimelineProps {
  itinerary: Itinerary;
}

export default function ItineraryTimeline({ itinerary }: ItineraryTimelineProps) {
  const [expandedDay, setExpandedDay] = useState<number>(1);

  if (!itinerary?.days?.length) {
    return (
      <div className="text-center py-8 text-slate-400">
        <Calendar className="w-8 h-8 mx-auto mb-2" />
        <p className="text-sm">Itinerary will appear here</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-slate-700 mb-3">
        {itinerary.destination} — {itinerary.duration_days} Days
      </h3>
      {itinerary.days.map((day) => (
        <DayCard
          key={day.day_number}
          day={day}
          isExpanded={expandedDay === day.day_number}
          onToggle={() =>
            setExpandedDay(expandedDay === day.day_number ? -1 : day.day_number)
          }
        />
      ))}
    </div>
  );
}
