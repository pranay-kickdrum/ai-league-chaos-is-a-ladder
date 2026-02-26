import { Loader2 } from 'lucide-react';
import { motion } from 'framer-motion';

interface LoadingStatesProps {
  message?: string;
  detail?: string;
}

export default function LoadingStates({ message = 'Working on it...', detail }: LoadingStatesProps) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col items-center justify-center py-12 gap-3"
    >
      <Loader2 className="w-8 h-8 text-ocean animate-spin" />
      <p className="text-slate-700 font-medium">{message}</p>
      {detail && <p className="text-slate-400 text-sm">{detail}</p>}
    </motion.div>
  );
}
