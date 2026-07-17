import { ClipboardCheck, FileClock, FileText, Plus, Search, Send } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import DataTable from '../components/DataTable.jsx';
import SectionCard from '../components/SectionCard.jsx';
import StatCard from '../components/StatCard.jsx';
import { fetchDeals } from '../services/api.js';

export default function Dashboard() {
  const [deals, setDeals] = useState([]);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('All');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchDeals()
      .then(setDeals)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const filteredDeals = useMemo(() => {
    return deals.filter((deal) => {
      const matchesQuery = [deal.customer, deal.facility, deal.industry, deal.geography]
        .join(' ')
        .toLowerCase()
        .includes(query.toLowerCase());
      const matchesStatus = status === 'All' || deal.status === status;
      return matchesQuery && matchesStatus;
    });
  }, [deals, query, status]);

  const stats = [
    { label: 'Total Deals', metric: deals.length, icon: FileText, tone: 'blue' },
    { label: 'Active Drafts', metric: deals.filter((deal) => deal.status === 'Draft').length, icon: FileClock, tone: 'slate' },
    { label: 'In Review', metric: deals.filter((deal) => deal.status === 'In Review').length, icon: Send, tone: 'amber' },
    {
      label: 'Approved / Exported',
      metric: deals.filter((deal) => deal.status === 'Approved / Exported').length,
      icon: ClipboardCheck,
      tone: 'emerald',
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-950">Credit Pitch Book Pipeline</h1>
          <p className="mt-2 text-slate-600">Initiate, draft, review, and export pitch books with full traceability.</p>
        </div>
        <Link
          to="/new-deal"
          className="inline-flex items-center gap-2 rounded-lg bg-[#003A8C] px-4 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-[#002f70]"
        >
          <Plus size={18} />
          New Deal
        </Link>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map((stat) => (
          <StatCard key={stat.label} {...stat} />
        ))}
      </div>

      <SectionCard
        title="Deal Pipeline"
        action={
          <span className="rounded-full bg-white/15 px-3 py-1 text-xs font-bold">{filteredDeals.length} visible</span>
        }
      >
        <div className="mb-5 flex flex-col gap-3 lg:flex-row">
          <label className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="w-full rounded-lg border border-slate-300 bg-white py-2.5 pl-10 pr-3 text-sm outline-none focus:border-[#003A8C] focus:ring-2 focus:ring-blue-100"
              placeholder="Search customer, facility, geography..."
            />
          </label>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm font-semibold text-slate-700 outline-none focus:border-[#003A8C] focus:ring-2 focus:ring-blue-100"
          >
            {['All', 'Draft', 'In Review', 'Approved / Exported'].map((option) => (
              <option key={option}>{option}</option>
            ))}
          </select>
        </div>
        {error && <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div>}
        {loading ? (
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-12 text-center font-medium text-slate-500">
            Loading deal pipeline...
          </div>
        ) : (
          <DataTable deals={filteredDeals} />
        )}
      </SectionCard>
    </div>
  );
}
