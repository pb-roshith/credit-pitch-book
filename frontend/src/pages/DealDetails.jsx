import { ArrowLeft, Download, FileText, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import ProgressBar from '../components/ProgressBar.jsx';
import SectionCard from '../components/SectionCard.jsx';
import Tabs from '../components/Tabs.jsx';
import {
  deleteDeal,
  downloadNarrativeExportVersion,
  exportNarrativeDrafts,
  fetchDeal,
  fetchNarrativeExportVersions,
} from '../services/api.js';
import { formatMoney } from '../utils/format.js';

export default function DealDetails() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [deal, setDeal] = useState(null);
  const [exportVersions, setExportVersions] = useState([]);
  const [activeTab, setActiveTab] = useState('Overview');
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([fetchDeal(id), fetchNarrativeExportVersions(id)])
      .then(([dealData, exportData]) => {
        setDeal(dealData);
        setExportVersions(exportData);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  const refreshExportVersions = async () => {
    const exportData = await fetchNarrativeExportVersions(id);
    setExportVersions(exportData);
  };

  const removeDeal = async () => {
    try {
      await deleteDeal(id);
      navigate('/');
    } catch (err) {
      setError(err.message);
    }
  };

  const downloadLatestDraft = async () => {
    if (exporting) {
      return;
    }

    setExporting(true);
    setError('');

    try {
      const blob = await exportNarrativeDrafts(id, { selectedDraftIds: {} });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      const safeName = (deal?.customer || 'credit_pitch_book').replace(/[^a-z0-9_-]+/gi, '_');
      link.href = url;
      link.download = `${safeName}_narrative_draft.docx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      await refreshExportVersions();
    } catch (err) {
      setError(err.message);
    } finally {
      setExporting(false);
    }
  };

  const downloadExportVersion = async (version) => {
    if (exporting) {
      return;
    }

    setExporting(true);
    setError('');

    try {
      const blob = await downloadNarrativeExportVersion(id, version.exportId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = version.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message);
    } finally {
      setExporting(false);
    }
  };

  if (loading) {
    return <div className="rounded-lg bg-white p-8 text-center font-semibold text-slate-500 shadow-enterprise">Loading deal...</div>;
  }

  if (error || !deal) {
    return (
      <div className="space-y-4">
        <Link to="/" className="inline-flex items-center gap-2 text-sm font-bold text-[#003A8C] hover:underline">
          <ArrowLeft size={17} />
          Dashboard
        </Link>
        <div className="rounded-lg bg-red-50 p-5 font-semibold text-red-700">{error || 'Deal not found.'}</div>
      </div>
    );
  }

  const snapshot = [
    ['Segment', deal.segment],
    ['Industry', deal.industry],
    ['Geography', deal.geography],
    ['KYC', deal.kycStatus],
    ['Facility', deal.facility],
    ['Amount', formatMoney(deal.currency, deal.amount)],
    ['Tenure', deal.tenure],
    ['Pricing', deal.pricing],
    ['Collateral', deal.collateral],
  ];
  const activity = deal.activity || [];
  const readiness = [
    { label: 'Mandatory sections ready', value: deal.progress || 0 },
    { label: 'Library documents', value: 0 },
    { label: 'Financial analysis', value: 0 },
    { label: 'Risk assessment', value: 0 },
    { label: 'Approval readiness', value: deal.progress || 0 },
  ];

  return (
    <div className="space-y-5">
      <Link to="/" className="inline-flex items-center gap-2 text-sm font-bold text-[#003A8C] hover:underline">
        <ArrowLeft size={17} />
        Dashboard
      </Link>

      <div className="rounded-lg bg-white p-5 shadow-enterprise">
        <div className="flex flex-col justify-between gap-5 lg:flex-row">
          <div>
            <div className="flex flex-wrap gap-2">
              {[deal.customerType, deal.facility, `Due ${deal.due}`].map((badge) => (
                <span key={badge} className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-[#003A8C]">
                  {badge}
                </span>
              ))}
            </div>
            <h1 className="mt-4 text-3xl font-bold text-slate-950">{deal.customer}</h1>
            <p className="mt-2 text-slate-600">
              {deal.industry} / {deal.geography}
            </p>
          </div>
          <div className="min-w-[280px] rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Facility</p>
            <p className="mt-2 text-2xl font-bold text-slate-950">{formatMoney(deal.currency, deal.amount)}</p>
            <p className="mt-1 text-sm font-semibold text-slate-600">
              {deal.tenure} / {deal.pricing}
            </p>
            <button
              onClick={removeDeal}
              className="mt-4 inline-flex items-center gap-2 rounded-lg bg-red-700 px-3 py-2 text-sm font-bold text-white"
            >
              <Trash2 size={16} />
              Delete Deal
            </button>
          </div>
        </div>
      </div>

      <div className="rounded-lg bg-white shadow-enterprise">
        <Tabs tabs={['Overview', 'Narratives', 'Versions', 'Export']} active={activeTab} onChange={setActiveTab} />
        <div className="p-5">
          {activeTab === 'Overview' && (
            <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
              <div className="space-y-5">
                <SectionCard title="Client & Facility Snapshot">
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {snapshot.map(([label, value]) => (
                      <div key={label} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                        <p className="text-xs font-bold uppercase tracking-wide text-slate-500">{label}</p>
                        <p className="mt-2 font-bold text-slate-900">{value}</p>
                      </div>
                    ))}
                  </div>
                </SectionCard>

                <SectionCard title="Recent Activity">
                  {activity.length === 0 ? (
                    <p className="text-sm font-medium text-slate-500">No activity has been recorded for this deal yet.</p>
                  ) : (
                    <div className="space-y-4">
                      {activity.map((item) => (
                        <div key={`${item.event}-${item.time}`} className="flex gap-3">
                          <span className="mt-1 h-3 w-3 rounded-full bg-[#003A8C]" />
                          <div>
                            <p className="font-bold text-slate-900">{item.event}</p>
                            <p className="text-sm text-slate-500">
                              {item.user} / {item.date} / {item.time}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </SectionCard>
              </div>

              <SectionCard title="Readiness" className="self-start">
                <div className="space-y-5">
                  {readiness.map((item) => (
                    <ProgressBar key={item.label} label={item.label} value={Math.max(0, item.value)} />
                  ))}
                </div>
              </SectionCard>
            </div>
          )}

          {activeTab === 'Narratives' && (
            <div className="rounded-lg border border-blue-100 bg-blue-50 p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="font-bold text-slate-950">Narratives Workspace</h2>
                  <p className="mt-1 text-sm text-slate-600">Draft, review, and export all credit narrative sections.</p>
                </div>
                <Link
                  to={`/deals/${deal.id}/narratives`}
                  className="inline-flex items-center gap-2 rounded-lg bg-[#003A8C] px-4 py-2.5 text-sm font-bold text-white"
                >
                  <FileText size={17} />
                  Open Workspace
                </Link>
              </div>
            </div>
          )}

          {activeTab === 'Versions' && (
            <div className="space-y-3">
              {exportVersions.length === 0 ? (
                <div className="rounded-lg border border-slate-200 p-5 text-sm text-slate-600">
                  No downloaded draft versions have been created for this deal yet.
                </div>
              ) : (
                exportVersions.map((version) => (
                  <div
                    key={version.exportId}
                    className="flex items-center gap-4 rounded-lg border border-slate-200 bg-white p-4 shadow-enterprise"
                  >
                    <button
                      onClick={() => downloadExportVersion(version)}
                      disabled={exporting}
                      className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-blue-50 text-[#003A8C] disabled:cursor-not-allowed disabled:opacity-60"
                      title="Download this version"
                    >
                      <Download size={18} />
                    </button>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-bold text-slate-900">
                        Version #{version.exportId} / {version.filename}
                      </p>
                      <p className="mt-1 text-xs font-semibold text-slate-500">
                        {version.sectionCount} sections / {new Date(version.createdAt).toLocaleString()}
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'Export' && (
            <div className="rounded-lg border border-blue-100 bg-blue-50 p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="font-bold text-slate-950">Download Draft Document</h2>
                  <p className="mt-1 text-sm text-slate-600">
                    Downloads the latest saved draft for each available section as a Word document.
                  </p>
                </div>
                <button
                  onClick={downloadLatestDraft}
                  disabled={exporting}
                  className="inline-flex items-center gap-2 rounded-lg bg-[#003A8C] px-4 py-2.5 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Download size={17} />
                  {exporting ? 'Downloading...' : 'Download Draft'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
