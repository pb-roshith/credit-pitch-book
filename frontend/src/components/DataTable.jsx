import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import ProgressBar from './ProgressBar.jsx';
import { formatMoney } from '../utils/format.js';

const statusStyles = {
  Draft: 'bg-slate-100 text-slate-700',
  'In Review': 'bg-amber-100 text-amber-800',
  'Approved / Exported': 'bg-emerald-100 text-emerald-800',
};

export default function DataTable({ deals }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
        <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wide text-slate-500">
          <tr>
            {['Customer', 'Type', 'Facility', 'Amount', 'Due', 'Status', 'Progress', ''].map((head) => (
              <th key={head} className="px-4 py-3">
                {head}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {deals.length === 0 ? (
            <tr>
              <td colSpan="8" className="px-4 py-12 text-center font-medium text-slate-500">
                No deals match your filters.
              </td>
            </tr>
          ) : (
            deals.map((deal) => (
              <tr key={deal.id} className="hover:bg-slate-50">
                <td className="px-4 py-4">
                  <Link to={`/deals/${deal.id}`} className="font-bold text-[#003A8C] hover:underline">
                    {deal.customer}
                  </Link>
                  <div className="text-xs text-slate-500">{deal.geography}</div>
                </td>
                <td className="px-4 py-4 text-slate-700">{deal.customerType}</td>
                <td className="px-4 py-4 text-slate-700">{deal.facility}</td>
                <td className="px-4 py-4 font-semibold text-slate-900">{formatMoney(deal.currency, deal.amount)}</td>
                <td className="px-4 py-4 text-slate-700">{deal.due}</td>
                <td className="px-4 py-4">
                  <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${statusStyles[deal.status]}`}>
                    {deal.status}
                  </span>
                </td>
                <td className="min-w-[150px] px-4 py-4">
                  <ProgressBar value={deal.progress} label="" />
                </td>
                <td className="px-4 py-4 text-right">
                  <Link
                    to={`/deals/${deal.id}`}
                    className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-blue-50 hover:text-[#003A8C]"
                    aria-label={`Open ${deal.customer}`}
                  >
                    <ChevronRight size={18} />
                  </Link>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
