import { motion } from 'framer-motion';
import { Clock, MapPin, Star, ExternalLink } from 'lucide-react';
import { formatCurrency } from '../../lib/utils';
import type { Activity } from '../../types';

interface ActivityItemProps {
  activity: Activity;
}

export default function ActivityItem({ activity }: ActivityItemProps) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex gap-3 py-2"
    >
      {/* Time column */}
      <div className="w-16 shrink-0 text-right">
        <span className="text-xs font-mono text-slate-400">{activity.time_slot.start}</span>
      </div>

      {/* Timeline dot */}
      <div className="flex flex-col items-center">
        <div
          className={`w-2.5 h-2.5 rounded-full mt-1 ${
            activity.is_verified ? 'bg-forest' : 'bg-slate-300'
          }`}
        />
        <div className="w-px flex-1 bg-slate-200" />
      </div>

      {/* Content */}
      <div className="flex-1 pb-3">
        <div className="flex items-start justify-between">
          <div>
            <h5 className="text-sm font-medium text-slate-800">{activity.name}</h5>
            {activity.description && (
              <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">{activity.description}</p>
            )}
          </div>
          {activity.cost > 0 && (
            <span className="text-xs font-semibold text-sunset ml-2 whitespace-nowrap">
              {formatCurrency(activity.cost, activity.currency)}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3 mt-1.5 text-xs text-slate-400">
          <span className="flex items-center gap-0.5">
            <Clock className="w-3 h-3" />
            {activity.time_slot.start}–{activity.time_slot.end}
          </span>
          {(activity.address || activity.location) && (
            <span className="flex items-center gap-0.5 truncate max-w-[150px]">
              <MapPin className="w-3 h-3" />
              {activity.address || activity.location}
            </span>
          )}
          {activity.rating && (
            <span className="flex items-center gap-0.5">
              <Star className="w-3 h-3 text-amber-400" />
              {activity.rating}
            </span>
          )}
          {activity.booking_url && (
            <a
              href={activity.booking_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-0.5 text-ocean hover:underline"
            >
              <ExternalLink className="w-3 h-3" /> Book
            </a>
          )}
        </div>

        {!activity.is_verified && (
          <span className="inline-block mt-1 text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">
            Unverified
          </span>
        )}
      </div>
    </motion.div>
  );
}
