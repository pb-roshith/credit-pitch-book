import { FileSpreadsheet, FileText, FileType, Presentation, Plus, Trash2, Eye } from 'lucide-react';

const icons = {
  PDF: FileType,
  DOCX: FileText,
  XLSX: FileSpreadsheet,
  PPTX: Presentation,
};

export default function DocumentLibrary({ documents }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-wide text-slate-700">Document Library</h3>
          <p className="mt-2 max-w-3xl text-sm text-slate-500">
            All documents are shared across every section. AI agents automatically search this library for relevant
            information.
          </p>
        </div>
        <button className="inline-flex items-center gap-2 rounded-lg bg-[#003A8C] px-3 py-2 text-sm font-bold text-white">
          <Plus size={16} />
          Add Document
        </button>
      </div>

      {documents.length === 0 ? (
        <div className="mt-5 rounded-lg border border-dashed border-slate-300 bg-slate-50 p-8 text-center text-sm text-slate-500">
          <p className="font-semibold text-slate-700">No documents in the library yet.</p>
          <p className="mt-1">Upload files to provide context to AI generation.</p>
        </div>
      ) : (
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {documents.map((doc) => {
            const Icon = icons[doc.type] || FileText;
            return (
              <article key={doc.id} className="flex items-center gap-3 rounded-lg border border-slate-200 p-3">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-slate-100 text-[#003A8C]">
                  <Icon size={20} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-bold text-slate-900">{doc.name}</p>
                  <p className="text-xs text-slate-500">
                    {doc.type} / {doc.size} / {doc.owner}
                  </p>
                </div>
                <button className="rounded-lg p-2 text-slate-500 hover:bg-blue-50 hover:text-[#003A8C]" aria-label="View">
                  <Eye size={16} />
                </button>
                <button className="rounded-lg p-2 text-slate-500 hover:bg-red-50 hover:text-red-700" aria-label="Delete">
                  <Trash2 size={16} />
                </button>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
