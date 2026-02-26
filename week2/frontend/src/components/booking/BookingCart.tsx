import { ExternalLink, ShoppingCart } from 'lucide-react';
import { formatCurrency } from '../../lib/utils';
import type { BookingCart as BookingCartType } from '../../types';

interface BookingCartProps {
  cart: BookingCartType;
}

export default function BookingCart({ cart }: BookingCartProps) {
  if (!cart?.items?.length) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-4 text-center text-slate-400">
        <ShoppingCart className="w-6 h-6 mx-auto mb-1" />
        <p className="text-sm">Booking cart will appear after planning</p>
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-1.5">
        <ShoppingCart className="w-4 h-4" /> Booking Cart
      </h3>

      <div className="space-y-2">
        {cart.items.map((item, i) => (
          <div key={i} className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0">
            <div>
              <p className="text-sm text-slate-700 font-medium">{item.name}</p>
              {item.provider && <p className="text-xs text-slate-400">{item.provider}</p>}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-sunset">
                {formatCurrency(item.cost, item.currency)}
              </span>
              {item.booking_url && (
                <a
                  href={item.booking_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-ocean hover:text-ocean/80"
                >
                  <ExternalLink className="w-4 h-4" />
                </a>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 pt-3 border-t border-slate-200 flex justify-between">
        <span className="text-sm font-semibold text-slate-700">Total</span>
        <span className="text-sm font-bold text-sunset">
          {formatCurrency(cart.total, cart.currency)}
        </span>
      </div>
    </div>
  );
}
