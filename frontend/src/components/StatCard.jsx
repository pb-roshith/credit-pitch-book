export default function StatCard({ icon: Icon, label, metric, tone = 'blue' }) {
  const colors = {
    blue: 'bg-blue-50 text-[#003A8C]',
    amber: 'bg-amber-50 text-amber-700',
    emerald: 'bg-emerald-50 text-emerald-700',
    slate: 'bg-slate-100 text-slate-700',
  };

  return (
    <article className="rounded-lg bg-white p-5 shadow-enterprise">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">{label}</p>
          <p className="mt-3 text-3xl font-bold text-slate-900">{metric}</p>
        </div>
        <span className={`grid h-11 w-11 place-items-center rounded-lg ${colors[tone]}`}>
          <Icon size={22} />
        </span>
      </div>
    </article>
  );
}
