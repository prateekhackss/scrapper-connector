import React, { useState, useEffect, useRef } from 'react'
import { BrowserRouter as Router, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard, Search, Users, Building2, BarChart3,
  Bell, Settings, Zap, ChevronRight, Play, Clock, Filter,
  ArrowUpRight, TrendingUp, TrendingDown, AlertCircle,
  Globe, Mail, Linkedin, Download, RefreshCcw, CheckCircle,
  XCircle, Eye, MoreHorizontal
} from 'lucide-react'
import {
  Chart as ChartJS, ArcElement, Tooltip, Legend,
  CategoryScale, LinearScale, BarElement, PointElement, LineElement, Filler
} from 'chart.js'
import { Doughnut, Bar, Line } from 'react-chartjs-2'
import * as api from './api'

ChartJS.register(
  ArcElement, Tooltip, Legend,
  CategoryScale, LinearScale, BarElement,
  PointElement, LineElement, Filler
)

// ── Shared Theme for Charts ──────────────────────────────────
const chartDefaults = {
  plugins: {
    legend: { labels: { color: '#a0a0a0', font: { family: 'Inter', size: 12 } } },
    tooltip: {
      backgroundColor: '#1e1e1e',
      titleColor: '#f5f5f5',
      bodyColor: '#a0a0a0',
      borderColor: 'rgba(212,168,67,0.25)',
      borderWidth: 1,
    },
  },
  scales: {
    x: { ticks: { color: '#666' }, grid: { color: 'rgba(255,255,255,0.04)' } },
    y: { ticks: { color: '#666' }, grid: { color: 'rgba(255,255,255,0.04)' } },
  },
}

const ROLE_FOCUS_OPTIONS = [
  ['engineering', 'Engineering'],
  ['data', 'Data / AI'],
  ['product', 'Product'],
  ['design', 'Design'],
  ['sales', 'Sales'],
  ['marketing', 'Marketing'],
  ['customer_success', 'Customer Success'],
  ['leadership', 'Leadership'],
  ['all', 'All Roles'],
]

// ── Hiring Label Badge ───────────────────────────────────────
function HiringBadge({ label }) {
  const cls = {
    RED_HOT: 'badge-red-hot',
    WARM: 'badge-warm',
    COOL: 'badge-cool',
    COLD: 'badge-cold',
  }[label] || 'badge-cold'
  return <span className={`badge ${cls}`}>{label?.replace('_', ' ') || '—'}</span>
}

function ConfidenceBadge({ tier }) {
  const cls = {
    VERIFIED: 'badge-verified',
    LIKELY: 'badge-likely',
    UNCERTAIN: 'badge-uncertain',
    UNVERIFIED: 'badge-unverified',
  }[tier] || 'badge-unverified'
  return <span className={`badge ${cls}`}>{tier || '—'}</span>
}

function PriorityBadge({ tier }) {
  if (tier === 'PRIORITY') return <span className="badge badge-priority">⭐ PRIORITY</span>
  if (tier === 'REVIEW') return <span className="badge badge-warm">REVIEW</span>
  if (tier === 'NURTURE') return <span className="badge badge-cool">NURTURE</span>
  return <span className="badge badge-cold">ARCHIVE</span>
}

function BuyerReadyBadge({ ready }) {
  return (
    <span className={`badge ${ready ? 'badge-verified' : 'badge-unverified'}`}>
      {ready ? 'BUYER READY' : 'NEEDS REVIEW'}
    </span>
  )
}

function QAStatusBadge({ status }) {
  const map = {
    approved: ['badge-verified', 'QA APPROVED'],
    pending_review: ['badge-likely', 'PENDING QA'],
    needs_research: ['badge-uncertain', 'NEEDS RESEARCH'],
    rejected: ['badge-unverified', 'REJECTED'],
  }
  const [cls, label] = map[status] || ['badge-cool', status || 'UNKNOWN']
  return <span className={`badge ${cls}`}>{label}</span>
}

function ScoreGauge({ value, color }) {
  const borderColor = value >= 80 ? '#22cc44' : value >= 60 ? '#d4a843' : value >= 40 ? '#ffcc00' : '#ff4444'
  return (
    <div className="score-gauge" style={{ borderColor: color || borderColor, color: color || borderColor }}>
      {value}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════
// PAGE: Dashboard
// ══════════════════════════════════════════════════════════════
function DashboardPage() {
  const [stats, setStats] = useState(null)
  const [overview, setOverview] = useState(null)
  const [pipelineStatus, setPipelineStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.getLeadStats().catch(() => null),
      api.getOverview().catch(() => null),
      api.getPipelineStatus().catch(() => null),
    ]).then(([s, o, p]) => {
      setStats(s)
      setOverview(o)
      setPipelineStatus(p)
      setLoading(false)
    })
  }, [])

  if (loading) return <div className="loading-container"><div className="spinner" />Loading dashboard...</div>

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}>
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">Real-time overview of your lead generation pipeline</p>
      </div>

      {/* KPI Cards */}
      <div className="stats-grid">
        {[
          { label: 'Total Leads', value: stats?.total || 0, icon: <Users size={20} /> },
          { label: 'Companies Tracked', value: overview?.total_companies || 0, icon: <Building2 size={20} /> },
          { label: 'Buyer-Ready Leads', value: overview?.buyer_ready_leads || 0, icon: <CheckCircle size={20} /> },
          { label: 'Pending QA', value: overview?.pending_review_leads || 0, icon: <Eye size={20} /> },
          { label: 'Today\'s Cost', value: `$${overview?.today_cost_usd?.toFixed(2) || '0.00'}`, icon: <BarChart3 size={20} />, gold: true },
        ].map((item, i) => (
          <motion.div
            key={item.label}
            className="stat-card"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
          >
            <div className={`stat-value ${item.gold ? 'gold' : ''}`}>{item.value}</div>
            <div className="stat-label">{item.label}</div>
            <div className="stat-icon">{item.icon}</div>
          </motion.div>
        ))}
      </div>

      <div className="grid-2">
        {/* Priority Distribution */}
        <div className="chart-container">
          <div className="chart-title">Lead Priority Distribution</div>
          {stats?.by_priority && (
            <Doughnut
              data={{
                labels: ['Priority', 'Review', 'Nurture', 'Archive'],
                datasets: [{
                  data: [
                    stats.by_priority.PRIORITY || 0,
                    stats.by_priority.REVIEW || 0,
                    stats.by_priority.NURTURE || 0,
                    stats.by_priority.ARCHIVE || 0,
                  ],
                  backgroundColor: ['#d4a843', '#ff9500', '#4488ff', '#444'],
                  borderWidth: 0,
                }],
              }}
              options={{
                ...chartDefaults,
                cutout: '65%',
                plugins: {
                  ...chartDefaults.plugins,
                  legend: { position: 'bottom', labels: { color: '#a0a0a0', padding: 16, usePointStyle: true } },
                },
              }}
            />
          )}
        </div>

        {/* Hiring Label Distribution */}
        <div className="chart-container">
          <div className="chart-title">Hiring Intensity Breakdown</div>
          {stats?.by_hiring_label && (
            <Bar
              data={{
                labels: ['Red Hot', 'Warm', 'Cool', 'Cold'],
                datasets: [{
                  data: [
                    stats.by_hiring_label.RED_HOT || 0,
                    stats.by_hiring_label.WARM || 0,
                    stats.by_hiring_label.COOL || 0,
                    stats.by_hiring_label.COLD || 0,
                  ],
                  backgroundColor: ['#ff4444', '#ff9500', '#4488ff', '#666'],
                  borderRadius: 6,
                  barPercentage: 0.6,
                }],
              }}
              options={{ ...chartDefaults, plugins: { ...chartDefaults.plugins, legend: { display: false } } }}
            />
          )}
        </div>
      </div>

      {/* Pipeline Status */}
      {pipelineStatus?.last_run && (
        <div className="card" style={{ marginBottom: 28 }}>
          <div className="section-title"><span className="gold-dot" />Last Pipeline Run</div>
          <div style={{ display: 'flex', gap: 40, flexWrap: 'wrap' }}>
            <div><div className="stat-label">Status</div><div style={{ color: pipelineStatus.last_run.status === 'completed' ? '#22cc44' : '#ffcc00', fontWeight: 600, textTransform: 'uppercase' }}>{pipelineStatus.last_run.status}</div></div>
            <div><div className="stat-label">Discovered</div><div style={{ fontSize: 20, fontWeight: 700 }}>{pipelineStatus.last_run.companies_discovered}</div></div>
            <div><div className="stat-label">Leads</div><div style={{ fontSize: 20, fontWeight: 700 }}>{pipelineStatus.last_run.leads_generated}</div></div>
            <div><div className="stat-label">Delivered</div><div style={{ fontSize: 20, fontWeight: 700 }}>{pipelineStatus.last_run.leads_delivered}</div></div>
            <div><div className="stat-label">Duration</div><div style={{ fontSize: 20, fontWeight: 700 }}>{pipelineStatus.last_run.duration_seconds ? `${Math.round(pipelineStatus.last_run.duration_seconds)}s` : '—'}</div></div>
          </div>
        </div>
      )}
    </motion.div>
  )
}

// ══════════════════════════════════════════════════════════════
// PAGE: Leads
// ══════════════════════════════════════════════════════════════
function LeadsPage() {
  const [leads, setLeads] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [roleFocus, setRoleFocus] = useState('engineering')
  const [priorityFilter, setPriorityFilter] = useState('')
  const [buyerReadyOnly, setBuyerReadyOnly] = useState(false)
  const [qaFilter, setQaFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [selectedLeadId, setSelectedLeadId] = useState(null)
  const [selectedLead, setSelectedLead] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const fetchLeads = () => {
    setLoading(true)
    const params = { page, per_page: 25, buyer_ready_only: buyerReadyOnly, role_focus: roleFocus }
    if (search) params.search = search
    if (priorityFilter) params.priority_tier = priorityFilter
    if (qaFilter) params.qa_status = qaFilter
    api.getLeads(params).then(data => {
      setLeads(data.leads || [])
      setTotal(data.total || 0)
      setLoading(false)
    }).catch(() => setLoading(false))
  }

  const loadLeadDetail = (leadId) => {
    setSelectedLeadId(leadId)
    setDetailLoading(true)
    api.getLead(leadId).then(data => {
      setSelectedLead(data)
      setDetailLoading(false)
    }).catch(() => {
      setSelectedLead(null)
      setDetailLoading(false)
    })
  }

  const updateLeadReview = async (leadId, nextQaStatus) => {
    await api.updateLead(leadId, { qa_status: nextQaStatus })
    if (selectedLeadId === leadId) {
      loadLeadDetail(leadId)
    }
    fetchLeads()
  }

  useEffect(() => { fetchLeads() }, [page, priorityFilter, buyerReadyOnly, qaFilter, roleFocus])

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <div className="page-header">
        <h1 className="page-title">Leads</h1>
        <p className="page-subtitle">{total} company snapshots · Sorted by buyer readiness, then hiring intensity</p>
      </div>

      <div className="filters-bar">
        <div className="filter-group">
          <span className="filter-label">Search</span>
          <input className="input" placeholder="Company name..." value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && fetchLeads()}
            style={{ width: 200 }}
          />
        </div>
        <div className="filter-group">
          <span className="filter-label">Role Focus</span>
          <select
            className="select"
            value={roleFocus}
            onChange={e => {
              setPage(1)
              setRoleFocus(e.target.value)
            }}
            style={{ width: 170 }}
          >
            {ROLE_FOCUS_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>
        <div className="filter-group">
          <span className="filter-label">Priority</span>
          <select className="select" value={priorityFilter} onChange={e => setPriorityFilter(e.target.value)} style={{ width: 140 }}>
            <option value="">All</option>
            <option value="PRIORITY">⭐ Priority</option>
            <option value="REVIEW">Review</option>
            <option value="NURTURE">Nurture</option>
            <option value="ARCHIVE">Archive</option>
          </select>
        </div>
        <label className="filter-group" style={{ gap: 8, cursor: 'pointer' }}>
          <span className="filter-label">Quality</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingBottom: 6 }}>
            <input
              type="checkbox"
              checked={buyerReadyOnly}
              onChange={e => {
                setPage(1)
                setBuyerReadyOnly(e.target.checked)
              }}
            />
            <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Only buyer-ready</span>
          </div>
        </label>
        <div className="filter-group">
          <span className="filter-label">QA</span>
          <select
            className="select"
            value={qaFilter}
            onChange={e => {
              setPage(1)
              setQaFilter(e.target.value)
            }}
            style={{ width: 170 }}
          >
            <option value="">All</option>
            <option value="approved">Approved</option>
            <option value="pending_review">Pending Review</option>
            <option value="needs_research">Needs Research</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'flex-end' }}>
          <button className="btn btn-secondary" onClick={fetchLeads}><RefreshCcw size={14} /> Refresh</button>
        </div>
      </div>

      {loading ? (
        <div className="loading-container"><div className="spinner" /></div>
      ) : leads.length === 0 ? (
        <div className="empty-state">
          <Users className="empty-state-icon" />
          <p>No leads yet. Run the pipeline to discover companies.</p>
        </div>
      ) : (
        <>
          <div className="card" style={{ padding: 0, overflow: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Why Now</th>
                  <th>Contact</th>
                  <th>Readiness</th>
                  <th>QA</th>
                  <th>Confidence</th>
                  <th>Priority</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((lead, i) => (
                  <motion.tr
                    key={lead.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: i * 0.03 }}
                    onClick={() => loadLeadDetail(lead.id)}
                    style={{ cursor: 'pointer', backgroundColor: selectedLeadId === lead.id ? 'rgba(212,168,67,0.06)' : 'transparent' }}
                  >
                    <td>
                      <div style={{ fontWeight: 600 }}>{lead.company_name}</div>
                      <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{lead.company_domain}</div>
                      {lead.proof_summary && (
                        <div style={{ color: 'var(--text-secondary)', fontSize: 12, marginTop: 6, maxWidth: 320 }}>
                          {lead.proof_summary}
                        </div>
                      )}
                    </td>
                    <td>
                      <HiringBadge label={lead.hiring_label} />
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{lead.hiring_intensity}/100</div>
                      <div style={{ marginTop: 8, fontWeight: 600 }}>{lead.role_count} roles</div>
                      <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
                        {(lead.top_roles || []).slice(0, 2).join(' · ') || 'No role titles'}
                      </div>
                    </td>
                    <td>
                      {lead.contact_name ? (
                        <>
                          <div style={{ fontWeight: 500 }}>{lead.contact_name}</div>
                          <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{lead.contact_title}</div>
                          <div style={{ color: 'var(--text-secondary)', fontSize: 11, marginTop: 6 }}>
                            {lead.contact_proof_quality || 'Unclassified contact'}
                          </div>
                        </>
                      ) : <span style={{ color: 'var(--text-muted)' }}>No named contact</span>}
                    </td>
                    <td>
                      <BuyerReadyBadge ready={lead.buyer_ready} />
                      <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 6 }}>
                        {lead.role_evidence_urls?.length || 0} role proofs · {lead.contact_source_urls?.length || 0} contact proofs
                      </div>
                      <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 6 }}>
                        Freshness: {lead.freshness_days == null ? 'unknown' : `${lead.freshness_days}d`}
                      </div>
                    </td>
                    <td><QAStatusBadge status={lead.qa_status} /></td>
                    <td>
                      <ConfidenceBadge tier={lead.confidence_tier} />
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>{lead.data_confidence}/100</div>
                    </td>
                    <td><PriorityBadge tier={lead.priority_tier} /></td>
                    <td><span className={`badge ${lead.status === 'delivered' ? 'badge-verified' : 'badge-cool'}`}>{lead.status}</span></td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card" style={{ marginTop: 20 }}>
            <div className="section-title"><span className="gold-dot" />Lead Evidence</div>
            {!selectedLeadId ? (
              <p style={{ color: 'var(--text-muted)' }}>Select a lead row to inspect proof, roles, and contact detail.</p>
            ) : detailLoading ? (
              <div className="loading-container" style={{ minHeight: 120 }}><div className="spinner" /></div>
            ) : !selectedLead ? (
              <p style={{ color: 'var(--text-muted)' }}>Could not load lead detail.</p>
            ) : (
              <div style={{ display: 'grid', gap: 18 }}>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                  <BuyerReadyBadge ready={selectedLead.scoring?.buyer_ready} />
                  <QAStatusBadge status={selectedLead.scoring?.qa_status} />
                  <HiringBadge label={selectedLead.scoring?.hiring_label} />
                  <ConfidenceBadge tier={selectedLead.scoring?.confidence_tier} />
                  <PriorityBadge tier={selectedLead.scoring?.priority_tier} />
                </div>
                <div style={{ color: 'var(--text-secondary)' }}>{selectedLead.scoring?.proof_summary || selectedLead.notes}</div>
                <div style={{ color: 'var(--text-secondary)' }}>{selectedLead.scoring?.outreach_summary || 'No outreach angle generated yet.'}</div>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <button className="btn btn-secondary" onClick={() => updateLeadReview(selectedLead.id, 'approved')}>Approve</button>
                  <button className="btn btn-secondary" onClick={() => updateLeadReview(selectedLead.id, 'pending_review')}>Needs QA</button>
                  <button className="btn btn-secondary" onClick={() => updateLeadReview(selectedLead.id, 'needs_research')}>Needs Research</button>
                  <button className="btn btn-secondary" onClick={() => updateLeadReview(selectedLead.id, 'rejected')}>Reject</button>
                </div>
                <div className="grid-2" style={{ gap: 20 }}>
                  <div>
                    <div className="stat-label" style={{ marginBottom: 8 }}>Top Roles</div>
                    {selectedLead.job_postings?.length ? selectedLead.job_postings.slice(0, 6).map((job, idx) => (
                      <div key={`${job.title}-${idx}`} style={{ padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
                        <div style={{ fontWeight: 600 }}>{job.title}</div>
                        <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{job.location || 'Unknown location'}{job.posted_date ? ` · ${job.posted_date}` : ''}</div>
                        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 6 }}>
                          {job.job_url && <a href={job.job_url} target="_blank" rel="noopener noreferrer">Job URL</a>}
                          {(job.evidence_urls || []).slice(0, 2).map((url, evidenceIdx) => (
                            <a key={`${url}-${evidenceIdx}`} href={url} target="_blank" rel="noopener noreferrer">Proof {evidenceIdx + 1}</a>
                          ))}
                        </div>
                      </div>
                    )) : <div style={{ color: 'var(--text-muted)' }}>No role-level proof yet.</div>}
                  </div>
                  <div>
                    <div className="stat-label" style={{ marginBottom: 8 }}>Contact</div>
                    {selectedLead.contact ? (
                      <div style={{ display: 'grid', gap: 10 }}>
                        <div>
                          <div style={{ fontWeight: 600 }}>{selectedLead.contact.name || 'Unnamed contact'}</div>
                          <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{selectedLead.contact.title || 'No title'}</div>
                        </div>
                        <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                          Quality: {selectedLead.contact.proof_quality || 'Unknown'} · Confidence: {selectedLead.contact.confidence || 0}/100
                        </div>
                        <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                          Verified: {selectedLead.contact.verified_at ? new Date(selectedLead.contact.verified_at).toLocaleString() : 'Not yet'}
                        </div>
                        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                          {selectedLead.contact.email && <a href={`mailto:${selectedLead.contact.email}`}><Mail size={14} style={{ verticalAlign: 'middle' }} /> {selectedLead.contact.email}</a>}
                          {selectedLead.contact.linkedin && <a href={selectedLead.contact.linkedin} target="_blank" rel="noopener noreferrer"><Linkedin size={14} style={{ verticalAlign: 'middle' }} /> LinkedIn</a>}
                        </div>
                        <div>
                          <div className="stat-label" style={{ marginBottom: 6 }}>Contact Proof Links</div>
                          {(selectedLead.contact.source_urls || []).length ? (
                            (selectedLead.contact.source_urls || []).map((url, idx) => (
                              <div key={`${url}-${idx}`} style={{ marginBottom: 4 }}>
                                <a href={url} target="_blank" rel="noopener noreferrer">{url}</a>
                              </div>
                            ))
                          ) : <div style={{ color: 'var(--text-muted)' }}>No source URLs attached.</div>}
                        </div>
                        <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                          Found on: {selectedLead.contact.found_on_date || 'Unknown'}{selectedLead.contact.generic_email_only ? ' · generic inbox only' : ''}
                        </div>
                        <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                          Company freshness: {selectedLead.scoring?.freshness_days == null ? 'unknown' : `${selectedLead.scoring.freshness_days} day(s) since last seen`}
                        </div>
                      </div>
                    ) : <div style={{ color: 'var(--text-muted)' }}>No contact attached to this lead yet.</div>}
                  </div>
                </div>
              </div>
            )}
          </div>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 12, marginTop: 20 }}>
            <button className="btn btn-ghost" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
            <span style={{ color: 'var(--text-muted)', alignSelf: 'center' }}>Page {page}</span>
            <button className="btn btn-ghost" onClick={() => setPage(p => p + 1)}>Next →</button>
          </div>
        </>
      )}
    </motion.div>
  )
}

// ══════════════════════════════════════════════════════════════
// PAGE: Search
// ══════════════════════════════════════════════════════════════
function SearchPage() {
  const [query, setQuery] = useState('')
  const [type, setType] = useState('company')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const onSearch = async () => {
    if (!query.trim()) return
    setLoading(true)
    setResult(null)
    try {
      let data
      if (type === 'company') data = await api.searchCompany(query)
      else if (type === 'contact') data = await api.searchContact(query)
      else data = await api.searchMarket(query)
      setResult(data)
    } catch (e) {
      setResult({ error: e.message })
    }
    setLoading(false)
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <div className="page-header">
        <h1 className="page-title">Search</h1>
        <p className="page-subtitle">Manually search for companies, contacts, or scan markets</p>
      </div>

      <div className="card" style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <select className="select" value={type} onChange={e => setType(e.target.value)} style={{ width: 150 }}>
            <option value="company">Company Lookup</option>
            <option value="contact">Contact Finder</option>
            <option value="market">Market Scan</option>
          </select>
          <input className="input" placeholder={type === 'market' ? 'e.g. AI/ML startups in NYC' : 'e.g. stripe.com'}
            value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && onSearch()}
            style={{ flex: 1, minWidth: 250 }}
          />
          <button className="btn btn-primary" onClick={onSearch} disabled={loading}>
            {loading ? <div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} /> : <><Search size={16} /> Search</>}
          </button>
        </div>
      </div>

      {result && !result.error && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="card">
          {result.contact && (
            <div>
              <div className="section-title"><span className="gold-dot" />Contact Found</div>
              {result.contact.found ? (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div><span className="stat-label">Name</span><div style={{ fontWeight: 600 }}>{result.contact.full_name}</div></div>
                  <div><span className="stat-label">Title</span><div>{result.contact.title}</div></div>
                  <div><span className="stat-label">LinkedIn</span><div>{result.contact.linkedin_url ? <a href={result.contact.linkedin_url} target="_blank" rel="noopener">{result.contact.linkedin_url}</a> : '—'}</div></div>
                  <div><span className="stat-label">Sources</span><div>{result.contact.enrichment_sources?.join(', ') || '—'}</div></div>
                </div>
              ) : <p style={{ color: 'var(--text-muted)' }}>No contact found.</p>}
            </div>
          )}
          {result.emails?.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <div className="section-title"><span className="gold-dot" />Email Patterns</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {result.emails.map((e, i) => (
                  <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    <Mail size={14} style={{ color: 'var(--gold)' }} />
                    <span>{e.email}</span>
                    <span className={`badge ${e.confidence === 'high' ? 'badge-verified' : e.confidence === 'medium' ? 'badge-cool' : 'badge-cold'}`}>{e.confidence}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {result.companies && (
            <div>
              <div className="section-title"><span className="gold-dot" />Found {result.total_found} Companies</div>
              <div style={{ display: 'grid', gap: 8 }}>
                {result.companies.slice(0, 10).map((c, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                    <div><span style={{ fontWeight: 600 }}>{c.company_name}</span><span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>{c.company_domain}</span></div>
                    <div style={{ color: 'var(--text-secondary)' }}>{c.industry || '—'}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </motion.div>
      )}
      {result?.error && (
        <div className="card" style={{ borderColor: 'rgba(255,68,68,0.3)' }}>
          <p style={{ color: 'var(--error)' }}><AlertCircle size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} />{result.error}</p>
        </div>
      )}
    </motion.div>
  )
}

// ══════════════════════════════════════════════════════════════
// PAGE: Agencies
// ══════════════════════════════════════════════════════════════
function AgenciesPage() {
  const [agencies, setAgencies] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', contact_email: '' })

  useEffect(() => { api.getAgencies().then(setAgencies).catch(() => {}).finally(() => setLoading(false)) }, [])

  const onCreate = async () => {
    if (!form.name.trim()) return
    await api.createAgency(form)
    const data = await api.getAgencies()
    setAgencies(data)
    setShowCreate(false)
    setForm({ name: '', contact_email: '' })
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Agencies</h1>
          <p className="page-subtitle">Manage client agencies and delivery preferences</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)}>{showCreate ? 'Cancel' : '+ Add Agency'}</button>
      </div>

      {showCreate && (
        <motion.div className="card" style={{ marginBottom: 20 }} initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
          <div style={{ display: 'flex', gap: 12 }}>
            <input className="input" placeholder="Agency Name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
            <input className="input" placeholder="Contact Email" value={form.contact_email} onChange={e => setForm({ ...form, contact_email: e.target.value })} />
            <button className="btn btn-primary" onClick={onCreate}>Create</button>
          </div>
        </motion.div>
      )}

      {loading ? (
        <div className="loading-container"><div className="spinner" /></div>
      ) : agencies.length === 0 ? (
        <div className="empty-state"><Building2 className="empty-state-icon" /><p>No agencies yet.</p></div>
      ) : (
        <div style={{ display: 'grid', gap: 16 }}>
          {agencies.map(a => (
            <motion.div key={a.id} className="card" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 600 }}>{a.name}</div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{a.contact_email || '—'} · {a.delivery_day} delivery</div>
                </div>
                <div style={{ display: 'flex', gap: 20, textAlign: 'center' }}>
                  <div><div className="stat-value" style={{ fontSize: 22 }}>{a.total_leads_sent || 0}</div><div className="stat-label">Leads Sent</div></div>
                  <div><div className="stat-value" style={{ fontSize: 22 }}>{a.max_leads_per_week}</div><div className="stat-label">Max/Week</div></div>
                  <span className={`badge ${a.status === 'active' ? 'badge-verified' : 'badge-cold'}`} style={{ alignSelf: 'center' }}>{a.status}</span>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </motion.div>
  )
}

// ══════════════════════════════════════════════════════════════
// PAGE: Pipeline
// ══════════════════════════════════════════════════════════════
function PipelinePage() {
  const [status, setStatus] = useState(null)
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [roleFocus, setRoleFocus] = useState('engineering')
  const [selectedRunId, setSelectedRunId] = useState(null)
  const [selectedRunPreview, setSelectedRunPreview] = useState(null)
  const [selectedRunPreviewLoading, setSelectedRunPreviewLoading] = useState(false)
  const [selectedRunPanel, setSelectedRunPanel] = useState('discovered')
  const [logs, setLogs] = useState([])
  const logEndRef = useRef(null)

  const fetchState = () => {
    Promise.all([
      api.getPipelineStatus().catch(() => null),
      api.getPipelineRuns().catch(() => []),
    ]).then(([s, r]) => { setStatus(s); setRuns(r); setLoading(false) })
  }

  useEffect(() => { fetchState() }, [])

  useEffect(() => {
    if (!status?.running) return undefined
    const interval = setInterval(() => {
      fetchState()
      if (selectedRunId) {
        loadRunPreview(selectedRunId, selectedRunPanel, false)
      }
    }, 10000)
    return () => clearInterval(interval)
  }, [status?.running, selectedRunId, selectedRunPanel])

  // Auto-scroll logs
  useEffect(() => {
    if (logEndRef.current) logEndRef.current.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  // Stream pipeline logs if running
  useEffect(() => {
    let es = null;
    if (status?.running) {
      es = api.getPipelineStream();
      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          setLogs(prev => [...prev, data]);
          
          const message = data.message || '';
          if (
            message.includes('completed in') ||
            message.includes('Pipeline stopped by user') ||
            message.includes('Pipeline crashed') ||
            message.includes('Pipeline failed to start')
          ) {
             setTimeout(fetchState, 1500); // refresh full state when completed
          }
        } catch (err) {}
      };
      es.onerror = () => { es.close(); };
    } else {
      setLogs([]); // Clear logs when not running
    }
    return () => { if (es) es.close(); };
  }, [status?.running]);

  const startRun = async () => {
    setStarting(true)
    const selectedRoleLabel = ROLE_FOCUS_OPTIONS.find(([value]) => value === roleFocus)?.[1] || 'Engineering'
    setLogs([{
      timestamp: new Date().toISOString(),
      stage: 'system',
      message: `Initializing pipeline for ${selectedRoleLabel} roles...`,
      level: 'info',
    }])
    try {
      await api.startPipeline({ role_focus: roleFocus })
      const s = await api.getPipelineStatus()
      setStatus(s)
      setSelectedRunId(null)
      setSelectedRunPreview(null)
    } catch (e) {
      alert(e.message)
      setLogs([])
    }
    setStarting(false)
  }

  const stopRun = async () => {
    setStopping(true)
    try {
      await api.stopPipeline()
      setLogs(prev => [
        ...prev,
        {
          timestamp: new Date().toISOString(),
          stage: 'system',
          message: 'Stop requested. Waiting for the current stage to halt...',
          level: 'warning',
        },
      ])
      const s = await api.getPipelineStatus()
      setStatus(s)
    } catch (e) {
      alert(e.message)
    }
    setStopping(false)
  }

  const loadRunPreview = async (runId, panel = 'discovered', showSpinner = true) => {
    setSelectedRunId(runId)
    setSelectedRunPanel(panel)
    if (showSpinner) setSelectedRunPreviewLoading(true)
    try {
      const data = await api.getRunPreview(runId)
      setSelectedRunPreview(data)
    } catch (e) {
      if (showSpinner) alert(e.message)
      setSelectedRunPreview(null)
    }
    if (showSpinner) setSelectedRunPreviewLoading(false)
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Pipeline</h1>
          <p className="page-subtitle">Run and monitor the lead generation pipeline</p>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <select
            className="select"
            value={roleFocus}
            onChange={e => setRoleFocus(e.target.value)}
            disabled={starting || stopping || status?.running}
            style={{ minWidth: 180 }}
          >
            {ROLE_FOCUS_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
          {status?.running && status?.supports_background_jobs !== false && (
            <button
              className="btn btn-secondary"
              onClick={stopRun}
              disabled={stopping || !status?.can_stop}
              style={{
                borderColor: 'rgba(255, 68, 68, 0.4)',
                color: stopping ? 'var(--text-muted)' : 'var(--error)',
              }}
            >
              {stopping ? <div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} /> : <><XCircle size={16} /> Stop Pipeline</>}
            </button>
          )}
          <button
            className="btn btn-primary"
            onClick={startRun}
            disabled={starting || status?.running || stopping || status?.supports_background_jobs === false}
          >
            {starting ? (
              <div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
            ) : (
              <>
                <Play size={16} /> {status?.supports_background_jobs === false ? 'Unavailable on Vercel' : status?.running ? 'Running...' : 'Start Pipeline'}
              </>
            )}
          </button>
        </div>
      </div>

      {status?.warning && (
        <div
          className="card"
          style={{
            marginBottom: 20,
            borderColor: 'rgba(255, 149, 0, 0.35)',
            background: 'rgba(255, 149, 0, 0.04)',
          }}
        >
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
            <AlertCircle size={18} style={{ color: '#ff9500', marginTop: 2, flexShrink: 0 }} />
            <div>
              <div style={{ fontWeight: 700, marginBottom: 6 }}>Pipeline host limitation</div>
              <div style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                {status.warning}
              </div>
            </div>
          </div>
        </div>
      )}

      {status?.running && (
        <motion.div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 20 }}
          initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
          
          <div style={{ backgroundColor: '#161618', borderBottom: '1px solid #2a2a2c', padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
            <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
            <span style={{ fontWeight: 600, color: 'var(--gold)', fontSize: 13 }}>LIVE CONSOLE</span>
          </div>
          
          <div style={{ backgroundColor: '#0a0a0b', padding: '16px', maxHeight: 300, overflowY: 'auto', fontFamily: 'monospace', fontSize: 13, lineHeight: 1.6 }}>
             {logs.length === 0 ? (
               <div style={{ color: '#555' }}>Awaiting logs...</div>
             ) : (
               logs.map((log, i) => {
                 let color = '#ccc';
                 if (log.level === 'error') color = 'var(--error)';
                 if (log.level === 'success') color = '#22cc44';
                 if (log.stage === 'system') color = 'var(--gold)';
                 
                 return (
                   <div key={i} style={{ display: 'flex', gap: 12, marginBottom: 4 }}>
                     <span style={{ color: '#555', minWidth: 65 }}>{new Date(log.timestamp).toLocaleTimeString([], { hour12: false })}</span>
                     <span style={{ color: '#888', minWidth: 80, textTransform: 'uppercase', fontSize: 11, paddingTop: 2 }}>[{log.stage}]</span>
                     <span style={{ color }}>{log.message}</span>
                   </div>
                 );
               })
             )}
             <div ref={logEndRef} />
          </div>
        </motion.div>
      )}

      <div className="section-title"><span className="gold-dot" />Run History</div>
      {runs.length === 0 ? (
        <div className="empty-state"><Clock className="empty-state-icon" /><p>No pipeline runs yet.</p></div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Focus</th>
                <th>Status</th>
                <th>Discovered</th>
                <th>Leads</th>
                <th>Delivered</th>
                <th>Cost</th>
                <th>Errors</th>
                <th>Duration</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {runs.map(r => (
                <tr key={r.id}>
                  <td style={{ fontWeight: 600 }}>#{r.id}</td>
                  <td>{r.run_type}</td>
                  <td>{ROLE_FOCUS_OPTIONS.find(([value]) => value === (r.target_role_family || 'engineering'))?.[1] || r.target_role_family || 'Engineering'}</td>
                  <td>
                    <span className={`badge ${
                      r.status === 'completed'
                        ? 'badge-verified'
                        : r.status === 'running'
                          ? 'badge-cool'
                          : r.status === 'cancelled'
                            ? 'badge-uncertain'
                            : 'badge-unverified'
                    }`}>
                      {r.status}
                    </span>
                  </td>
                  <td>
                    <button
                      className="btn btn-ghost"
                      onClick={() => loadRunPreview(r.id, 'discovered')}
                      style={{ padding: 0, minHeight: 'auto', color: 'var(--gold)' }}
                    >
                      {r.companies_discovered}
                    </button>
                  </td>
                  <td>
                    <button
                      className="btn btn-ghost"
                      onClick={() => loadRunPreview(r.id, 'leads')}
                      style={{ padding: 0, minHeight: 'auto', color: 'var(--gold)' }}
                    >
                      {r.leads_generated}
                    </button>
                  </td>
                  <td>{r.leads_delivered}</td>
                  <td>${(r.openai_cost_usd || 0).toFixed(2)}</td>
                  <td style={{ color: r.error_count > 0 ? 'var(--error)' : 'var(--text-muted)' }}>{r.error_count}</td>
                  <td>{r.duration_seconds ? `${Math.round(r.duration_seconds)}s` : '—'}</td>
                  <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{r.started_at ? new Date(r.started_at).toLocaleDateString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedRunId && (
        <div className="card" style={{ marginTop: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div className="section-title" style={{ marginBottom: 0 }}>
              <span className="gold-dot" />Run #{selectedRunId} Preview
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button className="btn btn-ghost" onClick={() => loadRunPreview(selectedRunId, selectedRunPanel)}>
                <RefreshCcw size={14} /> Refresh
              </button>
              <button className="btn btn-ghost" onClick={() => { setSelectedRunId(null); setSelectedRunPreview(null) }}>Close</button>
            </div>
          </div>

          {selectedRunPreview && (
            <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
              <button
                className={`btn ${selectedRunPanel === 'discovered' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setSelectedRunPanel('discovered')}
              >
                Discovered Companies ({selectedRunPreview.discovered_total || 0})
              </button>
              <button
                className={`btn ${selectedRunPanel === 'leads' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setSelectedRunPanel('leads')}
              >
                Lead Snapshots ({selectedRunPreview.leads_total || 0})
              </button>
              {selectedRunPreview.run?.status === 'running' && (
                <span className="badge badge-cool" style={{ alignSelf: 'center' }}>AUTO REFRESHING</span>
              )}
            </div>
          )}

          {selectedRunPreviewLoading ? (
            <div className="loading-container"><div className="spinner" /></div>
          ) : !selectedRunPreview ? (
            <div style={{ color: 'var(--text-muted)' }}>No preview data is available for this run yet.</div>
          ) : selectedRunPanel === 'discovered' ? (
            (selectedRunPreview.discovered_companies || []).length === 0 ? (
              <div style={{ color: 'var(--text-muted)' }}>No discovered companies are available for this run yet.</div>
            ) : (
              <div style={{ overflow: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Company</th>
                      <th>Roles Seen</th>
                      <th>Contact</th>
                      <th>Sources</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedRunPreview.discovered_companies.map((company) => (
                      <tr key={company.company_id}>
                        <td>
                          <div style={{ fontWeight: 600 }}>{company.company_name}</div>
                          <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{company.company_domain}</div>
                        </td>
                        <td>
                          <div style={{ fontWeight: 600 }}>{company.role_count} roles</div>
                          <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                            {(company.top_roles || []).slice(0, 2).join(' · ') || 'No role titles'}
                          </div>
                        </td>
                        <td>
                          {company.contact_name ? (
                            <>
                              <div style={{ fontWeight: 500 }}>{company.contact_name}</div>
                              <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{company.contact_title}</div>
                            </>
                          ) : (
                            <span style={{ color: 'var(--text-muted)' }}>No named contact yet</span>
                          )}
                        </td>
                        <td>
                          <div style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                            {(company.sources || []).join(' · ') || 'Unknown source'}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          ) : (
            (selectedRunPreview.leads || []).length === 0 ? (
              <div style={{ color: 'var(--text-muted)' }}>No lead snapshots were saved for this run yet.</div>
            ) : (
            <div style={{ overflow: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>Roles</th>
                    <th>Contact</th>
                    <th>Confidence</th>
                    <th>Priority</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedRunPreview.leads.map((lead) => (
                    <tr key={lead.id}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{lead.company_name}</div>
                        <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{lead.company_domain}</div>
                      </td>
                      <td>
                        <div style={{ fontWeight: 600 }}>{lead.role_count} roles</div>
                        <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                          {(lead.top_roles || []).slice(0, 2).join(' · ') || 'No role titles'}
                        </div>
                      </td>
                      <td>
                        {lead.contact_name ? (
                          <>
                            <div style={{ fontWeight: 500 }}>{lead.contact_name}</div>
                            <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{lead.contact_title}</div>
                          </>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>No named contact</span>
                        )}
                      </td>
                      <td>
                        <ConfidenceBadge tier={lead.confidence_tier} />
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>{lead.data_confidence}/100</div>
                      </td>
                      <td><PriorityBadge tier={lead.priority_tier} /></td>
                      <td><span className={`badge ${lead.status === 'delivered' ? 'badge-verified' : 'badge-cool'}`}>{lead.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            )
          )}
        </div>
      )}
    </motion.div>
  )
}

// ══════════════════════════════════════════════════════════════
// PAGE: Analytics
// ══════════════════════════════════════════════════════════════
function AnalyticsPage() {
  const [distributions, setDistributions] = useState(null)
  const [costs, setCosts] = useState(null)
  const [industries, setIndustries] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.getDistributions().catch(() => null),
      api.getCostBreakdown().catch(() => null),
      api.getIndustries().catch(() => null),
    ]).then(([d, c, i]) => {
      setDistributions(d)
      setCosts(c)
      setIndustries(i)
      setLoading(false)
    })
  }, [])

  if (loading) return <div className="loading-container"><div className="spinner" /></div>

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <div className="page-header">
        <h1 className="page-title">Analytics</h1>
        <p className="page-subtitle">Score distributions, industry breakdown, and cost analysis</p>
      </div>

      <div className="grid-2">
        {distributions?.hiring_intensity && (
          <div className="chart-container">
            <div className="chart-title">Hiring Intensity Distribution</div>
            <Bar
              data={{
                labels: distributions.hiring_intensity.labels,
                datasets: [{
                  label: 'Leads',
                  data: distributions.hiring_intensity.values,
                  backgroundColor: 'rgba(212, 168, 67, 0.6)',
                  borderColor: '#d4a843',
                  borderWidth: 1,
                  borderRadius: 4,
                }],
              }}
              options={{ ...chartDefaults, plugins: { ...chartDefaults.plugins, legend: { display: false } } }}
            />
          </div>
        )}

        {distributions?.data_confidence && (
          <div className="chart-container">
            <div className="chart-title">Data Confidence Distribution</div>
            <Bar
              data={{
                labels: distributions.data_confidence.labels,
                datasets: [{
                  label: 'Leads',
                  data: distributions.data_confidence.values,
                  backgroundColor: 'rgba(34, 204, 68, 0.5)',
                  borderColor: '#22cc44',
                  borderWidth: 1,
                  borderRadius: 4,
                }],
              }}
              options={{ ...chartDefaults, plugins: { ...chartDefaults.plugins, legend: { display: false } } }}
            />
          </div>
        )}
      </div>

      <div className="grid-2">
        {industries?.industries?.length > 0 && (
          <div className="chart-container">
            <div className="chart-title">Top Industries</div>
            <Doughnut
              data={{
                labels: industries.industries.map(i => i.name),
                datasets: [{
                  data: industries.industries.map(i => i.count),
                  backgroundColor: ['#d4a843', '#ff9500', '#4488ff', '#22cc44', '#ff4444', '#9944ff', '#ff44aa', '#44cccc', '#8888ff', '#cccc44'],
                  borderWidth: 0,
                }],
              }}
              options={{ cutout: '55%', plugins: { legend: { position: 'right', labels: { color: '#a0a0a0', padding: 10 } } } }}
            />
          </div>
        )}

        {costs?.stages?.length > 0 && (
          <div className="chart-container">
            <div className="chart-title">Cost Breakdown (30d) — Total: ${costs.total_usd}</div>
            <Doughnut
              data={{
                labels: costs.stages.map(s => s.name),
                datasets: [{
                  data: costs.stages.map(s => s.cost_usd),
                  backgroundColor: ['#d4a843', '#ff9500', '#4488ff', '#22cc44', '#ff4444'],
                  borderWidth: 0,
                }],
              }}
              options={{ cutout: '60%', plugins: { legend: { position: 'right', labels: { color: '#a0a0a0', padding: 10 } } } }}
            />
          </div>
        )}
      </div>
    </motion.div>
  )
}

// ══════════════════════════════════════════════════════════════
// PAGE: Notifications
// ══════════════════════════════════════════════════════════════
function NotificationsPage() {
  const [notifs, setNotifs] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { api.getNotifications().then(setNotifs).catch(() => {}).finally(() => setLoading(false)) }, [])

  const onMarkAllRead = async () => {
    await api.markAllRead()
    const data = await api.getNotifications()
    setNotifs(data)
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Notifications</h1>
          <p className="page-subtitle">System alerts, pipeline updates, and hot lead notifications</p>
        </div>
        <button className="btn btn-secondary" onClick={onMarkAllRead}><CheckCircle size={14} /> Mark All Read</button>
      </div>

      {loading ? (
        <div className="loading-container"><div className="spinner" /></div>
      ) : notifs.length === 0 ? (
        <div className="empty-state"><Bell className="empty-state-icon" /><p>No notifications yet.</p></div>
      ) : (
        notifs.map(n => (
          <motion.div key={n.id} className="notif-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            style={{ opacity: n.is_read ? 0.6 : 1 }}>
            <div className={`notif-dot ${n.severity}`} />
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600 }}>{n.title}</div>
              <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 2 }}>{n.message}</div>
              <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 6 }}>
                {n.created_at ? new Date(n.created_at).toLocaleString() : '—'}
              </div>
            </div>
            {!n.is_read && (
              <button className="btn btn-ghost" onClick={async () => {
                await api.markRead(n.id)
                setNotifs(notifs.map(x => x.id === n.id ? { ...x, is_read: true } : x))
              }}>Mark Read</button>
            )}
          </motion.div>
        ))
      )}
    </motion.div>
  )
}

// ══════════════════════════════════════════════════════════════
// PAGE: Settings
// ══════════════════════════════════════════════════════════════
function SettingsPage() {
  const [settings, setSettings] = useState([])
  const [loading, setLoading] = useState(true)
  const [edits, setEdits] = useState({})

  useEffect(() => { api.getSettings().then(setSettings).catch(() => {}).finally(() => setLoading(false)) }, [])

  const onSave = async () => {
    const updates = Object.entries(edits).map(([key, value]) => ({ key, value }))
    if (updates.length === 0) return
    await api.updateSettings(updates)
    const data = await api.getSettings()
    setSettings(data)
    setEdits({})
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">Pipeline configuration, API limits, and system preferences</p>
        </div>
        <button className="btn btn-primary" onClick={onSave} disabled={Object.keys(edits).length === 0}>Save Changes</button>
      </div>

      {loading ? (
        <div className="loading-container"><div className="spinner" /></div>
      ) : (
        <div className="card">
          <div style={{ display: 'grid', gap: 14 }}>
            {settings.map(s => (
              <div key={s.key} style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 12, alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{s.key}</div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 11.5 }}>{s.description}</div>
                </div>
                <input className="input" value={edits[s.key] !== undefined ? edits[s.key] : s.value}
                  onChange={e => setEdits({ ...edits, [s.key]: e.target.value })}
                  style={{ maxWidth: 400 }}
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  )
}

// ══════════════════════════════════════════════════════════════
// SIDEBAR
// ══════════════════════════════════════════════════════════════
function Sidebar() {
  const [unread, setUnread] = useState(0)

  useEffect(() => {
    api.getUnreadCount().then(d => setUnread(d.unread)).catch(() => {})
    const interval = setInterval(() => {
      api.getUnreadCount().then(d => setUnread(d.unread)).catch(() => {})
    }, 30000)
    return () => clearInterval(interval)
  }, [])

  const navItems = [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/leads', label: 'Leads', icon: Users },
    { path: '/search', label: 'Search', icon: Search },
    { path: '/pipeline', label: 'Pipeline', icon: Zap },
    { path: '/agencies', label: 'Agencies', icon: Building2 },
    { path: '/analytics', label: 'Analytics', icon: BarChart3 },
    { path: '/notifications', label: 'Notifications', icon: Bell, badge: unread },
    { path: '/settings', label: 'Settings', icon: Settings },
  ]

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">CS</div>
        <div>
          <div className="sidebar-title">ConnectorOS</div>
          <div className="sidebar-subtitle">Scout v2.0</div>
        </div>
      </div>
      <nav className="sidebar-nav">
        {navItems.map(item => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <item.icon className="nav-icon" />
            {item.label}
            {item.badge > 0 && <span className="nav-badge">{item.badge}</span>}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}

// ══════════════════════════════════════════════════════════════
// APP
// ══════════════════════════════════════════════════════════════
export default function App() {
  return (
    <Router>
      <div className="app-layout">
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/leads" element={<LeadsPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/pipeline" element={<PipelinePage />} />
            <Route path="/agencies" element={<AgenciesPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}
