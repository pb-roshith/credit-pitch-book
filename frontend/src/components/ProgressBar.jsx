export default function ProgressBar({ value, label, showValue = true }) {
  return (
    <div className="space-y-2">
      {label && (
        <div className="flex items-center justify-between gap-4 text-sm">
          <span className="font-medium text-slate-700">{label}</span>
          {showValue && <span className="font-semibold text-[#003A8C]">{value}%</span>}
        </div>
      )}
      <div className="h-2.5 overflow-hidden rounded-full bg-slate-200">
        <div className="h-full rounded-full bg-[#003A8C]" style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}
