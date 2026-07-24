import {
  Activity,
  BarChart3,
  FileJson,
  Gauge,
  RefreshCw,
  Search,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { fetchObservability } from '../services/api.js';

const notTracked = 'Not tracked';

function formatValue(value, suffix = '') {
  if (value === null || value === undefined || value === '') {
    return notTracked;
  }
  return `${value}${suffix}`;
}

function formatPromptField(value) {
  return typeof value === 'string' && value.trim() ? 'Available' : 'Not available';
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : notTracked;
}

function Panel({ title, subtitle, icon: Icon, children }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-enterprise">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-blue-50 text-[#003A8C]">
            <Icon size={19} />
          </span>
          <div>
            <h2 className="text-sm font-bold uppercase tracking-wide text-slate-700">{title}</h2>
            {subtitle && <p className="mt-1 text-sm font-semibold text-slate-500">{subtitle}</p>}
          </div>
        </div>
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function RectStat({ label, value, detail }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <p className="text-xs font-bold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-xl font-bold text-slate-950">{value}</p>
      {detail && <p className="mt-1 text-xs font-semibold text-slate-500">{detail}</p>}
    </div>
  );
}

function MiniList({ items, emptyText = 'No records available.' }) {
  if (!items?.length) {
    return <p className="text-sm font-semibold text-slate-500">{emptyText}</p>;
  }

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div key={item.name || item.toolName || item.clientMatch} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
          <span className="min-w-0 truncate text-sm font-semibold text-slate-700">{item.name || item.toolName || item.clientMatch}</span>
          <span className="rounded-full bg-white px-2.5 py-1 text-xs font-bold text-[#003A8C]">{item.count ?? item.status ?? ''}</span>
        </div>
      ))}
    </div>
  );
}

function WorkflowSummary({ title, workflow, detail, extraStats = [] }) {
  return (
    <div className="mt-4 border-t border-slate-200 pt-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase tracking-wide text-slate-500">{title}</p>
        {detail && <span className="text-xs font-semibold text-slate-500">{detail}</span>}
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <RectStat label="Requests" value={workflow?.totalRequests || 0} />
        <RectStat label="Successful" value={workflow?.successfulRequests || 0} />
        <RectStat label="Failed" value={workflow?.failedRequests || 0} />
        <RectStat label="Average Latency" value={formatValue(workflow?.averageLatencyMs, ' ms')} />
        <RectStat label="Input Tokens" value={formatValue(workflow?.inputTokens)} />
        <RectStat label="Output Tokens" value={formatValue(workflow?.outputTokens)} />
        <RectStat label="Total Tokens" value={formatValue(workflow?.totalTokens)} detail="Input + output tokens" />
        {extraStats.map((stat) => (
          <RectStat key={stat.label} label={stat.label} value={stat.value} detail={stat.detail} />
        ))}
      </div>
    </div>
  );
}

function FlowStep({ index, title, status = 'success', detail, metrics }) {
  const isSuccess = status === 'success' || status === 'available';
  const isSkipped = status === 'not_run' || status === 'not_available';
  const statusClass = isSuccess
    ? 'bg-emerald-50 text-emerald-700'
    : isSkipped
      ? 'bg-slate-100 text-slate-500'
      : 'bg-red-50 text-red-700';

  return (
    <div className="relative pl-10">
      <div className="absolute left-3 top-9 h-[calc(100%+1rem)] w-px bg-slate-200 last:hidden" />
      <span className="absolute left-0 top-1 grid h-7 w-7 place-items-center rounded-full bg-[#003A8C] text-xs font-bold text-white">{index}</span>
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="font-bold text-slate-900">{title}</p>
          <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${statusClass}`}>{status}</span>
        </div>
        {detail && <p className="mt-2 text-sm font-semibold text-slate-600">{detail}</p>}
        {metrics?.length ? (
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {metrics.map((metric) => (
              <div key={metric.label} className="rounded-lg border border-slate-200 bg-white px-3 py-2">
                <p className="text-xs font-bold uppercase tracking-wide text-slate-500">{metric.label}</p>
                <p className="mt-1 text-sm font-bold text-slate-900">{metric.value}</p>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default function Observability() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState('');
  const [selectedClient, setSelectedClient] = useState('');
  const [selectedTraceId, setSelectedTraceId] = useState(null);
  const [showTraceExplorer, setShowTraceExplorer] = useState(false);
  const [error, setError] = useState('');

  const loadData = async (showRefreshing = false) => {
    if (showRefreshing) {
      setRefreshing(true);
    }
    setError('');
    try {
      const result = await fetchObservability(selectedClient);
      setData(result);
      setSelectedTraceId((current) => (
        result.traces?.some((trace) => trace.id === current) ? current : result.traces?.[0]?.id || null
      ));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [selectedClient]);

  const traces = data?.traces || [];
  const filteredTraces = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return traces;
    }
    return traces.filter((trace) =>
      [trace.userQuery, trace.agentFlow, trace.mistralTraceId, trace.model, trace.customer, trace.sectionName]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(needle)),
    );
  }, [query, traces]);
  const selectedTrace = traces.find((trace) => trace.id === selectedTraceId) || filteredTraces[0] || null;

  if (loading) {
    return <div className="rounded-lg bg-white p-8 text-center font-semibold text-slate-500 shadow-enterprise">Loading observability...</div>;
  }

  const summary = data?.summary || {};
  const clients = data?.clients || [];
  const performanceByUseCase = summary.performanceByUseCase || [];
  const narrativeGenerationFailures = performanceByUseCase.find((item) => item.name === 'narrative_generate')?.failedRequests || 0;
  const judgeFailures = performanceByUseCase.find((item) => item.name === 'judge')?.failedRequests || 0;
  const selectedTraceFlowSteps = selectedTrace ? [
    {
      title: 'User Request',
      status: 'success',
      detail: selectedTrace.audit.originalUserRequest,
      metrics: [{ label: 'Trace ID', value: selectedTrace.audit.traceId }],
    },
    {
      title: 'Source Discovery',
      status: selectedTrace.audit.retrievedSources?.length ? 'success' : 'not_available',
      detail: 'Discover available MCP and source-table evidence for the selected narrative section.',
      metrics: [
        { label: 'Retrieved Sources', value: selectedTrace.audit.retrievedSources?.length || 0 },
        { label: 'OpenTelemetry Trace', value: selectedTrace.audit.openTelemetry?.available ? 'Available' : 'Not available' },
        { label: 'Latency', value: formatValue(selectedTrace.audit.metrics?.sourceDiscovery?.latencyMs, ' ms') },
        { label: 'Total Tokens', value: formatValue(selectedTrace.audit.metrics?.sourceDiscovery?.tokens) },
      ],
    },
    {
      title: 'Prompt Construction',
      status: 'success',
      detail: selectedTrace.audit.finalPrompt?.section || selectedTrace.sectionName || notTracked,
      metrics: [
        { label: 'Input Sources', value: selectedTrace.audit.retrievedSources?.length || 0 },
        { label: 'Expected Output', value: selectedTrace.audit.finalPrompt?.expectedOutput ? 'Available' : notTracked },
        { label: 'Custom Instructions', value: formatPromptField(selectedTrace.audit.finalPrompt?.customInstructions) },
        { label: 'Output Template', value: formatPromptField(selectedTrace.audit.finalPrompt?.outputTemplate) },
      ],
    },
    {
      title: 'Generate Narrative',
      status: selectedTrace.status,
      detail: selectedTrace.audit.openTelemetry?.available ? 'OpenTelemetry span captured for this narrative generation.' : (selectedTrace.model || notTracked),
      metrics: [
        { label: 'Latency', value: formatValue(selectedTrace.audit.metrics?.narrativeGenerate?.latencyMs, ' ms') },
        { label: 'Input Tokens', value: formatValue(selectedTrace.audit.metrics?.narrativeGenerate?.inputTokens) },
        { label: 'Output Tokens', value: formatValue(selectedTrace.audit.metrics?.narrativeGenerate?.outputTokens) },
        { label: 'Total Tokens', value: formatValue(selectedTrace.audit.metrics?.narrativeGenerate?.tokens) },
        { label: 'Failures', value: narrativeGenerationFailures },
      ],
    },
    {
      title: 'Run Judge',
      status: selectedTrace.audit.evaluationScores?.judgeConfidencePercent !== null && selectedTrace.audit.evaluationScores?.judgeConfidencePercent !== undefined ? 'success' : 'not_run',
      detail: 'Evaluate whether the generated narrative is grounded in the discovered sources.',
      metrics: [
        { label: 'Latency', value: formatValue(selectedTrace.audit.metrics?.judge?.latencyMs, ' ms') },
        { label: 'Input Tokens', value: formatValue(selectedTrace.audit.metrics?.judge?.inputTokens) },
        { label: 'Output Tokens', value: formatValue(selectedTrace.audit.metrics?.judge?.outputTokens) },
        { label: 'Total Tokens', value: formatValue(selectedTrace.audit.metrics?.judge?.tokens) },
        { label: 'Judge Score', value: formatValue(selectedTrace.audit.evaluationScores?.judgeConfidencePercent, '%') },
      ],
    },
    {
      title: 'Save Draft',
      status: 'success',
      detail: formatDate(selectedTrace.audit.timestamp),
      metrics: [
        { label: 'Citations', value: selectedTrace.audit.citations?.length || 0 },
        { label: 'Draft ID', value: selectedTrace.draftId || notTracked },
      ],
    },
  ] : [];

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'observability-dashboard.json';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-5">
      <div className="rounded-lg bg-white p-5 shadow-enterprise">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="grid h-11 w-11 place-items-center rounded-lg bg-[#003A8C] text-white">
              <Activity size={22} />
            </span>
            <div>
              <h1 className="text-2xl font-bold text-slate-950">Observability</h1>
              <p className="text-sm font-semibold text-slate-500">Trace, RAG, evaluation, performance, and audit dashboard.</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={exportJson}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-700"
            >
              <FileJson size={16} />
              Export JSON
            </button>
            <button
              onClick={() => loadData(true)}
              disabled={refreshing}
              className="inline-flex items-center gap-2 rounded-lg bg-[#003A8C] px-3 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw className={refreshing ? 'animate-spin' : ''} size={16} />
              Refresh
            </button>
          </div>
        </div>
      </div>

      {error && <div className="rounded-lg bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div>}

      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-enterprise">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Client</p>
            <p className="mt-1 text-sm font-semibold text-slate-700">Select a client to filter the observability dashboard.</p>
          </div>
          <select
            value={selectedClient}
            onChange={(event) => {
              setSelectedClient(event.target.value);
              setQuery('');
              setShowTraceExplorer(false);
            }}
            className="min-w-[240px] rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-bold text-slate-800 outline-none focus:border-[#003A8C]"
          >
            <option value="">All Clients</option>
            {clients.map((client) => (
              <option key={client} value={client}>{client}</option>
            ))}
          </select>
        </div>
      </div>

      <Panel title="Executive Overview" subtitle="Operational summary across AI drafting and review workflows." icon={Gauge}>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <RectStat label="Total Requests" value={summary.totalRequests || 0} />
          <RectStat label="Successful Requests" value={summary.successfulRequests || 0} />
          <RectStat label="Failed Requests" value={summary.failedRequests || 0} />
          <RectStat label="Average Latency" value={formatValue(summary.averageLatencyMs, ' ms')} />
          <RectStat label="Input Tokens" value={formatValue(summary.inputTokens)} />
          <RectStat label="Output Tokens" value={formatValue(summary.outputTokens)} />
          <RectStat label="Total Tokens" value={formatValue(summary.totalTokens)} detail="Input + output tokens" />
          <RectStat label="Average Evaluation Score" value={formatValue(summary.averageEvaluationScore, '%')} />
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Top Use Cases</p>
            <MiniList items={summary.topUseCases} />
          </div>
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Top Models</p>
            <MiniList items={summary.topModels} />
          </div>
        </div>
        <WorkflowSummary
          title="Source Discovery"
          workflow={summary.sourceDiscovery}
          detail={summary.sourceDiscovery?.estimatedTokenUsage ? 'Token usage is estimated from the beta agent prompt and response.' : 'No source-discovery agent token estimate is available yet.'}
          extraStats={[
            { label: 'Agent Runs', value: summary.sourceDiscovery?.agentRuns || 0 },
            { label: 'Retrieved Sources', value: summary.sourceDiscovery?.retrievedSources || 0 },
          ]}
        />
        <WorkflowSummary
          title="Narrative Generation"
          workflow={summary.narrativeGeneration}
          extraStats={[
            { label: 'Generated Drafts', value: summary.generatedDrafts || 0 },
          ]}
        />
        <WorkflowSummary
          title="Judge"
          workflow={summary.judge}
          extraStats={[
            { label: 'Judged Drafts', value: summary.judgedDrafts || 0 },
            { label: 'Average Judge Score', value: formatValue(summary.averageJudgePercent, '%') },
          ]}
        />
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Performance By Model</p>
            <div className="space-y-2">
              {(summary.performanceByModel || []).map((item) => (
                <div key={item.name} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-bold text-slate-900">{item.name}</p>
                    <span className="rounded-full bg-white px-2.5 py-1 text-xs font-bold text-[#003A8C]">{item.count} requests</span>
                  </div>
                  <p className="mt-1 text-xs font-semibold text-slate-500">
                    {formatValue(item.averageLatencyMs, ' ms avg')} / input {formatValue(item.inputTokens)} / output {formatValue(item.outputTokens)} / total {formatValue(item.totalTokens)} tokens / {item.failedRequests || 0} failures
                  </p>
                </div>
              ))}
              {!(summary.performanceByModel || []).length && <p className="text-sm font-semibold text-slate-500">No tracked model performance yet.</p>}
            </div>
          </div>
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Performance By Use Case</p>
            <div className="space-y-2">
              {(summary.performanceByUseCase || []).map((item) => (
                <div key={item.name} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-bold text-slate-900">{item.name}</p>
                    <span className="rounded-full bg-white px-2.5 py-1 text-xs font-bold text-[#003A8C]">{item.count} requests</span>
                  </div>
                  <p className="mt-1 text-xs font-semibold text-slate-500">
                    {formatValue(item.averageLatencyMs, ' ms avg')} / input {formatValue(item.inputTokens)} / output {formatValue(item.outputTokens)} / total {formatValue(item.totalTokens)} tokens / {item.failedRequests || 0} failures
                  </p>
                </div>
              ))}
              {!(summary.performanceByUseCase || []).length && <p className="text-sm font-semibold text-slate-500">No tracked use-case performance yet.</p>}
            </div>
          </div>
        </div>
      </Panel>

      <Panel title="Trace Explorer" subtitle="Search generated-draft traces and inspect the selected execution." icon={Search}>
        <button
          type="button"
          onClick={() => setShowTraceExplorer((current) => !current)}
          className="flex w-full items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-left text-sm font-bold text-slate-700"
        >
          <span>{filteredTraces.length} traces</span>
          <span>{showTraceExplorer ? 'Collapse' : 'Expand'}</span>
        </button>
        {showTraceExplorer && (
          <div className="mt-4">
            <div className="mb-4 flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2">
              <Search size={16} className="text-slate-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="w-full text-sm outline-none"
                placeholder="Search by user query, client, section, trace id, model, or flow"
              />
            </div>
            <div className="grid gap-4 xl:grid-cols-[1.1fr_1fr]">
              <div className="max-h-[560px] space-y-3 overflow-auto pr-1">
                {filteredTraces.map((trace) => (
                  <button
                    key={trace.id}
                    onClick={() => setSelectedTraceId(trace.id)}
                    className={`w-full rounded-lg border p-4 text-left ${selectedTrace?.id === trace.id ? 'border-blue-300 bg-blue-50' : 'border-slate-200 bg-slate-50 hover:bg-white'}`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-bold text-slate-900">{trace.userQuery}</p>
                      <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${trace.status === 'success' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'}`}>
                        {trace.status}
                      </span>
                    </div>
                    <div className="mt-3 grid gap-2 text-xs font-semibold text-slate-600 sm:grid-cols-2">
                      <span>Trace ID: {trace.traceId || trace.mistralTraceId}</span>
                      <span>Latency: {formatValue(trace.latencyMs, ' ms')}</span>
                      <span>Model: {trace.model || notTracked}</span>
                      <span>Input: {formatValue(trace.inputTokens)}</span>
                      <span>Output: {formatValue(trace.outputTokens)}</span>
                      <span>Total: {formatValue(trace.tokens)}</span>
                      <span>Judge Score: {formatValue(trace.evaluationScore, '%')}</span>
                    </div>
                  </button>
                ))}
                {!filteredTraces.length && <p className="text-sm font-semibold text-slate-500">No traces match your search.</p>}
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Selected Trace Details</p>
                {selectedTrace ? (
                  <div className="mt-3 space-y-3 text-sm">
                    <p className="font-bold text-slate-900">{selectedTrace.userQuery}</p>
                    <p className="font-mono text-xs text-slate-500">{selectedTrace.traceId || selectedTrace.mistralTraceId}</p>
                    <p className="text-xs font-semibold text-slate-500">{formatDate(selectedTrace.timestamp)}</p>
                    <p className={`text-xs font-bold ${selectedTrace.audit.openTelemetry?.available ? 'text-emerald-700' : 'text-slate-500'}`}>
                      OpenTelemetry trace: {selectedTrace.audit.openTelemetry?.available ? 'Available' : 'Not available'}
                    </p>
                  </div>
                ) : (
                  <p className="mt-3 text-sm font-semibold text-slate-500">No trace selected.</p>
                )}
              </div>
            </div>
          </div>
        )}
      </Panel>

      <Panel title="Audit View" subtitle="Selected generated credit memo / risk dossier trace evidence." icon={BarChart3}>
        {selectedTrace ? (
          <div className="grid gap-4 md:grid-cols-2">
            <RectStat label="Original User Request" value={selectedTrace.audit.originalUserRequest} />
            <RectStat label="Full Trace ID" value={selectedTrace.audit.traceId} detail={formatDate(selectedTrace.audit.timestamp)} />
            <RectStat label="Retrieved Sources" value={selectedTrace?.rag?.retrievedDocuments?.length || 0} />
            <RectStat label="Source Discovery Agent" value={selectedTrace.audit.sourceDiscovery?.agentId || 'Rule-based fallback'} />
            <RectStat label="Source Discovery Conversation" value={selectedTrace.audit.sourceDiscovery?.conversationId || notTracked} />
            <RectStat label="Source Discovery Latency ms" value={formatValue(selectedTrace.audit.metrics?.sourceDiscovery?.latencyMs, ' ms')} />
            <RectStat label="Source Discovery Input Tokens" value={formatValue(selectedTrace.audit.metrics?.sourceDiscovery?.inputTokens)} detail={selectedTrace.audit.sourceDiscovery?.tokenUsageEstimated ? 'Estimated' : undefined} />
            <RectStat label="Source Discovery Output Tokens" value={formatValue(selectedTrace.audit.metrics?.sourceDiscovery?.outputTokens)} detail={selectedTrace.audit.sourceDiscovery?.tokenUsageEstimated ? 'Estimated' : undefined} />
            <RectStat label="Source Discovery Total Tokens" value={formatValue(selectedTrace.audit.metrics?.sourceDiscovery?.tokens)} detail={selectedTrace.audit.sourceDiscovery?.tokenUsageEstimated ? 'Estimated input + output' : undefined} />
            <RectStat label="Source Discovery Selected Sources" value={selectedTrace.audit.sourceDiscovery?.selectedSourceCount || 0} />
            <RectStat label="Generate Narrative Latency ms" value={formatValue(selectedTrace.audit.metrics?.narrativeGenerate?.latencyMs, ' ms')} />
            <RectStat label="Generate Narrative Input Tokens" value={formatValue(selectedTrace.audit.metrics?.narrativeGenerate?.inputTokens)} />
            <RectStat label="Generate Narrative Output Tokens" value={formatValue(selectedTrace.audit.metrics?.narrativeGenerate?.outputTokens)} />
            <RectStat label="Generate Narrative Total Tokens" value={formatValue(selectedTrace.audit.metrics?.narrativeGenerate?.tokens)} />
            <RectStat label="Narrative Generation Failures" value={narrativeGenerationFailures} />
            <RectStat label="Judge Latency ms" value={formatValue(selectedTrace.audit.metrics?.judge?.latencyMs, ' ms')} />
            <RectStat label="Judge Input Tokens" value={formatValue(selectedTrace.audit.metrics?.judge?.inputTokens)} />
            <RectStat label="Judge Output Tokens" value={formatValue(selectedTrace.audit.metrics?.judge?.outputTokens)} />
            <RectStat label="Judge Total Tokens" value={formatValue(selectedTrace.audit.metrics?.judge?.tokens)} />
            <RectStat label="Judge Failures" value={judgeFailures} />
            <RectStat label="Judge Score" value={formatValue(selectedTrace.audit.evaluationScores?.judgeConfidencePercent, '%')} />
            <RectStat label="Citations" value={selectedTrace.audit.citations?.length || 0} />
            <RectStat
              label="OpenTelemetry Trace"
              value={selectedTrace.audit.openTelemetry?.available ? 'Available' : 'Not available'}
              detail={selectedTrace.audit.openTelemetry?.available ? `${selectedTrace.audit.openTelemetry.spanCount || 0} captured spans` : 'Available for newly generated drafts.'}
            />
            <div className="col-span-full rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Retrieved Sources</p>
              {selectedTrace.audit.retrievedSources?.length ? (
                <div className="mt-3 overflow-auto rounded-lg border border-slate-200 bg-white">
                  <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                    <thead className="bg-slate-100">
                      <tr>
                        <th className="px-3 py-2 text-xs font-bold uppercase tracking-wide text-slate-500">Source</th>
                        <th className="px-3 py-2 text-xs font-bold uppercase tracking-wide text-slate-500">Description</th>
                        <th className="px-3 py-2 text-xs font-bold uppercase tracking-wide text-slate-500">Score</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {selectedTrace.audit.retrievedSources.map((source, index) => (
                        <tr key={`${source.toolName || 'source'}-${index}`}>
                          <td className="max-w-[260px] px-3 py-2 font-semibold text-slate-800">
                            <span className="block truncate">{source.toolName || notTracked}</span>
                          </td>
                          <td className="px-3 py-2 font-semibold text-slate-600">{source.description || notTracked}</td>
                          <td className="whitespace-nowrap px-3 py-2 font-bold text-[#003A8C]">{source.score ?? notTracked}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="mt-2 text-sm font-semibold text-slate-500">No retrieved sources available.</p>
              )}
            </div>
            <div className="col-span-full rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Final Prompt Sent To Mistral</p>
              <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap text-xs font-semibold text-slate-700">
                {JSON.stringify(selectedTrace.audit.finalPrompt, null, 2)}
              </pre>
            </div>
            <div className="col-span-full rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Mistral Response</p>
              <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap text-xs font-semibold text-slate-700">
                {selectedTrace.audit.mistralResponse}
              </pre>
            </div>
          </div>
        ) : (
          <p className="text-sm font-semibold text-slate-500">Select a trace to inspect audit details.</p>
        )}
      </Panel>

      <Panel title="Flow Map" subtitle="Vertical execution flow for the selected trace." icon={Activity}>
        {selectedTrace ? (
          <div className="space-y-4">
            {selectedTraceFlowSteps.map((step, index) => (
              <FlowStep
                key={step.title}
                index={index + 1}
                title={step.title}
                status={step.status}
                detail={step.detail}
                metrics={step.metrics}
              />
            ))}
            {selectedTrace.otelSpans?.length ? (
              <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
                <p className="text-xs font-bold uppercase tracking-wide text-[#003A8C]">OpenTelemetry Spans</p>
                <div className="mt-3 space-y-2">
                  {selectedTrace.otelSpans.map((span) => (
                    <div key={span.spanId || `${span.name}-${span.durationMs}`} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-blue-100 bg-white px-3 py-2">
                      <span className="font-semibold text-slate-800">{span.name}</span>
                      <span className="text-xs font-bold text-slate-600">{formatValue(span.durationMs, ' ms')} / {span.status}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <p className="text-sm font-semibold text-slate-500">Select a trace to view the flow map.</p>
        )}
      </Panel>
    </div>
  );
}
