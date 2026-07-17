export default function Tabs({ tabs, active, onChange }) {
  return (
    <div className="flex flex-wrap gap-2 border-b border-slate-200">
      {tabs.map((tab) => (
        <button
          key={tab}
          onClick={() => onChange(tab)}
          className={`border-b-2 px-4 py-3 text-sm font-bold transition ${
            active === tab
              ? 'border-[#003A8C] text-[#003A8C]'
              : 'border-transparent text-slate-500 hover:text-slate-900'
          }`}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}
