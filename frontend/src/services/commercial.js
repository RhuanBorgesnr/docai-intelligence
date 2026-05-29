// Sprint 4 — commercial / executive operations service layer.
// Reuses the shared `api` axios client (JWT + base URL).
import api from './api'

export const commercial = {
  // Leads
  listLeads: (params = {}) => api.get('/commercial/leads/', { params }),
  hotLeads: (params = {}) => api.get('/commercial/leads/hot/', { params }),
  getLead: (leadId) => api.get(`/commercial/leads/${leadId}/`),
  ingestLead: (data) => api.post('/commercial/leads/ingest/', data),
  qualifyLead: (leadId) => api.post(`/commercial/leads/${leadId}/qualify/`, {}),
  draftFollowup: (leadId, data = {}) =>
    api.post(`/commercial/leads/${leadId}/followup/`, data),
  runDocaiDemo: (leadId, documentId) =>
    api.post(`/commercial/leads/${leadId}/docai-demo/`, { document_id: documentId }),

  // Lead documents
  uploadDocument: (leadId, file, title = '', docType = 'other') => {
    const fd = new FormData()
    fd.append('file', file)
    if (title) fd.append('title', title)
    fd.append('document_type', docType)
    return api.post(`/commercial/leads/${leadId}/documents/`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  listDocuments: (leadId) => api.get(`/commercial/leads/${leadId}/documents/list/`),
  getInsights: (leadId) => api.get(`/commercial/leads/${leadId}/insights/`),
  getTimeline: (leadId) => api.get(`/commercial/leads/${leadId}/timeline/`),

  // Pipeline / opportunities
  pipelineSummary: (params = {}) => api.get('/commercial/pipeline/', { params }),
  listOpportunities: (params = {}) => api.get('/commercial/opportunities/', { params }),
  getOpportunity: (id) => api.get(`/commercial/opportunities/${id}/`),
  moveOpportunity: (id, stage, reason = '') =>
    api.post(`/commercial/opportunities/${id}/stage/`, { stage, reason }),

  // Follow-ups
  listFollowups: (params = {}) => api.get('/commercial/followups/', { params }),

  // Agent Team (Phase 3)
  getAgentTeam: () => api.get('/commercial/agents/team/'),
  getAgentDetail: (agentType) => api.get(`/commercial/agents/${agentType}/`),
  runAgentRoutine: (agentType, routineName) =>
    api.post(`/commercial/agents/${agentType}/routine/${routineName}/`),

  // Demo Scheduler
  scheduleDemo: (leadId, data = {}) =>
    api.post(`/commercial/leads/${leadId}/schedule-demo/`, data),
}

export const executive = {
  briefing: (params = {}) => api.get('/orchestrator/jarvis/briefing/', { params }),
  approvals: (params = {}) => api.get('/orchestrator/dashboard/approvals/', { params }),
  agents: (params = {}) => api.get('/orchestrator/dashboard/agents/', { params }),
  health: () => api.get('/orchestrator/dashboard/health/'),

  // Daily Operations (Operational Phase)
  dailyOps: () => api.get('/orchestrator/ops/daily/'),
  costs: (days = 7) => api.get('/orchestrator/ops/costs/', { params: { days } }),
  agentPerformance: (agentType, days = 7) =>
    api.get(`/orchestrator/ops/agents/${agentType}/performance/`, { params: { days } }),
  executionFeedback: (executionId, data) =>
    api.post(`/orchestrator/ops/executions/${executionId}/feedback/`, data),
  systemStatus: () => api.get('/orchestrator/ops/status/'),
}
