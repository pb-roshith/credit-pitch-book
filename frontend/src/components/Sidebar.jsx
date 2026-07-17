import { Bot, CheckSquare, Sparkles } from 'lucide-react';
import ProgressBar from './ProgressBar.jsx';

const statusClass = {
  Pending: 'bg-slate-100 text-slate-600',
  Drafted: 'bg-blue-100 text-[#003A8C]',
  Reviewing: 'bg-amber-100 text-amber-800',
  Completed: 'bg-emerald-100 text-emerald-800',
};

export default function Sidebar({
  sections,
  selected,
  setSelected,
  checkedSectionNumbers = [],
  onToggleSection,
  onDraftAll,
  onDraftSelected,
  bulkGenerating = false,
}) {
  const draftedCount = sections.filter((section) => section.status === 'Drafted').length;
  const progress = sections.length ? Math.round((draftedCount / sections.length) * 100) : 0;
  const selectedCount = checkedSectionNumbers.length;

  return (
    <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
      <div className="rounded-lg bg-white p-5 shadow-enterprise">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-blue-50 text-[#003A8C]">
            <Bot size={20} />
          </span>
          <div>
            <p className="font-bold text-slate-900">Progress: {draftedCount}/{sections.length} Sections</p>
            <p className="text-sm text-slate-500">{progress}%</p>
          </div>
        </div>
        <div className="mt-4">
          <ProgressBar value={progress} label="" showValue={false} />
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2">
          <button
            onClick={onDraftAll}
            disabled={bulkGenerating || sections.length === 0}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#003A8C] px-3 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Sparkles size={16} />
            {bulkGenerating ? 'Drafting...' : 'Draft All'}
          </button>
          <button
            onClick={onDraftSelected}
            disabled={bulkGenerating || selectedCount === 0}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <CheckSquare size={16} />
            Draft Selected
          </button>
        </div>
        <p className="mt-3 text-xs font-semibold text-slate-500">{selectedCount} selected for Draft Selected</p>
      </div>

      <div className="rounded-lg bg-white shadow-enterprise">
        <div className="border-b border-slate-200 px-4 py-3">
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate-600">Sections</h2>
        </div>
        <div className="max-h-[680px] overflow-auto p-2 scrollbar-thin">
          {sections.map((section) => {
            const active = selected?.number === section.number;
            const checked = checkedSectionNumbers.includes(section.sectionNumber);
            return (
              <button
                key={section.number}
                onClick={() => setSelected(section)}
                className={`mb-1 grid w-full grid-cols-[24px_34px_1fr] items-center gap-2 rounded-lg px-2 py-2 text-left text-sm ${
                  active ? 'bg-blue-50 ring-1 ring-blue-200' : 'hover:bg-slate-50'
                }`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  className="h-4 w-4 accent-[#003A8C]"
                  onClick={(event) => event.stopPropagation()}
                  onChange={() => onToggleSection(section.sectionNumber)}
                />
                <span className="font-bold text-slate-500">{section.number}</span>
                <span className="min-w-0">
                  <span className="block truncate font-semibold text-slate-800">{section.name}</span>
                  <span className={`mt-1 inline-block rounded-full px-2 py-0.5 text-[11px] font-bold ${statusClass[section.status]}`}>
                    {section.status}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </aside>
  );
}
