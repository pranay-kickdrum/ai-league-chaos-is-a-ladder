import { clsx, type ClassValue } from 'clsx';

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatCurrency(amount: number | undefined | null, currency = 'INR'): string {
  const symbol: Record<string, string> = {
    INR: '₹',
    USD: '$',
    EUR: '€',
    GBP: '£',
    JPY: '¥',
    THB: '฿',
  };
  const s = symbol[currency] ?? currency + ' ';
  const num = amount ?? 0;
  return `${s}${num.toLocaleString()}`;
}

export function formatDate(dateStr: string): string {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function getPhaseLabel(status: string): string {
  const labels: Record<string, string> = {
    collecting_preferences: 'Understanding',
    researching: 'Researching',
    checkpoint_1: 'Review Research',
    planning: 'Planning',
    checkpoint_2: 'Review Plan',
    verifying: 'Verifying',
    checkpoint_3: 'Final Review',
    finalizing: 'Finalizing',
    complete: 'Complete',
    replanning: 'Re-planning',
    error: 'Error',
  };
  return labels[status] ?? status;
}
