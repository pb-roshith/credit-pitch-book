import { Activity, BookOpen, Factory, FileText, LayoutDashboard, LogOut, PlusCircle, UserCircle } from 'lucide-react';
import { Link, NavLink } from 'react-router-dom';

const navClass = ({ isActive }) =>
  `inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition ${
    isActive ? 'bg-[#003A8C] text-white' : 'text-slate-700 hover:bg-slate-100'
  }`;

export default function Navbar({ user, onLogout }) {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-[1480px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-center gap-3">
          <Link to="/" className="flex items-center gap-2 text-lg font-bold text-[#003A8C]">
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-[#003A8C] text-white">
              <BookOpen size={20} />
            </span>
            Credit Pitch Book
          </Link>
          <nav className="flex items-center gap-1">
            <NavLink to="/" className={navClass}>
              <LayoutDashboard size={17} />
              Dashboard
            </NavLink>
            <NavLink to="/new-deal" className={navClass}>
              <PlusCircle size={17} />
              New Deal
            </NavLink>
            <NavLink to="/manufacture-data" className={navClass}>
              <Factory size={17} />
              Manufacture Data
            </NavLink>
            <NavLink to="/observability" className={navClass}>
              <Activity size={17} />
              Observability
            </NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 font-semibold text-slate-700">
            <UserCircle size={16} />
            {user.username}
          </span>
          <span className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 font-semibold text-slate-700">
            <FileText size={16} />
            Credit Dossier
          </span>
          <span className="rounded-lg bg-slate-100 px-3 py-2 font-semibold text-slate-500">Pipeline v1.0</span>
          <button
            onClick={onLogout}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 font-bold text-slate-700"
          >
            <LogOut size={16} />
            Logout
          </button>
        </div>
      </div>
    </header>
  );
}
