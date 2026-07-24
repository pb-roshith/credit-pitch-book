import { Factory, Loader2, WandSparkles } from 'lucide-react';
import { useState } from 'react';
import { manufactureData } from '../services/api.js';

export default function ManufactureData() {
  const [form, setForm] = useState({
    clientName: '',
    industry: '',
    geography: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const updateField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError('');
    setResult(null);

    try {
      const response = await manufactureData(form);
      setResult(response);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="rounded-lg bg-white p-5 shadow-enterprise">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-lg bg-[#003A8C] text-white">
            <Factory size={22} />
          </span>
          <div>
            <h1 className="text-2xl font-bold text-slate-950">Manufacture Data</h1>
            <p className="text-sm font-semibold text-slate-500">
              Generate client MCP data, PDFs, Mistral library upload, and Postgres tables.
            </p>
          </div>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="rounded-lg bg-white p-5 shadow-enterprise">
        <div className="grid gap-4 lg:grid-cols-3">
          <label className="block">
            <span className="text-xs font-bold uppercase tracking-wide text-slate-500">Client Name</span>
            <input
              value={form.clientName}
              onChange={(event) => updateField('clientName', event.target.value)}
              className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-[#003A8C] focus:ring-2 focus:ring-blue-100"
              required
            />
          </label>
          <label className="block">
            <span className="text-xs font-bold uppercase tracking-wide text-slate-500">Industry</span>
            <input
              value={form.industry}
              onChange={(event) => updateField('industry', event.target.value)}
              className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-[#003A8C] focus:ring-2 focus:ring-blue-100"
              placeholder="Manufacturing"
              required
            />
          </label>
          <label className="block">
            <span className="text-xs font-bold uppercase tracking-wide text-slate-500">Geography</span>
            <input
              value={form.geography}
              onChange={(event) => updateField('geography', event.target.value)}
              className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-[#003A8C] focus:ring-2 focus:ring-blue-100"
              placeholder="India"
              required
            />
          </label>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="mt-5 inline-flex items-center gap-2 rounded-lg bg-[#003A8C] px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? <Loader2 className="animate-spin" size={17} /> : <WandSparkles size={17} />}
          {loading ? 'Manufacturing data...' : 'Manufacture Data'}
        </button>
      </form>

      {error && <div className="rounded-lg bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div>}

      {result && (
        <div className="rounded-lg bg-white p-5 shadow-enterprise">
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate-700">Generated Output</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Database</p>
              <p className="mt-1 font-mono text-sm font-semibold text-slate-800">{result.databaseName}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-500">MCP Folder</p>
              <p className="mt-1 break-all font-mono text-sm font-semibold text-slate-800">{result.mcpFolder}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-500">MCP URL</p>
              <p className="mt-1 break-all font-mono text-sm font-semibold text-slate-800">{result.mcpUrl}</p>
            </div>
            <div className={`rounded-lg border p-4 ${result.mcpReady ? 'border-emerald-200 bg-emerald-50' : 'border-amber-200 bg-amber-50'}`}>
              <p className="text-xs font-bold uppercase tracking-wide text-slate-500">MCP Status</p>
              <p className={`mt-1 text-sm font-semibold ${result.mcpReady ? 'text-emerald-700' : 'text-amber-700'}`}>
                {result.mcpStatus || 'MCP status was not returned.'}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-500">PDFs</p>
              <p className="mt-1 text-sm font-semibold text-slate-800">
                {result.generatedPdfCount ?? result.pdfCount} generated this run / {result.pdfCount} available
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Tables</p>
              <p className="mt-1 text-sm font-semibold text-slate-800">
                {result.seededTableCount ?? result.tableCount} seeded this run / {result.tableCount} available
              </p>
            </div>
          </div>
          {result.mistralLibraryId && (
            <p className="mt-4 rounded-lg bg-blue-50 px-4 py-3 font-mono text-sm font-semibold text-[#003A8C]">
              Library ID: {result.mistralLibraryId}
            </p>
          )}
          {result.uploadError && (
            <p className="mt-4 rounded-lg bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-700">
              Mistral upload did not complete: {result.uploadError}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
