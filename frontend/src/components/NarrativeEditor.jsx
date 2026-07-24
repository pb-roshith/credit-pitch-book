import { Download, Eye, History, PenLine, RotateCcw, Save, Square, WandSparkles, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { fetchNarrativeDrafts, generateNarrative, runNarrativeJudge, saveNarrativeDraft } from '../services/api.js';

function getCurrentUser() {
  const saved = localStorage.getItem('creditPitchUser');
  return saved ? JSON.parse(saved) : null;
}

export default function NarrativeEditor({ deal, section, selectedDraftId, onSelectDraftForDownload }) {
  const [mode, setMode] = useState('Preview');
  const [customInstructions, setCustomInstructions] = useState('');
  const [outputTemplate, setOutputTemplate] = useState('');
  const [draft, setDraft] = useState('');
  const [editDraft, setEditDraft] = useState('');
  const [savedDraft, setSavedDraft] = useState(null);
  const [versions, setVersions] = useState([]);
  const [expandedVersions, setExpandedVersions] = useState({});
  const [discoveredSources, setDiscoveredSources] = useState([]);
  const [generating, setGenerating] = useState(false);
  const [runningJudge, setRunningJudge] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);
  const [error, setError] = useState('');
  const [moderationWarning, setModerationWarning] = useState('');
  const [moderationDetails, setModerationDetails] = useState([]);
  const [showModerationDetails, setShowModerationDetails] = useState(false);
  const [judgeResult, setJudgeResult] = useState(null);
  const [showJudgeDetails, setShowJudgeDetails] = useState(false);
  const [judgeExplanationMode, setJudgeExplanationMode] = useState('score');
  const inputSources = section.inputSources
    ? section.inputSources.split(',').map((source) => source.trim()).filter(Boolean)
    : [];

  const toggleVersionExpanded = (draftId) => {
    setExpandedVersions((current) => ({
      ...current,
      [draftId]: !current[draftId],
    }));
  };

  const getVersionPreview = (content, expanded) => {
    if (expanded) {
      return content;
    }

    const lines = content.split('\n');
    const preview = lines.slice(0, 4).join('\n');
    if (preview.length > 520) {
      return `${preview.slice(0, 520)}...`;
    }
    return lines.length > 4 ? `${preview}\n...` : preview;
  };

  const getJudgePoints = (explanation) => {
    if (!explanation) {
      return [];
    }

    const linePoints = explanation
      .split('\n')
      .map((line) => line.replace(/^[-*]\s*/, '').replace(/^\d+[.)]\s*/, '').trim())
      .filter(Boolean);

    if (linePoints.length > 1) {
      return linePoints;
    }

    return explanation
      .split(/(?<=[.!?])\s+/)
      .map((sentence) => sentence.trim())
      .filter(Boolean);
  };

  const getChangedPieces = (baseText, currentText) => {
    const currentTokens = currentText.match(/\s+|[^\s]+/g) || [];
    const baseTokens = baseText.match(/\s+|[^\s]+/g) || [];
    const currentWords = currentTokens
      .map((value, index) => ({ value, index }))
      .filter((token) => token.value.trim());
    const baseWords = baseTokens
      .map((value, index) => ({ value, index }))
      .filter((token) => token.value.trim());

    if (!baseText || baseText === currentText) {
      return currentTokens.map((value) => ({ value, changed: false }));
    }

    if (baseWords.length > 1200 || currentWords.length > 1200) {
      let start = 0;
      while (start < baseTokens.length && start < currentTokens.length && baseTokens[start] === currentTokens[start]) {
        start += 1;
      }

      let baseEnd = baseTokens.length - 1;
      let currentEnd = currentTokens.length - 1;
      while (baseEnd >= start && currentEnd >= start && baseTokens[baseEnd] === currentTokens[currentEnd]) {
        baseEnd -= 1;
        currentEnd -= 1;
      }

      return currentTokens.map((value, index) => ({
        value,
        changed: value.trim() ? index >= start && index <= currentEnd : false,
      }));
    }

    const rows = Array.from({ length: baseWords.length + 1 }, () => new Uint16Array(currentWords.length + 1));
    for (let i = 1; i <= baseWords.length; i += 1) {
      for (let j = 1; j <= currentWords.length; j += 1) {
        rows[i][j] =
          baseWords[i - 1].value === currentWords[j - 1].value
            ? rows[i - 1][j - 1] + 1
            : Math.max(rows[i - 1][j], rows[i][j - 1]);
      }
    }

    const unchangedTokenIndexes = new Set();
    let i = baseWords.length;
    let j = currentWords.length;
    while (i > 0 && j > 0) {
      if (baseWords[i - 1].value === currentWords[j - 1].value) {
        unchangedTokenIndexes.add(currentWords[j - 1].index);
        i -= 1;
        j -= 1;
      } else if (rows[i - 1][j] >= rows[i][j - 1]) {
        i -= 1;
      } else {
        j -= 1;
      }
    }

    return currentTokens.map((value, index) => ({
      value,
      changed: value.trim() ? !unchangedTokenIndexes.has(index) : false,
    }));
  };

  const renderDraftWithChanges = (baseText, currentText) => (
    <div className="whitespace-pre-wrap font-sans text-sm leading-7 text-slate-800">
      {getChangedPieces(baseText, currentText).map((piece, index) => (
        <span key={`${piece.value}-${index}`} className={piece.changed ? 'text-pink-600' : undefined}>
          {piece.value}
        </span>
      ))}
    </div>
  );

  const getCurrentVersion = () => versions.find((version) => version.draftId === savedDraft?.id);

  const getParentVersion = (version) => {
    if (!version?.editedFromDraftId) {
      return null;
    }

    return versions.find((candidate) => candidate.draftId === version.editedFromDraftId) || null;
  };

  const effectiveDownloadDraftId = selectedDraftId || versions[0]?.draftId || null;

  const loadVersions = async () => {
    const history = await fetchNarrativeDrafts(deal.id, section.sectionNumber);
    setVersions(history);
    if (history.length > 0) {
      const latest = history[0];
      setDraft(latest.draft);
      setEditDraft(latest.draft);
      setSavedDraft({ id: latest.draftId, savedAt: latest.createdAt, versionType: latest.versionType });
      setDiscoveredSources(latest.discoveredSources || []);
      setJudgeResult(latest.judge || null);
    } else {
      setDraft('');
      setEditDraft('');
      setSavedDraft(null);
      setDiscoveredSources([]);
      setJudgeResult(null);
    }
  };

  useEffect(() => {
    setMode('Preview');
    setExpandedVersions({});
    setError('');
    setModerationWarning('');
    setModerationDetails([]);
    setShowModerationDetails(false);
    setShowJudgeDetails(false);
    setJudgeExplanationMode('score');
    loadVersions().catch((err) => setError(err.message));
  }, [deal.id, section.sectionNumber]);

  const handleGenerate = async () => {
    const currentUser = getCurrentUser();
    setGenerating(true);
    setError('');
    setModerationWarning('');
    setModerationDetails([]);
    setShowModerationDetails(false);
    setShowJudgeDetails(false);
    setJudgeExplanationMode('score');

    try {
      const result = await generateNarrative(deal.id, section.sectionNumber, {
        customInstructions,
        outputTemplate,
        username: currentUser?.username || '',
      });
      setDraft(result.draft);
      setEditDraft(result.draft);
      setSavedDraft({ id: result.draftId, savedAt: result.savedAt, versionType: 'generated' });
      setDiscoveredSources(result.discoveredSources || []);
      setJudgeResult(null);
      setMode('Preview');
      await loadVersions();
    } catch (err) {
      if (err.detail?.code === 'moderation_failed') {
        setModerationWarning(err.message);
        setModerationDetails(err.detail?.categoryResults || []);
        setShowModerationDetails(true);
      } else {
        setError(err.message);
      }
    } finally {
      setGenerating(false);
    }
  };

  const handleEditMode = () => {
    setEditDraft(draft);
    setMode('Edit');
  };

  const handlePreviewMode = () => {
    setEditDraft(draft);
    setMode('Preview');
  };

  const handleHistoryMode = async () => {
    setError('');
    setMode('History');
    await loadVersions();
  };

  const handleSaveEdit = async () => {
    if (!editDraft.trim()) {
      setError('Edited narrative content cannot be empty.');
      return;
    }

    const currentUser = getCurrentUser();
    setSavingEdit(true);
    setError('');

    try {
      const result = await saveNarrativeDraft(deal.id, section.sectionNumber, {
        content: editDraft,
        editedFromDraftId: savedDraft?.id || null,
        username: currentUser?.username || '',
      });
      setDraft(result.draft);
      setEditDraft(result.draft);
      setSavedDraft({ id: result.draftId, savedAt: result.createdAt, versionType: result.versionType });
      setDiscoveredSources(result.discoveredSources || []);
      setJudgeResult(result.judge || null);
      setMode('Preview');
      await loadVersions();
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingEdit(false);
    }
  };

  const handleRunJudge = async () => {
    if (!savedDraft?.id) {
      setError('Generate or save a draft before running judge.');
      return;
    }

    setRunningJudge(true);
    setError('');
    setShowJudgeDetails(false);
    setJudgeExplanationMode('score');

    try {
      const result = await runNarrativeJudge(deal.id, section.sectionNumber, {
        draftId: savedDraft.id,
      });
      setJudgeResult(result.judge || null);
      await loadVersions();
    } catch (err) {
      setError(err.message);
    } finally {
      setRunningJudge(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg bg-white p-5 shadow-enterprise">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-bold text-slate-900">
                {section.number} {section.name.toUpperCase()}
              </h1>
              <span className="rounded-full bg-blue-100 px-2.5 py-1 text-xs font-bold text-[#003A8C]">ZERO-SHOT</span>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-600">PENDING</span>
            </div>
            <p className="mt-2 text-sm text-slate-500">{section.description}</p>
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <h3 className="text-sm font-bold uppercase tracking-wide text-slate-700">Data Sources</h3>
          <div className="mt-3 flex flex-wrap gap-2">
            {inputSources.map((chip) => (
              <span key={chip} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-700">
                {chip}
              </span>
            ))}
          </div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <h3 className="text-sm font-bold uppercase tracking-wide text-slate-700">Expected Output</h3>
          <p className="mt-3 text-sm leading-6 text-slate-600">{section.expectedOutput}</p>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm font-bold uppercase tracking-wide text-slate-700">Custom Instructions For AI</h3>
            <span className="rounded-full bg-blue-100 px-2.5 py-1 text-xs font-bold text-[#003A8C]">ZERO-SHOT</span>
          </div>
          <textarea
            value={customInstructions}
            onChange={(event) => {
              setCustomInstructions(event.target.value);
              setModerationWarning('');
              setModerationDetails([]);
            }}
            className={`mt-4 min-h-44 w-full resize-y rounded-lg border p-3 text-sm outline-none focus:ring-2 ${
              moderationWarning
                ? 'border-red-400 bg-red-50 text-red-800 focus:border-red-500 focus:ring-red-100'
                : 'border-slate-300 focus:border-[#003A8C] focus:ring-blue-100'
            }`}
            placeholder="Provide example outputs, business guidance, writing style, risk considerations, or custom instructions."
          />
          {moderationWarning && (
            <div className="mt-3 rounded-lg bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
              {moderationWarning}
            </div>
          )}
          {moderationDetails.length > 0 && (
            <div className="mt-3 overflow-hidden rounded-lg border border-red-200 bg-white">
              <button
                type="button"
                onClick={() => setShowModerationDetails((current) => !current)}
                className="flex w-full items-center justify-between gap-3 bg-red-50 px-4 py-3 text-left text-sm font-bold text-red-700"
              >
                <span>Moderation details</span>
                <span>{showModerationDetails ? 'Collapse' : 'Expand'}</span>
              </button>
              {showModerationDetails && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                      <tr>
                        <th className="px-4 py-2">Topic</th>
                        <th className="px-4 py-2">True / False</th>
                        <th className="px-4 py-2">Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {moderationDetails.map((item) => (
                        <tr key={item.topic} className="border-t border-slate-100">
                          <td className="px-4 py-2 font-semibold text-slate-700">{item.topic}</td>
                          <td className={`px-4 py-2 font-bold ${item.flagged ? 'text-red-700' : 'text-emerald-700'}`}>
                            {item.flagged ? 'True' : 'False'}
                          </td>
                          <td className="px-4 py-2 font-mono text-slate-600">{Number(item.score || 0).toFixed(3)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
          <div className="mt-3 flex gap-2">
            <button className="inline-flex items-center gap-2 rounded-lg bg-[#003A8C] px-3 py-2 text-sm font-bold text-white">
              <Save size={16} />
              Save Instructions
            </button>
            <button
              onClick={() => setCustomInstructions('')}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-700"
            >
              <RotateCcw size={16} />
              Reset
            </button>
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <h3 className="text-sm font-bold uppercase tracking-wide text-slate-700">Output Template</h3>
          <textarea
            value={outputTemplate}
            onChange={(event) => setOutputTemplate(event.target.value)}
            className="mt-4 min-h-44 w-full resize-y rounded-lg border border-slate-300 p-3 font-mono text-sm outline-none focus:border-[#003A8C] focus:ring-2 focus:ring-blue-100"
            placeholder="Create or paste an output template for this section."
          />
          <div className="mt-3 flex gap-2">
            <button className="inline-flex items-center gap-2 rounded-lg bg-[#003A8C] px-3 py-2 text-sm font-bold text-white">
              <Save size={16} />
              Save Template
            </button>
            <button className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-700">
              <Eye size={16} />
              Preview
            </button>
          </div>
        </div>
      </div>

      {mode !== 'History' && (
        <div className="sticky bottom-4 z-20 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-blue-100 bg-white p-3 shadow-enterprise">
          <div className="text-sm font-semibold text-slate-600">{mode === 'Edit' ? 'Edit Action Bar' : 'AI Action Bar'}</div>
          <div className="flex flex-wrap gap-2">
            {mode === 'Preview' && (
              <>
                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="inline-flex items-center gap-2 rounded-lg bg-[#003A8C] px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <WandSparkles size={16} />
                  {generating ? 'Generating...' : 'Generate Draft'}
                </button>
                <button className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-700">Regenerate</button>
                <button className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-700">
                  <Square size={14} />
                  Stop
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {error && <div className="rounded-lg bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div>}
      {savedDraft && mode !== 'History' && (
        <div className="rounded-lg bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700">
          Draft #{savedDraft.id} saved to Postgres as {savedDraft.versionType}.
        </div>
      )}
      {mode === 'Preview' && draft && (
      <div className="rounded-lg border border-blue-100 bg-white p-4 shadow-enterprise">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-slate-600">LLM Judge Confidence</p>
              {judgeResult?.confidencePercent !== null && judgeResult?.confidencePercent !== undefined ? (
                <p className="mt-1 text-sm font-semibold text-slate-500">
                  Remaining gap: {100 - judgeResult.confidencePercent}%
                </p>
              ) : (
                <p className="mt-1 text-sm font-semibold text-slate-500">Run judge when you want to evaluate this draft.</p>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-[#003A8C] px-3 py-1 text-sm font-bold text-white">
                {judgeResult?.confidencePercent !== null && judgeResult?.confidencePercent !== undefined
                  ? `${judgeResult.confidencePercent}%`
                  : 'Not scored'}
              </span>
              <button
                type="button"
                onClick={handleRunJudge}
                disabled={runningJudge || !savedDraft?.id}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <WandSparkles size={16} />
                {runningJudge ? 'Running...' : 'Run Judge'}
              </button>
            </div>
          </div>
          {(judgeResult?.scoreExplanation || judgeResult?.remainingGapExplanation || judgeResult?.explanation) && (
            <div className="mt-3 overflow-hidden rounded-lg border border-slate-200">
              <button
                type="button"
                onClick={() => setShowJudgeDetails((current) => !current)}
                className="flex w-full items-center justify-between gap-3 bg-slate-50 px-4 py-3 text-left text-sm font-bold text-slate-700"
              >
                <span>Judge explanation</span>
                <span>{showJudgeDetails ? 'Collapse' : 'Expand'}</span>
              </button>
              {showJudgeDetails && (
                <div className="px-4 py-4">
                  <div className="inline-flex rounded-lg border border-slate-300 bg-white p-1">
                    <button
                      type="button"
                      onClick={() => setJudgeExplanationMode('score')}
                      className={`rounded-md px-3 py-2 text-xs font-bold ${
                        judgeExplanationMode === 'score' ? 'bg-[#003A8C] text-white' : 'text-slate-600'
                      }`}
                    >
                      Score explanation ({judgeResult?.confidencePercent ?? 0}%)
                    </button>
                    <button
                      type="button"
                      onClick={() => setJudgeExplanationMode('gap')}
                      className={`rounded-md px-3 py-2 text-xs font-bold ${
                        judgeExplanationMode === 'gap' ? 'bg-[#003A8C] text-white' : 'text-slate-600'
                      }`}
                    >
                      Remaining gap ({Math.max(0, 100 - (judgeResult?.confidencePercent || 0))}%)
                    </button>
                  </div>
                  <ul className="mt-4 space-y-2 text-sm leading-6 text-slate-600">
                    {getJudgePoints(
                      judgeExplanationMode === 'score'
                        ? (judgeResult?.scoreExplanation || judgeResult?.metadata?.scoreExplanation || judgeResult?.explanation)
                        : (judgeResult?.remainingGapExplanation || judgeResult?.metadata?.remainingGapExplanation || judgeResult?.explanation),
                    ).map((point, index) => (
                      <li key={`${point}-${index}`} className="flex gap-2">
                        <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#003A8C]" />
                        <span>{point}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="rounded-lg bg-white p-5 shadow-enterprise">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-bold uppercase tracking-wide text-slate-700">
            {mode === 'History' ? 'Version History' : mode === 'Edit' ? 'Edit Narrative' : 'Generated Narrative Preview'}
          </h3>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={handlePreviewMode}
              className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-bold ${
                mode === 'Preview' ? 'bg-[#003A8C] text-white' : 'border border-slate-300 text-slate-700'
              }`}
            >
              <Eye size={16} />
              Preview mode
            </button>
            <button
              onClick={handleEditMode}
              className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-bold ${
                mode === 'Edit' ? 'bg-[#003A8C] text-white' : 'border border-slate-300 text-slate-700'
              }`}
            >
              <PenLine size={16} />
              Edit mode
            </button>
            <button
              onClick={handleHistoryMode}
              className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-bold ${
                mode === 'History' ? 'bg-[#003A8C] text-white' : 'border border-slate-300 text-slate-700'
              }`}
            >
              <History size={16} />
              Version history
            </button>
            <button className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-700">
              <Download size={16} />
              Export
            </button>
          </div>
        </div>

        {mode === 'History' && (
          <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-600">All Generated And Edited Versions</p>
              <button onClick={handlePreviewMode} className="rounded-lg border border-slate-300 p-2 text-slate-600">
                <X size={15} />
              </button>
            </div>
            <div className="mt-3 space-y-3">
              {versions.length === 0 ? (
                <p className="text-sm font-semibold text-slate-500">No saved versions yet.</p>
              ) : (
                versions.map((version) => {
                  const expanded = Boolean(expandedVersions[version.draftId]);
                  const versionPreview = getVersionPreview(version.draft, expanded);
                  const parentVersion = getParentVersion(version);
                  const markedForDownload = effectiveDownloadDraftId === version.draftId;
                  return (
                  <div
                    key={version.draftId}
                    className="w-full rounded-lg border border-slate-200 bg-white p-3 text-left"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-bold text-slate-800">
                          Draft #{version.draftId} / {version.versionType}
                        </span>
                        {markedForDownload && (
                          <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-bold text-[#003A8C]">
                            {selectedDraftId ? 'Marked for download' : 'Default download'}
                          </span>
                        )}
                      </div>
                      <span className="text-xs font-semibold text-slate-500">{new Date(version.createdAt).toLocaleString()}</span>
                    </div>
                    {version.editedBy && <p className="mt-1 text-xs font-semibold text-slate-500">Edited by {version.editedBy}</p>}
                    <div className="mt-2">
                      {version.versionType === 'edited' && parentVersion?.draft ? (
                        renderDraftWithChanges(parentVersion.draft, versionPreview)
                      ) : (
                        <p className="whitespace-pre-wrap text-sm leading-6 text-slate-600">{versionPreview}</p>
                      )}
                    </div>
                    {version.draft.length > getVersionPreview(version.draft, false).length && (
                      <button
                        type="button"
                        onClick={() => toggleVersionExpanded(version.draftId)}
                        className="mt-3 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-bold text-slate-700"
                      >
                        {expanded ? 'Show less' : 'Show more'}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => onSelectDraftForDownload?.(section.sectionNumber, version.draftId)}
                      disabled={selectedDraftId === version.draftId}
                      className="ml-2 mt-3 rounded-lg border border-blue-200 px-3 py-1.5 text-xs font-bold text-[#003A8C] disabled:cursor-not-allowed disabled:bg-blue-50"
                    >
                      {selectedDraftId === version.draftId ? 'Marked' : 'Use for download'}
                    </button>
                  </div>
                  );
                })
              )}
            </div>
          </div>
        )}

        {mode === 'Preview' && discoveredSources.length > 0 && (
          <div className="mt-4 rounded-lg border border-blue-100 bg-blue-50 p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-[#003A8C]">Discovered Sources</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {discoveredSources.map((source) => (
                <span key={source.toolName} className="rounded-full bg-white px-3 py-1 text-xs font-bold text-slate-700">
                  {source.toolName}
                </span>
              ))}
            </div>
          </div>
        )}

        {mode === 'Edit' && (
          <div className="mt-5 min-h-72 rounded-lg border border-slate-200 bg-slate-50 p-5 leading-7 text-slate-700">
            <div>
              <div className="mb-4 rounded-lg border border-pink-200 bg-pink-50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-bold text-pink-700">Edit mode is active</p>
                    <p className="mt-1 text-sm font-semibold text-slate-600">
                      Save after editing. Only added or changed text will display in pink in preview.
                    </p>
                  </div>
                  <button
                    onClick={handleSaveEdit}
                    disabled={savingEdit}
                    className="inline-flex items-center gap-2 rounded-lg bg-[#003A8C] px-5 py-2.5 text-sm font-bold text-white shadow-enterprise disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    <Save size={16} />
                    {savingEdit ? 'Saving...' : 'Save Edited Version'}
                  </button>
                </div>
              </div>
              <textarea
                value={editDraft}
                onChange={(event) => setEditDraft(event.target.value)}
                className="min-h-72 w-full resize-y rounded-lg border border-slate-300 bg-white p-4 font-sans text-sm leading-7 text-slate-800 outline-none focus:border-[#003A8C] focus:ring-2 focus:ring-blue-100"
                placeholder="Generate a draft before editing this section."
              />
            </div>
          </div>
        )}

        {mode === 'Preview' && (
          <div className="mt-5 min-h-72 rounded-lg border border-slate-200 bg-slate-50 p-5 leading-7 text-slate-700">
          {draft ? (() => {
            const currentVersion = getCurrentVersion();
            const parentVersion = getParentVersion(currentVersion);

            if (currentVersion?.versionType === 'edited' && parentVersion?.draft) {
              return renderDraftWithChanges(parentVersion.draft, draft);
            }

            return (
              <pre className="whitespace-pre-wrap font-sans text-sm leading-7 text-slate-800">
                {draft}
              </pre>
            );
          })() : (
            <p className="font-medium text-slate-500">No generated narrative is available for this section yet.</p>
          )}
          </div>
        )}
      </div>
    </div>
  );
}
