const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    const message = typeof error.detail === 'string' ? error.detail : error.detail?.message || 'Request failed';
    const requestError = new Error(message);
    requestError.detail = error.detail;
    throw requestError;
  }

  return response.json();
}

async function requestBlob(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    const message = typeof error.detail === 'string' ? error.detail : error.detail?.message || 'Request failed';
    const requestError = new Error(message);
    requestError.detail = error.detail;
    throw requestError;
  }

  return response.blob();
}

export function fetchDeals() {
  return request('/deals');
}

export function fetchNarrativeSections() {
  return request('/narrative-sections');
}

export function fetchDeal(id) {
  return request(`/deals/${id}`);
}

export function createDeal(payload) {
  return request('/deals', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteDeal(id) {
  return request(`/deals/${id}`, {
    method: 'DELETE',
  });
}

export function generateNarrative(dealId, sectionNumber, payload) {
  return request(`/deals/${dealId}/narratives/${sectionNumber}/generate`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function generateNarratives(dealId, payload) {
  return request(`/deals/${dealId}/narratives/generate-all`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function runNarrativeJudge(dealId, sectionNumber, payload) {
  return request(`/deals/${dealId}/narratives/${sectionNumber}/judge`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function exportNarrativeDrafts(dealId, payload) {
  return requestBlob(`/deals/${dealId}/narratives/export`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchNarrativeExportVersions(dealId) {
  return request(`/deals/${dealId}/narratives/exports`);
}

export function downloadNarrativeExportVersion(dealId, exportId) {
  return requestBlob(`/deals/${dealId}/narratives/exports/${exportId}/download`, {
    method: 'GET',
  });
}

export function fetchNarrativeDrafts(dealId, sectionNumber) {
  return request(`/deals/${dealId}/narratives/${sectionNumber}/drafts`);
}

export function saveNarrativeDraft(dealId, sectionNumber, payload) {
  return request(`/deals/${dealId}/narratives/${sectionNumber}/drafts`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function login(payload) {
  return request('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function register(payload) {
  return request('/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function manufactureData(payload) {
  return request('/manufacture-data', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
