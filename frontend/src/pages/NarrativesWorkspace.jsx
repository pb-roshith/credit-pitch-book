import { ArrowLeft, Download } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import NarrativeEditor from '../components/NarrativeEditor.jsx';
import Sidebar from '../components/Sidebar.jsx';
import { exportNarrativeDrafts, fetchDeal, fetchNarrativeSections, generateNarratives } from '../services/api.js';
import { formatMoney } from '../utils/format.js';

function getCurrentUser() {
  const saved = localStorage.getItem('creditPitchUser');
  return saved ? JSON.parse(saved) : null;
}

export default function NarrativesWorkspace() {
  const { id } = useParams();
  const [deal, setDeal] = useState(null);
  const [sections, setSections] = useState([]);
  const [selected, setSelected] = useState(null);
  const [checkedSectionNumbers, setCheckedSectionNumbers] = useState([]);
  const [selectedDraftIds, setSelectedDraftIds] = useState({});
  const [bulkGenerating, setBulkGenerating] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([fetchDeal(id), fetchNarrativeSections()])
      .then(([dealData, sectionData]) => {
        setDeal(dealData);
        setSections(sectionData);
        setSelected(sectionData[0] || null);
        setCheckedSectionNumbers([]);
        setSelectedDraftIds({});
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return <div className="rounded-lg bg-white p-8 text-center font-semibold text-slate-500 shadow-enterprise">Loading workspace...</div>;
  }

  if (error || !deal) {
    return <div className="rounded-lg bg-red-50 p-5 font-semibold text-red-700">{error || 'Deal not found.'}</div>;
  }

  const toggleCheckedSection = (sectionNumber) => {
    setCheckedSectionNumbers((current) =>
      current.includes(sectionNumber)
        ? current.filter((value) => value !== sectionNumber)
        : [...current, sectionNumber].sort((left, right) => left - right),
    );
  };

  const markDraftedSections = (results) => {
    const draftedNumbers = new Set(results.filter((result) => result.status === 'drafted').map((result) => result.sectionNumber));
    if (draftedNumbers.size === 0) {
      return;
    }

    setSections((current) =>
      current.map((section) =>
        draftedNumbers.has(section.sectionNumber)
          ? { ...section, status: 'Drafted' }
          : section,
      ),
    );
  };

  const runBulkDraft = async (sectionNumbers = []) => {
    if (bulkGenerating) {
      return;
    }

    setBulkGenerating(true);
    setBulkResult(null);
    setError('');

    try {
      const currentUser = getCurrentUser();
      const result = await generateNarratives(deal.id, {
        sectionNumbers,
        username: currentUser?.username || '',
      });
      setBulkResult(result);
      markDraftedSections(result.results || []);
    } catch (err) {
      if (err.detail?.code === 'moderation_failed') {
        setError(err.message);
      } else {
        setError(err.message);
      }
    } finally {
      setBulkGenerating(false);
    }
  };

  const markDraftForDownload = (sectionNumber, draftId) => {
    setSelectedDraftIds((current) => ({
      ...current,
      [sectionNumber]: draftId,
    }));
  };

  const downloadDraft = async () => {
    if (exporting) {
      return;
    }

    setExporting(true);
    setError('');

    try {
      const blob = await exportNarrativeDrafts(deal.id, {
        selectedDraftIds,
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      const safeName = deal.customer.replace(/[^a-z0-9_-]+/gi, '_') || 'credit_pitch_book';
      link.href = url;
      link.download = `${safeName}_narrative_draft.docx`;
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

  return (
    <div className="space-y-5">
      <Link to={`/deals/${deal.id}`} className="inline-flex items-center gap-2 text-sm font-bold text-[#003A8C] hover:underline">
        <ArrowLeft size={17} />
        Dashboard
      </Link>

      <div className="rounded-lg bg-white p-5 shadow-enterprise">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap gap-2">
              <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-[#003A8C]">{deal.customerType}</span>
              <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-[#003A8C]">{deal.facility}</span>
              <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-[#003A8C]">Due {deal.due}</span>
            </div>
            <h1 className="mt-3 text-2xl font-bold text-slate-950">{deal.customer}</h1>
            <p className="mt-1 text-slate-600">
              {deal.industry} / {deal.geography}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Facility</p>
            <p className="text-xl font-bold text-slate-950">{formatMoney(deal.currency, deal.amount)}</p>
            <p className="text-sm font-semibold text-slate-600">
              {deal.tenure} / {deal.pricing}
            </p>
            <button
              onClick={downloadDraft}
              disabled={exporting}
              className="mt-4 inline-flex items-center gap-2 rounded-lg bg-[#003A8C] px-4 py-2.5 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Download size={16} />
              {exporting ? 'Downloading...' : 'Download Draft'}
            </button>
          </div>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(280px,25%)_1fr]">
        <Sidebar
          sections={sections}
          selected={selected}
          setSelected={setSelected}
          checkedSectionNumbers={checkedSectionNumbers}
          onToggleSection={toggleCheckedSection}
          onDraftAll={() => runBulkDraft([])}
          onDraftSelected={() => runBulkDraft(checkedSectionNumbers)}
          bulkGenerating={bulkGenerating}
        />
        {selected ? (
          <div className="space-y-4">
            {bulkResult && (
              <div className="rounded-lg border border-blue-100 bg-white p-4 shadow-enterprise">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm font-bold text-slate-800">
                    Bulk draft completed: {bulkResult.draftedCount} drafted, {bulkResult.errorCount} failed
                  </p>
                  <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-[#003A8C]">
                    {bulkResult.requestedCount} requested
                  </span>
                </div>
                {bulkResult.errorCount > 0 && (
                  <div className="mt-3 space-y-2">
                    {bulkResult.results
                      .filter((result) => result.status === 'error')
                      .map((result) => (
                        <p key={result.sectionNumber} className="text-sm font-semibold text-red-700">
                          Section {String(result.sectionNumber).padStart(2, '0')}: {result.message}
                        </p>
                      ))}
                  </div>
                )}
              </div>
            )}
            <NarrativeEditor
              deal={deal}
              section={selected}
              selectedDraftId={selectedDraftIds[selected.sectionNumber]}
              onSelectDraftForDownload={markDraftForDownload}
            />
          </div>
        ) : (
          <div className="rounded-lg bg-white p-8 text-center font-semibold text-slate-500 shadow-enterprise">
            No narrative sections have been loaded yet.
          </div>
        )}
      </div>
    </div>
  );
}
