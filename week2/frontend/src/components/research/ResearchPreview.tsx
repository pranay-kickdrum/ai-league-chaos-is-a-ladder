import { useState } from 'react';
import { Plane, Hotel, MapPin, Star, ExternalLink, ChevronDown, ChevronUp, Clock, MapPinned, Train, Bus, CheckCircle } from 'lucide-react';
import { formatCurrency } from '../../lib/utils';
import type { ResearchData, ResearchFlight, ResearchHotel, ResearchActivity } from '../../types';

interface ResearchPreviewProps {
  research: ResearchData;
  currency?: string;
  selectedTransportId?: string;
  selectedHotelId?: string;
  recommendedTransportId?: string;
  recommendedHotelId?: string;
  onSelectTransport?: (flight: ResearchFlight) => void;
  onSelectHotel?: (hotel: ResearchHotel) => void;
}

function TransportIcon({ mode }: { mode?: string }) {
  if (mode === 'train') return <Train className="w-3.5 h-3.5 text-emerald-600" />;
  if (mode === 'bus') return <Bus className="w-3.5 h-3.5 text-amber-600" />;
  return <Plane className="w-3.5 h-3.5 text-ocean" />;
}

function TransportCard({ f, currency, isSelected, isRecommended, onSelect }: {
  f: ResearchFlight; currency: string; isSelected?: boolean; isRecommended?: boolean; onSelect?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const selectable = !!onSelect;
  return (
    <div
      className={`rounded-lg p-3 cursor-pointer transition border-2 ${
        isSelected
          ? 'border-ocean bg-ocean/5 ring-1 ring-ocean/20'
          : 'border-transparent bg-slate-50 hover:bg-slate-100 hover:border-ocean/20'
      }`}
      onClick={() => { if (selectable) onSelect(); else setOpen(!open); }}
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-slate-700 flex items-center gap-1.5">
            <TransportIcon mode={f.mode} />
            {f.airline_or_operator || 'Unknown'}
            {isRecommended && (
              <span className="text-[10px] bg-forest/10 text-forest px-1.5 py-0.5 rounded-full font-medium ml-1">Rec.</span>
            )}
            {isSelected && <CheckCircle className="w-3.5 h-3.5 text-ocean ml-1" />}
          </p>
          <div className="flex items-center gap-2 text-xs text-slate-500 mt-0.5">
            {f.departure_time && <span>{f.departure_time}</span>}
            {f.duration && <span>• {f.duration}</span>}
            {!f.duration && f.duration_minutes && f.duration_minutes > 0 && (
              <span>• {Math.floor(f.duration_minutes / 60)}h {f.duration_minutes % 60}m</span>
            )}
            {f.stops !== undefined && (
              <span>• {f.stops === 0 ? 'Non-stop' : `${f.stops} stop${f.stops > 1 ? 's' : ''}`}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="text-right">
            <p className="text-sm font-bold text-sunset">
              {formatCurrency(f.price, f.currency || currency)}
            </p>
            {f.source && <span className="text-[10px] text-slate-400">{f.source}</span>}
          </div>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
            className="p-0.5 hover:bg-slate-200 rounded"
          >
            {open ? <ChevronUp className="w-3.5 h-3.5 text-slate-400" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-400" />}
          </button>
        </div>
      </div>
      {open && (
        <div className="mt-2.5 pt-2.5 border-t border-slate-200 space-y-1.5 text-xs text-slate-600" onClick={(e) => e.stopPropagation()}>
          {f.from_location && f.to_location && (
            <p><span className="text-slate-400">Route:</span> {f.from_location} → {f.to_location}</p>
          )}
          {f.mode && <p><span className="text-slate-400">Mode:</span> {f.mode}</p>}
          {f.class_type && <p><span className="text-slate-400">Class:</span> {f.class_type}</p>}
          {f.stops !== undefined && f.stops > 0 && f.layover_info && (
            <p><span className="text-slate-400">Layover:</span> {f.layover_info}</p>
          )}
          {f.arrival_time && <p><span className="text-slate-400">Arrival:</span> {f.arrival_time}</p>}
          {f.duration_minutes && f.duration_minutes > 0 && (
            <p><span className="text-slate-400">Duration:</span> {Math.floor(f.duration_minutes / 60)}h {f.duration_minutes % 60}m</p>
          )}
          {f.booking_url && (
            <a
              href={f.booking_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1 text-ocean hover:underline font-medium mt-1"
            >
              <ExternalLink className="w-3 h-3" /> View & Book
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function HotelCard({ h, currency, isSelected, isRecommended, onSelect }: {
  h: ResearchHotel; currency: string; isSelected?: boolean; isRecommended?: boolean; onSelect?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const hasPrice = h.price_per_night > 0;
  const selectable = !!onSelect;
  return (
    <div
      className={`rounded-lg p-3 cursor-pointer transition border-2 ${
        isSelected
          ? 'border-ocean bg-ocean/5 ring-1 ring-ocean/20'
          : 'border-transparent bg-slate-50 hover:bg-slate-100 hover:border-ocean/20'
      }`}
      onClick={() => { if (selectable) onSelect(); else setOpen(!open); }}
    >
      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-700 truncate flex items-center gap-1.5">
            {h.name}
            {isRecommended && (
              <span className="text-[10px] bg-forest/10 text-forest px-1.5 py-0.5 rounded-full font-medium">Rec.</span>
            )}
            {isSelected && <CheckCircle className="w-3.5 h-3.5 text-ocean" />}
          </p>
          <div className="flex items-center gap-2 text-xs text-slate-500 mt-0.5">
            {h.rating ? (
              <span className="flex items-center gap-0.5">
                <Star className="w-3 h-3 text-amber-400 fill-amber-400" />
                {h.rating}
              </span>
            ) : null}
            {h.hotel_type && <span className="capitalize">• {h.hotel_type}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="text-right ml-3 shrink-0">
            {hasPrice ? (
              <>
                <p className="text-sm font-bold text-sunset">
                  {formatCurrency(h.price_per_night, h.currency || currency)}
                </p>
                <span className="text-[10px] text-slate-400">/night</span>
              </>
            ) : (
              <span className="text-xs text-slate-400 italic">Price on site</span>
            )}
          </div>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
            className="p-0.5 hover:bg-slate-200 rounded"
          >
            {open ? <ChevronUp className="w-3.5 h-3.5 text-slate-400" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-400" />}
          </button>
        </div>
      </div>
      {open && (
        <div className="mt-2.5 pt-2.5 border-t border-slate-200 space-y-1.5 text-xs text-slate-600" onClick={(e) => e.stopPropagation()}>
          {h.location && (
            <p className="flex items-center gap-1">
              <MapPinned className="w-3 h-3 text-slate-400" /> {h.location}
            </p>
          )}
          {hasPrice && h.total_price && h.total_price > 0 && (
            <p><span className="text-slate-400">Total stay:</span> {formatCurrency(h.total_price, h.currency || currency)}</p>
          )}
          {h.amenities && h.amenities.length > 0 && (
            <div className="flex gap-1 flex-wrap">
              {h.amenities.map((a, j) => (
                <span key={j} className="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">
                  {a}
                </span>
              ))}
            </div>
          )}
          {h.source && <p><span className="text-slate-400">Source:</span> {h.source}</p>}
          {h.booking_url && (
            <a
              href={h.booking_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1 text-ocean hover:underline font-medium mt-1"
            >
              <ExternalLink className="w-3 h-3" /> View & Book
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function ActivityCard({ a, currency }: { a: ResearchActivity; currency: string }) {
  const [open, setOpen] = useState(false);
  const cost = a.cost ?? a.price ?? 0;
  return (
    <div
      className="bg-slate-50 rounded-lg p-2.5 cursor-pointer hover:bg-slate-100 transition border border-transparent hover:border-ocean/20"
      onClick={() => setOpen(!open)}
    >
      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-700 truncate">{a.name}</p>
          <div className="flex items-center gap-2 text-xs text-slate-500 mt-0.5">
            {a.category && (
              <span className="bg-emerald-50 text-emerald-600 px-1.5 py-0.5 rounded text-[10px]">
                {a.category}
              </span>
            )}
            {a.rating ? (
              <span className="flex items-center gap-0.5">
                <Star className="w-3 h-3 text-amber-400 fill-amber-400" />
                {a.rating}
              </span>
            ) : null}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {cost > 0 && (
            <p className="text-xs font-semibold text-slate-600 shrink-0">
              {formatCurrency(cost, a.currency || currency)}
            </p>
          )}
          {open ? <ChevronUp className="w-3.5 h-3.5 text-slate-400" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-400" />}
        </div>
      </div>
      {open && (
        <div className="mt-2 pt-2 border-t border-slate-200 space-y-1.5 text-xs text-slate-600">
          {a.description && <p>{a.description}</p>}
          {a.location && (
            <p className="flex items-center gap-1">
              <MapPinned className="w-3 h-3 text-slate-400" /> {a.location}
            </p>
          )}
          {a.duration_minutes && a.duration_minutes > 0 && (
            <p className="flex items-center gap-1">
              <Clock className="w-3 h-3 text-slate-400" />
              {a.duration_minutes >= 60
                ? `${Math.floor(a.duration_minutes / 60)}h ${a.duration_minutes % 60 > 0 ? `${a.duration_minutes % 60}m` : ''}`
                : `${a.duration_minutes}m`}
            </p>
          )}
          {a.booking_url && (
            <a
              href={a.booking_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1 text-ocean hover:underline font-medium mt-1"
            >
              <ExternalLink className="w-3 h-3" /> View Details
            </a>
          )}
          {!a.booking_url && a.place_id && (
            <a
              href={`https://www.google.com/maps/place/?q=place_id:${a.place_id}`}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1 text-ocean hover:underline font-medium mt-1"
            >
              <ExternalLink className="w-3 h-3" /> View on Maps
            </a>
          )}
        </div>
      )}
    </div>
  );
}

export default function ResearchPreview({
  research,
  currency = 'INR',
  selectedTransportId,
  selectedHotelId,
  recommendedTransportId,
  recommendedHotelId,
  onSelectTransport,
  onSelectHotel,
}: ResearchPreviewProps) {
  const { flights, hotels, activities } = research;
  const trains = research.trains ?? [];
  const buses = research.buses ?? [];

  return (
    <div className="space-y-4">
      {/* Flights */}
      {flights.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Plane className="w-4 h-4 text-ocean" />
            <h3 className="text-sm font-semibold text-slate-800">
              Flights Found ({flights.length})
            </h3>
          </div>
          <div className="space-y-2">
            {flights.slice(0, 5).map((f, i) => (
              <TransportCard
                key={f.id || i}
                f={f}
                currency={currency}
                isSelected={!!selectedTransportId && f.id === selectedTransportId}
                isRecommended={!!recommendedTransportId && f.id === recommendedTransportId}
                onSelect={onSelectTransport ? () => onSelectTransport(f) : undefined}
              />
            ))}
          </div>
        </div>
      )}

      {/* Trains */}
      {trains.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Train className="w-4 h-4 text-emerald-600" />
            <h3 className="text-sm font-semibold text-slate-800">
              Trains Found ({trains.length})
            </h3>
          </div>
          <div className="space-y-2">
            {trains.slice(0, 5).map((t, i) => (
              <TransportCard
                key={t.id || i}
                f={t}
                currency={currency}
                isSelected={!!selectedTransportId && t.id === selectedTransportId}
                isRecommended={!!recommendedTransportId && t.id === recommendedTransportId}
                onSelect={onSelectTransport ? () => onSelectTransport(t) : undefined}
              />
            ))}
          </div>
        </div>
      )}

      {/* Buses */}
      {buses.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Bus className="w-4 h-4 text-amber-600" />
            <h3 className="text-sm font-semibold text-slate-800">
              Buses Found ({buses.length})
            </h3>
          </div>
          <div className="space-y-2">
            {buses.slice(0, 5).map((b, i) => (
              <TransportCard
                key={b.id || i}
                f={b}
                currency={currency}
                isSelected={!!selectedTransportId && b.id === selectedTransportId}
                isRecommended={!!recommendedTransportId && b.id === recommendedTransportId}
                onSelect={onSelectTransport ? () => onSelectTransport(b) : undefined}
              />
            ))}
          </div>
        </div>
      )}

      {/* Hotels */}
      {hotels.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Hotel className="w-4 h-4 text-ocean" />
            <h3 className="text-sm font-semibold text-slate-800">
              Hotels Found ({hotels.length})
            </h3>
          </div>
          <div className="space-y-2">
            {hotels.slice(0, 5).map((h, i) => (
              <HotelCard
                key={h.id || i}
                h={h}
                currency={currency}
                isSelected={!!selectedHotelId && h.id === selectedHotelId}
                isRecommended={!!recommendedHotelId && h.id === recommendedHotelId}
                onSelect={onSelectHotel ? () => onSelectHotel(h) : undefined}
              />
            ))}
          </div>
        </div>
      )}

      {/* Activities */}
      {activities.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <MapPin className="w-4 h-4 text-ocean" />
            <h3 className="text-sm font-semibold text-slate-800">
              Activities Found ({activities.length})
            </h3>
          </div>
          <div className="space-y-2">
            {activities.slice(0, 8).map((a, i) => (
              <ActivityCard key={i} a={a} currency={currency} />
            ))}
            {activities.length > 8 && (
              <p className="text-xs text-slate-400 text-center">
                + {activities.length - 8} more activities
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
