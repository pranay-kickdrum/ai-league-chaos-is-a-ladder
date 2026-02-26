import { AlertTriangle, RefreshCw, SkipForward, ArrowLeft } from 'lucide-react';

interface ErrorRecoveryProps {
  message: string;
  onRetry?: () => void;
  onSkip?: () => void;
  onGoBack?: () => void;
}

export default function ErrorRecovery({ message, onRetry, onSkip, onGoBack }: ErrorRecoveryProps) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-xl p-5 my-3">
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-red-500 mt-0.5 shrink-0" />
        <div className="flex-1">
          <p className="text-red-800 font-medium text-sm">{message}</p>
          <div className="flex gap-2 mt-3">
            {onRetry && (
              <button
                onClick={onRetry}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-red-100 text-red-700 rounded-lg text-xs font-medium hover:bg-red-200 transition"
              >
                <RefreshCw className="w-3.5 h-3.5" /> Retry
              </button>
            )}
            {onSkip && (
              <button
                onClick={onSkip}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-600 rounded-lg text-xs font-medium hover:bg-slate-200 transition"
              >
                <SkipForward className="w-3.5 h-3.5" /> Skip
              </button>
            )}
            {onGoBack && (
              <button
                onClick={onGoBack}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-600 rounded-lg text-xs font-medium hover:bg-slate-200 transition"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Go Back
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
