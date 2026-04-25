import { motion } from 'framer-motion';
import { CheckCircle, XCircle, RotateCcw, MapPin, Calendar, Users, Wallet, Compass, ExternalLink, AlertTriangle, Plane, Train, Bus, Hotel } from 'lucide-react';
import { formatCurrency } from '../../lib/utils';
import type { BookingOption, CheckpointData, ResearchFlight, ResearchHotel } from '../../types';

/* ── Booking card sub-component for CP3 ── */

function BookingCard({ option, emoji, sectionTitle }: { option: BookingOption; emoji: string; sectionTitle: string }) {
  const bgClass = option.category === 'travel'
    ? 'from-blue-50/50 to-slate-50'
    : 'from-amber-50/40 to-slate-50';
  const labelColor = option.category === 'travel' ? 'text-blue-700' : 'text-amber-700';

  return (
    <div className={`bg-gradient-to-br ${bgClass} rounded-lg border border-slate-100 p-3`}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-base">{emoji}</span>
        <h5 className={`text-xs font-semibold uppercase tracking-wider ${labelColor}`}>{sectionTitle}</h5>
      </div>

      <div className="space-y-1">
        {option.route && (
          <p className="text-sm text-slate-800">
            <span className="text-slate-400 text-xs mr-1">Route:</span>
            <span className="font-medium">{option.route}</span>
          </p>
        )}
        {option.mode && (
          <p className="text-sm text-slate-800">
            <span className="text-slate-400 text-xs mr-1">Mode:</span>
            <span className="font-medium">{option.mode}</span>
          </p>
        )}
        <p className="text-sm text-slate-800">
          <span className="text-slate-400 text-xs mr-1">{option.category === 'stay' ? 'Property:' : 'Provider:'}</span>
          <span className="font-medium">{option.name}</span>
        </p>
        {option.details.filter(d => d).map((d, i) => (
          <p key={i} className="text-xs text-slate-500">{d}</p>
        ))}
      </div>

      <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-200/60">
        <span className="text-sm font-bold text-slate-800">
          {formatCurrency(option.cost, option.currency)}
        </span>
        {option.booking_url && (
          <a
            href={option.booking_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs font-medium text-ocean hover:text-cyan-700 transition"
          >
            🔗 Book Now <ExternalLink className="w-3 h-3" />
          </a>
        )}
      </div>
    </div>
  );
}

/* ── Main approval card ── */

interface ApprovalCardProps {
  checkpoint: CheckpointData;
  onAction: (action: string, metadata?: Record<string, string>) => void;
  selectedTransport?: ResearchFlight;
  selectedHotel?: ResearchHotel;
}

export default function ApprovalCard({ checkpoint, onAction, selectedTransport, selectedHotel }: ApprovalCardProps) {
  const { type } = checkpoint;

  const handlePlanSelect = (planId: string) => {
    const metadata: Record<string, string> = {};
    if (selectedTransport?.id) metadata.selected_transport_id = selectedTransport.id;
    if (selectedHotel?.id) metadata.selected_hotel_id = selectedHotel.id;
    onAction(`select_plan:${planId}`, Object.keys(metadata).length > 0 ? metadata : undefined);
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="bg-white border-2 border-ocean/30 rounded-xl p-4 my-3 shadow-md"
    >
      {/* Checkpoint 1: Trip Understanding + Plan Direction */}
      {type === 'plan_direction' && (
        <div>
          <h4 className="font-semibold text-slate-800 mb-3 text-base">Destination & Plan Direction</h4>

          {/* Trip Understanding */}
          {checkpoint.trip_understanding && (
            <div className="bg-gradient-to-br from-slate-50 to-blue-50/30 rounded-lg p-3 mb-4 border border-slate-100">
              <h5 className="text-xs font-semibold text-ocean uppercase tracking-wider mb-2">Trip Understanding</h5>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
                <div className="flex items-center gap-1.5 text-slate-600">
                  <Users className="w-3.5 h-3.5 text-slate-400" />
                  <span className="text-slate-400">Travelers:</span>
                  <span className="font-medium text-slate-700 capitalize">
                    {checkpoint.trip_understanding.traveler_count > 1
                      ? `${checkpoint.trip_understanding.traveler_count} ${checkpoint.trip_understanding.traveler_type}`
                      : checkpoint.trip_understanding.traveler_type}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 text-slate-600">
                  <Compass className="w-3.5 h-3.5 text-slate-400" />
                  <span className="text-slate-400">Theme:</span>
                  <span className="font-medium text-slate-700 capitalize">{checkpoint.trip_understanding.styles}</span>
                </div>
                <div className="flex items-center gap-1.5 text-slate-600">
                  <Wallet className="w-3.5 h-3.5 text-slate-400" />
                  <span className="text-slate-400">Budget:</span>
                  <span className="font-medium text-slate-700">{formatCurrency(checkpoint.trip_understanding.budget, checkpoint.trip_understanding.currency)}</span>
                </div>
                <div className="flex items-center gap-1.5 text-slate-600">
                  <MapPin className="w-3.5 h-3.5 text-slate-400" />
                  <span className="text-slate-400">Origin:</span>
                  <span className="font-medium text-slate-700">{checkpoint.trip_understanding.origin}</span>
                </div>
                <div className="flex items-center gap-1.5 text-slate-600">
                  <Calendar className="w-3.5 h-3.5 text-slate-400" />
                  <span className="text-slate-400">Dates:</span>
                  <span className="font-medium text-slate-700">{checkpoint.trip_understanding.start_date}</span>
                </div>
                <div className="flex items-center gap-1.5 text-slate-600">
                  <Calendar className="w-3.5 h-3.5 text-slate-400" />
                  <span className="text-slate-400">Duration:</span>
                  <span className="font-medium text-slate-700">{checkpoint.trip_understanding.duration_days} days</span>
                </div>
              </div>
              {checkpoint.trip_understanding.interests && checkpoint.trip_understanding.interests.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {checkpoint.trip_understanding.interests.map((interest, i) => (
                    <span key={i} className="text-[10px] bg-ocean/10 text-ocean px-2 py-0.5 rounded-full font-medium">
                      {interest}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {checkpoint.budget_feasibility && !checkpoint.budget_feasibility.is_feasible && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-3 text-sm text-amber-800">
              ⚠️ {checkpoint.budget_feasibility.suggestion}
            </div>
          )}

          {checkpoint.travel_advisory && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-3 text-sm text-blue-800">
              🌍 International travel detected. {checkpoint.travel_advisory.visa_required
                ? 'Visa may be required.'
                : 'No visa required.'}
            </div>
          )}

          {/* Plan Options */}
          <h5 className="text-xs font-semibold text-ocean uppercase tracking-wider mb-2">Proposed Plan Options</h5>
          {checkpoint.plan_options?.map((opt, idx) => {
            // Compute adjusted total when user picks different transport/hotel
            // Transport prices in research are per-person; estimated_total includes cost for all travelers
            const travelerCount = Math.max(checkpoint.trip_understanding?.traveler_count ?? 1, 1);
            const origTransportPricePP = checkpoint.research
              ? [...(checkpoint.research.flights ?? []), ...(checkpoint.research.trains ?? []), ...(checkpoint.research.buses ?? [])]
                  .find(t => t.id === checkpoint.recommended_transport_id)?.price ?? 0
              : 0;
            const origHotelPpn = checkpoint.research?.hotels?.find(h => h.id === checkpoint.recommended_hotel_id)?.price_per_night ?? 0;
            const nights = Math.max((checkpoint.trip_understanding?.duration_days ?? 2) - 1, 1);

            let adjustedTotal = opt.estimated_total ?? 0;
            if (selectedTransport && selectedTransport.id !== checkpoint.recommended_transport_id) {
              adjustedTotal = adjustedTotal - (origTransportPricePP * travelerCount) + (selectedTransport.price * travelerCount);
            }
            if (selectedHotel && selectedHotel.id !== checkpoint.recommended_hotel_id) {
              adjustedTotal = adjustedTotal - (origHotelPpn * nights) + (selectedHotel.price_per_night * nights);
            }

            // Display names: use user selection if different, otherwise plan's original
            const displayTransportMode = selectedTransport?.mode ?? opt.transport_mode;
            const displayTransportName = selectedTransport
              ? `${selectedTransport.airline_or_operator}${selectedTransport.class_type ? ' — ' + selectedTransport.class_type : ''}`
              : opt.transport_name;
            const displayHotelName = selectedHotel?.name ?? opt.hotel_name;

            return (
            <div
              key={opt.id}
              className="bg-slate-50 rounded-lg p-3 mb-2 hover:bg-slate-100 cursor-pointer transition border border-transparent hover:border-ocean/30"
              onClick={() => handlePlanSelect(opt.id)}
            >
              <div className="flex justify-between items-start">
                <div className="flex items-center gap-2">
                  <span className="w-6 h-6 rounded-full bg-ocean/10 text-ocean text-xs font-bold flex items-center justify-center">
                    {String.fromCharCode(65 + idx)}
                  </span>
                  <h5 className="font-medium text-slate-800">{opt.label}</h5>
                </div>
                <span className="text-sm font-bold text-sunset">
                  {formatCurrency(adjustedTotal, opt.currency)}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1 ml-8">{opt.trade_offs}</p>
              {/* Transport & Hotel badges */}
              {(displayTransportMode || displayHotelName || opt.airport_transfer) && (
                <div className="flex flex-wrap gap-2 mt-2 ml-8">
                  {displayTransportMode && (
                    <span className="inline-flex items-center gap-1 text-[10px] bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full font-medium">
                      {displayTransportMode === 'train' ? <Train className="w-3 h-3" /> : displayTransportMode === 'bus' ? <Bus className="w-3 h-3" /> : <Plane className="w-3 h-3" />}
                      {displayTransportName || displayTransportMode}
                    </span>
                  )}
                  {opt.airport_transfer && (
                    <span className="inline-flex items-center gap-1 text-[10px] bg-purple-50 text-purple-700 px-2 py-0.5 rounded-full font-medium">
                      <Bus className="w-3 h-3" />
                      {opt.airport_transfer}
                    </span>
                  )}
                  {displayHotelName && (
                    <span className="inline-flex items-center gap-1 text-[10px] bg-amber-50 text-amber-700 px-2 py-0.5 rounded-full font-medium">
                      <Hotel className="w-3 h-3" />
                      {displayHotelName}
                    </span>
                  )}
                </div>
              )}
              {opt.highlights && opt.highlights.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2 ml-8">
                  {opt.highlights.map((h, i) => (
                    <span key={i} className="text-[10px] bg-emerald-50 text-emerald-600 px-2 py-0.5 rounded-full">
                      {h}
                    </span>
                  ))}
                </div>
              )}
              {opt.is_recommended && (
                <span className="inline-block mt-2 ml-8 text-[10px] bg-forest/10 text-forest px-2 py-0.5 rounded-full font-medium">
                  ✅ Recommended
                </span>
              )}
            </div>
            );
          })}

          {checkpoint.research_summary && (
            <p className="text-[11px] text-slate-400 mt-2 text-center">
              Based on {checkpoint.research_summary.flights_found || 0} flights
              {(checkpoint.research_summary.trains_found ?? 0) > 0 && `, ${checkpoint.research_summary.trains_found} trains`}
              {(checkpoint.research_summary.buses_found ?? 0) > 0 && `, ${checkpoint.research_summary.buses_found} buses`}
              , {checkpoint.research_summary.hotels_found} hotels, {checkpoint.research_summary.activities_found} activities found
            </p>
          )}
        </div>
      )}

      {/* Legacy: Research review (kept for backward compat) */}
      {type === 'research_review' && (
        <div>
          <h4 className="font-semibold text-slate-800 mb-2">Research Complete</h4>
          {checkpoint.research_summary && (
            <div className="grid grid-cols-3 gap-2 mb-3">
              <div className="bg-slate-50 rounded-lg p-2 text-center">
                <div className="text-lg font-bold text-ocean">
                  {(checkpoint.research_summary.flights_found || 0) + (checkpoint.research_summary.trains_found || 0) + (checkpoint.research_summary.buses_found || 0)}
                </div>
                <div className="text-xs text-slate-500">Transport</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-2 text-center">
                <div className="text-lg font-bold text-ocean">{checkpoint.research_summary.hotels_found}</div>
                <div className="text-xs text-slate-500">Hotels</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-2 text-center">
                <div className="text-lg font-bold text-ocean">{checkpoint.research_summary.activities_found}</div>
                <div className="text-xs text-slate-500">Activities</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Checkpoint 2: Budget Allocation Approval */}
      {type === 'budget_review' && (
        <div>
          <h4 className="font-semibold text-slate-800 mb-3 text-base">Budget Allocation Approval</h4>
          {checkpoint.budget_breakdown && (
            <div className="space-y-1.5 mb-3">
              {[
                { label: 'Transport', value: checkpoint.budget_breakdown.transport },
                { label: 'Accommodation', value: checkpoint.budget_breakdown.accommodation },
                { label: 'Food', value: checkpoint.budget_breakdown.food },
                { label: 'Activities', value: checkpoint.budget_breakdown.activities },
                { label: 'Buffer', value: checkpoint.budget_breakdown.buffer },
              ].map(({ label, value }) => (
                <div key={label} className="flex justify-between items-center bg-slate-50 rounded-lg px-3 py-2">
                  <span className="text-sm text-slate-600">{label}</span>
                  <span className="text-sm font-semibold text-slate-800">
                    {formatCurrency(value ?? 0, checkpoint.budget_breakdown!.currency)}
                  </span>
                </div>
              ))}
              <div className="flex justify-between items-center bg-ocean/5 rounded-lg px-3 py-2 border border-ocean/20">
                <span className="text-sm font-semibold text-ocean">Projected Total</span>
                <span className="text-sm font-bold text-ocean">
                  {formatCurrency(checkpoint.budget_breakdown.total ?? 0, checkpoint.budget_breakdown.currency)}
                </span>
              </div>
              {checkpoint.budget_breakdown.traveler_count && checkpoint.budget_breakdown.traveler_count > 1 && (
                <div className="flex justify-between items-center bg-slate-50 rounded-lg px-3 py-1.5 mt-1">
                  <span className="text-xs text-slate-500">
                    👥 Per person ({checkpoint.budget_breakdown.traveler_count} travelers)
                  </span>
                  <span className="text-xs font-semibold text-slate-600">
                    {formatCurrency(
                      checkpoint.budget_breakdown.per_person_total
                        ?? Math.round((checkpoint.budget_breakdown.total ?? 0) / checkpoint.budget_breakdown.traveler_count),
                      checkpoint.budget_breakdown.currency
                    )}
                  </span>
                </div>
              )}
            </div>
          )}
          <p className="text-sm text-slate-500 mb-1">
            Approve the budget allocation or request changes.
          </p>
        </div>
      )}

      {/* Legacy: Plan review */}
      {type === 'plan_review' && (
        <div>
          <h4 className="font-semibold text-slate-800 mb-2">Choose Your Plan</h4>
          {checkpoint.plan_options?.map((opt) => (
            <div
              key={opt.id}
              className="bg-slate-50 rounded-lg p-3 mb-2 hover:bg-slate-100 cursor-pointer transition"
              onClick={() => onAction(`select_plan:${opt.id}`)}
            >
              <div className="flex justify-between items-start">
                <h5 className="font-medium text-slate-800">{opt.label}</h5>
                <span className="text-sm font-bold text-sunset">
                  {formatCurrency(opt.estimated_total ?? 0, opt.currency)}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">{opt.trade_offs}</p>
              {opt.highlights && opt.highlights.length > 0 && (
                <ul className="mt-2 space-y-0.5">
                  {opt.highlights.map((h, i) => (
                    <li key={i} className="text-xs text-slate-600 flex items-center gap-1">
                      <span className="w-1 h-1 bg-ocean rounded-full" /> {h}
                    </li>
                  ))}
                </ul>
              )}
              {opt.is_recommended && (
                <span className="inline-block mt-2 text-[10px] bg-forest/10 text-forest px-2 py-0.5 rounded-full font-medium">Recommended</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Checkpoint 3: Booking Cart Confirmation */}
      {type === 'final_review' && (
        <div>
          <h4 className="font-semibold text-slate-800 mb-3 text-base">Booking Cart Confirmation</h4>

          {/* Price changes warning */}
          {checkpoint.price_changes && checkpoint.price_changes.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-3">
              <div className="flex items-center gap-1.5 mb-1">
                <AlertTriangle className="w-4 h-4 text-amber-600" />
                <p className="text-sm font-medium text-amber-800">Price Changes Detected</p>
              </div>
              {checkpoint.price_changes.map((pc, i) => (
                <div key={i} className="text-xs text-amber-700">
                  {pc.item}: {formatCurrency(pc.old_price)} → <span className="font-semibold">{formatCurrency(pc.new_price)}</span>
                </div>
              ))}
            </div>
          )}

          {/* Booking options */}
          {checkpoint.booking_options && checkpoint.booking_options.length > 0 ? (
            <div className="space-y-3 mb-3">
              {/* Travel options */}
              {checkpoint.booking_options.filter(b => b.category === 'travel').map((opt, i) => (
                <BookingCard key={`travel-${i}`} option={opt} emoji="🚆" sectionTitle="Travel Option" />
              ))}

              {/* Stay options */}
              {checkpoint.booking_options.filter(b => b.category === 'stay').map((opt, i) => (
                <BookingCard key={`stay-${i}`} option={opt} emoji="🏨" sectionTitle="Stay Option" />
              ))}

              {/* Activity options */}
              {(() => {
                const activities = checkpoint.booking_options.filter(b => b.category === 'activity');
                if (activities.length === 0) return null;
                return (
                  <div className="bg-gradient-to-br from-purple-50/50 to-slate-50 rounded-lg border border-slate-100 p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-base">🛶</span>
                      <h5 className="text-xs font-semibold uppercase tracking-wider text-purple-700">Activities</h5>
                    </div>
                    <div className="space-y-2">
                      {activities.map((opt, i) => (
                        <div key={`act-${i}`} className="flex items-start justify-between">
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-slate-800">{opt.name}</p>
                            {opt.details.filter(d => d).slice(0, 1).map((d, j) => (
                              <p key={j} className="text-xs text-slate-500 mt-0.5">{d}</p>
                            ))}
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                            <span className="text-sm font-semibold text-slate-800">
                              {formatCurrency(opt.cost, opt.currency)}
                            </span>
                            {(opt.booking_url || opt.place_id) && (
                              <a
                                href={opt.booking_url || `https://www.google.com/maps/place/?q=place_id:${opt.place_id}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-ocean hover:text-cyan-700 transition"
                                title="Book"
                              >
                                <ExternalLink className="w-3.5 h-3.5" />
                              </a>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}

              {/* Booking total */}
              {checkpoint.booking_total != null && (
                <div className="flex justify-between items-center bg-ocean/5 rounded-lg px-3 py-2.5 border border-ocean/20">
                  <span className="text-sm font-semibold text-ocean">Booking Total</span>
                  <span className="text-sm font-bold text-ocean">
                    {formatCurrency(checkpoint.booking_total, checkpoint.budget_breakdown?.currency)}
                  </span>
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-slate-500 mb-3">
              Everything looks good. Confirm to finalize your trip package.
            </p>
          )}
        </div>
      )}

      {/* Action buttons — only show if no plan selection is the primary action */}
      {type !== 'plan_direction' && type !== 'plan_review' && (
        <div className="flex gap-2 mt-3">
          {(() => {
            const approveOpt = checkpoint.options.find(o =>
              o === 'approve_and_continue' || o === 'confirm_and_book'
            );
            return approveOpt ? (
              <button
                onClick={() => onAction(approveOpt)}
                className="flex items-center gap-1.5 px-4 py-2 bg-forest text-white rounded-lg text-sm font-medium hover:bg-green-700 transition"
              >
                <CheckCircle className="w-4 h-4" />
                {approveOpt === 'confirm_and_book' ? 'Confirm & Book' : 'Approve'}
              </button>
            ) : null;
          })()}
          {checkpoint.options.includes('request_changes') && (
            <button
              onClick={() => onAction('request_changes')}
              className="flex items-center gap-1.5 px-4 py-2 bg-slate-100 text-slate-600 rounded-lg text-sm font-medium hover:bg-slate-200 transition"
            >
              <RotateCcw className="w-4 h-4" /> Request Changes
            </button>
          )}
          {checkpoint.options.includes('cancel') && (
            <button
              onClick={() => onAction('cancel')}
              className="flex items-center gap-1.5 px-3 py-2 text-red-500 rounded-lg text-sm hover:bg-red-50 transition"
            >
              <XCircle className="w-4 h-4" /> Cancel
            </button>
          )}
        </div>
      )}

      {/* For plan_direction: show select hint + cancel */}
      {(type === 'plan_direction' || type === 'plan_review') && (
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-slate-400 italic">Click a plan above to select it</p>
          <div className="flex gap-2">
            {checkpoint.options.includes('request_changes') && (
              <button
                onClick={() => onAction('request_changes')}
                className="flex items-center gap-1 px-3 py-1.5 bg-slate-100 text-slate-600 rounded-lg text-xs font-medium hover:bg-slate-200 transition"
              >
                <RotateCcw className="w-3.5 h-3.5" /> Changes
              </button>
            )}
            {checkpoint.options.includes('cancel') && (
              <button
                onClick={() => onAction('cancel')}
                className="flex items-center gap-1 px-3 py-1.5 text-red-500 rounded-lg text-xs hover:bg-red-50 transition"
              >
                <XCircle className="w-3.5 h-3.5" /> Cancel
              </button>
            )}
          </div>
        </div>
      )}
    </motion.div>
  );
}
