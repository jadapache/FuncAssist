export const StatusPill = ({ connected }: { connected: boolean }) => (
  <span
    className={[
      'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold',
      connected
        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
        : 'bg-slate-100 text-slate-600 border border-slate-200',
    ].join(' ')}
  >
    <span
      className={['h-2 w-2 rounded-full', connected ? 'bg-emerald-500 animate-pulse-soft' : 'bg-slate-400'].join(' ')}
      aria-hidden
    />
    {connected ? 'Conectado' : 'No conectado'}
  </span>
)
