import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  ShieldAlert,
  SlidersHorizontal,
  Search,
  Filter,
  TrendingDown,
  Lock,
  Users,
  AlertTriangle,
  FileSpreadsheet,
  Layers,
  Sparkles,
} from 'lucide-react';
import FlowGraph from './components/FlowGraph';
import AccountCard from './components/AccountCard';
import { formatMoney, formatMoneyExact } from './utils/format';
import './App.css';

const ACTION_SEVERITY_ORDER = {
  timed_hold: 4,
  lien_cap: 3,
  lien: 2,
  none: 1,
};

export default function App() {
  const [scams, setScams] = useState([]);
  const [selectedScam, setSelectedScam] = useState('');
  const [delay, setDelay] = useState(60);
  const [logLam, setLogLam] = useState(-1.30103); // default 0.05
  const [graphData, setGraphData] = useState(null);
  const [decisions, setDecisions] = useState([]);
  const [selectedAccountId, setSelectedAccountId] = useState(null);
  const [auditLog, setAuditLog] = useState([]);

  // Top Tabs: 'case' | 'tradeoff'
  const [activeTab, setActiveTab] = useState('case');

  // Review list controls: search & filter chip
  const [searchQuery, setSearchQuery] = useState('');
  const [actionFilter, setActionFilter] = useState('all');

  const [loadingScams, setLoadingScams] = useState(true);
  const [loadingData, setLoadingData] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  const detailSectionRef = useRef(null);

  const lam = parseFloat(Math.pow(10, logLam).toFixed(4));

  // Fetch scams list on mount
  useEffect(() => {
    setLoadingScams(true);
    fetch('/api/scams')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setScams(data);
        if (data.length > 0) {
          setSelectedScam(data[0].scam_id);
        }
        setErrorMsg(null);
      })
      .catch((err) => {
        setErrorMsg(`Failed to connect to backend: ${err.message}. Is the API running on port 8000?`);
      })
      .finally(() => {
        setLoadingScams(false);
      });
  }, []);

  // Fetch graph and decisions whenever scam, delay, or lam changes
  useEffect(() => {
    if (!selectedScam) return;

    setLoadingData(true);
    setErrorMsg(null);

    const graphPromise = fetch(`/api/graph?scam_id=${selectedScam}&delay=${delay}`).then((res) => {
      if (!res.ok) throw new Error(`Graph API returned ${res.status}`);
      return res.json();
    });

    const decPromise = fetch(`/api/decisions?scam_id=${selectedScam}&delay=${delay}&lam=${lam}`).then((res) => {
      if (!res.ok) throw new Error(`Decisions API returned ${res.status}`);
      return res.json();
    });

    Promise.all([graphPromise, decPromise])
      .then(([gData, dData]) => {
        setGraphData(gData);
        setDecisions(dData);

        // Auto-select the highest-priority flagged account on first load or when switching
        if (dData.length > 0) {
          const sorted = [...dData].sort((a, b) => {
            const sevDiff = (ACTION_SEVERITY_ORDER[b.action] || 0) - (ACTION_SEVERITY_ORDER[a.action] || 0);
            if (sevDiff !== 0) return sevDiff;
            return (b.tainted_max || 0) - (a.tainted_max || 0);
          });

          // If current selection is not in list, auto-select highest priority
          const currentExists = dData.some((d) => d.account_id === selectedAccountId);
          if (!selectedAccountId || !currentExists) {
            setSelectedAccountId(sorted[0].account_id);
          }
        } else {
          setSelectedAccountId(null);
        }
      })
      .catch((err) => {
        setErrorMsg(`Error loading case data: ${err.message}. Is the API running on port 8000?`);
      })
      .finally(() => {
        setLoadingData(false);
      });
  }, [selectedScam, delay, lam]);

  // Selected scam object
  const currentScam = useMemo(() => {
    return scams.find((s) => s.scam_id === selectedScam) || {};
  }, [scams, selectedScam]);

  // KPI Calculations
  const totalStolen = currentScam.total_stolen || 0;
  const accountsFlaggedCount = decisions.filter((d) => (d.tainted_max || 0) > 1.0).length;
  const holdCount = decisions.filter((d) => d.action === 'timed_hold').length;

  const totalHeldAmount = useMemo(() => {
    return decisions.reduce((acc, d) => {
      if (d.action === 'timed_hold') return acc + (d.balance || 0);
      if (d.action === 'lien') return acc + Math.min(d.balance || 0, d.lien_amount || 0);
      if (d.action === 'lien_cap') {
        const base = Math.min(d.balance || 0, d.lien_amount || 0);
        return acc + base + (d.cap_share || 0) * Math.max(0, (d.balance || 0) - base);
      }
      return acc;
    }, 0);
  }, [decisions]);

  // Filtered & Sorted Review Accounts
  const sortedAndFilteredDecisions = useMemo(() => {
    return decisions
      .filter((d) => {
        if (searchQuery.trim() !== '') {
          const matchId = d.account_id.toLowerCase().includes(searchQuery.toLowerCase().trim());
          if (!matchId) return false;
        }
        if (actionFilter !== 'all' && d.action !== actionFilter) {
          return false;
        }
        return true;
      })
      .sort((a, b) => {
        const sevA = ACTION_SEVERITY_ORDER[a.action] || 0;
        const sevB = ACTION_SEVERITY_ORDER[b.action] || 0;
        if (sevA !== sevB) return sevB - sevA; // High severity first
        return (b.tainted_max || 0) - (a.tainted_max || 0); // High taint first
      });
  }, [decisions, searchQuery, actionFilter]);

  const handleAccountClick = (id) => {
    setSelectedAccountId(id);
    if (detailSectionRef.current) {
      detailSectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <div className="app-container">
      {/* 1. Top Bar */}
      <header className="top-bar">
        <div className="top-bar-left">
          <div className="logo-badge">
            <ShieldAlert size={20} className="logo-icon" />
            <span className="logo-text">Smart Freeze</span>
          </div>
          <span className="logo-subtitle">
            Proportionate freezing decision support
          </span>
        </div>

        <div className="top-bar-center">
          <div className="simulated-data-pill">
            <span className="pill-dot" />
            <span>SIMULATED DATA — a human approves every action</span>
          </div>
        </div>

        <div className="top-bar-right">
          <div className="nav-tabs">
            <button
              type="button"
              className={`nav-tab ${activeTab === 'case' ? 'active' : ''}`}
              onClick={() => setActiveTab('case')}
            >
              Case view
            </button>
            <button
              type="button"
              className={`nav-tab ${activeTab === 'tradeoff' ? 'active' : ''}`}
              onClick={() => setActiveTab('tradeoff')}
            >
              Trade-off
            </button>
          </div>
        </div>
      </header>

      {/* 2. Controls Toolbar Directly Under Top Bar */}
      <section className="controls-toolbar">
        {/* Scam Incident Select */}
        <div className="toolbar-group">
          <label className="toolbar-label">Scam Incident</label>
          <select
            className="toolbar-select"
            value={selectedScam}
            onChange={(e) => {
              setSelectedScam(e.target.value);
              setSelectedAccountId(null);
            }}
            disabled={loadingScams || scams.length === 0}
          >
            {scams.map((s) => (
              <option key={s.scam_id} value={s.scam_id}>
                {s.scam_id} (Stolen: {formatMoney(s.total_stolen)})
              </option>
            ))}
          </select>
        </div>

        {/* Decision Delay Segmented Control */}
        <div className="toolbar-group">
          <label className="toolbar-label">Decision Delay</label>
          <div className="segmented-control">
            {[60, 180, 300].map((d) => (
              <button
                key={d}
                type="button"
                className={`segment-btn ${delay === d ? 'active' : ''}`}
                onClick={() => setDelay(d)}
              >
                {d} min
              </button>
            ))}
          </div>
        </div>

        {/* Lambda Trade-off Slider */}
        <div className="toolbar-group toolbar-slider-group">
          <div className="slider-label-row">
            <span className="toolbar-label">
              Trade-off λ: <strong className="text-teal tabular-nums">λ = {lam.toFixed(4)}</strong>
            </span>
            <span className="slider-subtext">max recovery &lt;—&gt; min harm</span>
          </div>
          <div className="slider-input-row">
            <span className="slider-bound">0.001</span>
            <input
              type="range"
              min={-3.0}
              max={-0.60206}
              step={0.05}
              value={logLam}
              onChange={(e) => setLogLam(parseFloat(e.target.value))}
              className="toolbar-slider"
            />
            <span className="slider-bound">0.250</span>
          </div>
        </div>
      </section>

      {/* Main Tab Content */}
      {activeTab === 'tradeoff' ? (
        <main className="tab-placeholder-main">
          <div className="card tradeoff-placeholder-card">
            <SlidersHorizontal size={40} className="text-teal" />
            <h3>Policy Trade-Off Analysis</h3>
            <p className="placeholder-text">
              Coming next: Multi-policy evaluation comparing Blanket Freeze, Pure FIFO, Pure LIBR,
              and Smart Freeze frontier across recovery vs clean-money harm metrics.
            </p>
            <div className="tradeoff-info-badge">
              Active Trade-off Parameter: λ = {lam.toFixed(4)} at Delay {delay} min
            </div>
            <button
              type="button"
              className="return-case-btn"
              onClick={() => setActiveTab('case')}
            >
              Return to Case View
            </button>
          </div>
        </main>
      ) : (
        <main className="case-view-container">
          {/* Error Banner */}
          {errorMsg && (
            <div className="error-banner">
              <AlertTriangle size={20} className="text-red" />
              <div className="error-content">
                <strong>Connection or Data Error</strong>
                <p>{errorMsg}</p>
              </div>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="retry-btn"
              >
                Retry
              </button>
            </div>
          )}

          {/* 3. KPI Strip: 4 Cards from existing data */}
          <section className="kpi-strip">
            <div className="card kpi-card">
              <div className="kpi-icon-wrap kpi-icon-red">
                <ShieldAlert size={18} />
              </div>
              <div className="kpi-content">
                <span className="kpi-label">Total Stolen</span>
                <span className="kpi-value tabular-nums" title={formatMoneyExact(totalStolen)}>
                  {formatMoney(totalStolen)}
                </span>
                <span className="kpi-subtext">Incident {selectedScam}</span>
              </div>
            </div>

            <div className="card kpi-card">
              <div className="kpi-icon-wrap kpi-icon-amber">
                <Users size={18} />
              </div>
              <div className="kpi-content">
                <span className="kpi-label">Accounts Flagged</span>
                <span className="kpi-value tabular-nums">{accountsFlaggedCount}</span>
                <span className="kpi-subtext">Tainted max &gt; ₹1.00</span>
              </div>
            </div>

            <div className="card kpi-card">
              <div className="kpi-icon-wrap kpi-icon-blue">
                <Lock size={18} />
              </div>
              <div className="kpi-content">
                <span className="kpi-label">Recommended for Hold</span>
                <span className="kpi-value tabular-nums">{holdCount}</span>
                <span className="kpi-subtext">Timed hold auto-releases in 24h</span>
              </div>
            </div>

            <div className="card kpi-card">
              <div className="kpi-icon-wrap kpi-icon-teal">
                <TrendingDown size={18} />
              </div>
              <div className="kpi-content">
                <span className="kpi-label">Sure Part Held</span>
                <span className="kpi-value tabular-nums" title={formatMoneyExact(totalHeldAmount)}>
                  {formatMoney(totalHeldAmount)}
                </span>
                <span className="kpi-subtext">Targeted lock on sure taint</span>
              </div>
            </div>
          </section>

          {/* 4. Main Row, Equal Height (approx 560px): Graph (2/3) + Accounts to review (1/3) */}
          <section className="main-row">
            {/* Graph Card (approx 2/3 width) */}
            <div className="graph-column">
              {loadingData && !graphData ? (
                <div className="card graph-skeleton">
                  <div className="spinner" />
                  <p>Synthesizing money-flow network graph...</p>
                </div>
              ) : (
                graphData && (
                  <FlowGraph
                    graphData={graphData}
                    selectedAccountId={selectedAccountId}
                    onSelectAccount={handleAccountClick}
                  />
                )
              )}
            </div>

            {/* Accounts to Review Card (approx 1/3 width) */}
            <div className="review-column">
              <div className="card review-card">
                <div className="review-card-header">
                  <div className="review-title-group">
                    <h4 className="review-title">Accounts to review</h4>
                    <span className="review-count-badge tabular-nums">
                      {sortedAndFilteredDecisions.length} / {decisions.length}
                    </span>
                  </div>

                  {/* Search Box */}
                  <div className="search-box-wrap">
                    <Search size={14} className="search-icon" />
                    <input
                      type="text"
                      placeholder="Search account ID..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="search-input"
                    />
                    {searchQuery && (
                      <button
                        type="button"
                        onClick={() => setSearchQuery('')}
                        className="search-clear-btn"
                      >
                        ✕
                      </button>
                    )}
                  </div>

                  {/* Action Filter Chips */}
                  <div className="filter-chips">
                    {[
                      { id: 'all', label: 'All' },
                      { id: 'timed_hold', label: 'Hold' },
                      { id: 'lien_cap', label: 'Lien+Cap' },
                      { id: 'lien', label: 'Lien' },
                      { id: 'none', label: 'None' },
                    ].map((chip) => (
                      <button
                        key={chip.id}
                        type="button"
                        className={`filter-chip ${actionFilter === chip.id ? 'active' : ''} chip-${chip.id}`}
                        onClick={() => setActionFilter(chip.id)}
                      >
                        {chip.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Scrollable List */}
                <div className="review-scroll-list">
                  {sortedAndFilteredDecisions.length === 0 ? (
                    <div className="empty-review-list">
                      No matching accounts found for query "{searchQuery}".
                    </div>
                  ) : (
                    sortedAndFilteredDecisions.map((item) => {
                      const isSelected = selectedAccountId === item.account_id;
                      const heldAmt =
                        item.action === 'timed_hold'
                          ? item.balance
                          : item.action === 'lien'
                          ? Math.min(item.balance, item.lien_amount)
                          : item.action === 'lien_cap'
                          ? Math.min(item.balance, item.lien_amount) +
                            item.cap_share * Math.max(0, item.balance - item.lien_amount)
                          : 0;

                      return (
                        <div
                          key={item.account_id}
                          className={`account-list-item ${isSelected ? 'selected' : ''}`}
                          onClick={() => handleAccountClick(item.account_id)}
                        >
                          <div className="item-left">
                            <span className="item-account-id">{item.account_id}</span>
                            <span className="item-account-type">{item.type}</span>
                          </div>

                          <div className="item-right">
                            <span className={`badge badge-${item.action}`}>
                              {item.action}
                            </span>
                            <span
                              className="item-held-val tabular-nums"
                              title={`Held: ${formatMoneyExact(heldAmt)} (Balance: ${formatMoneyExact(item.balance)})`}
                            >
                              {formatMoney(heldAmt)}
                            </span>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </div>
          </section>

          {/* 5. Account Detail Section: Full-width underneath main row */}
          <div ref={detailSectionRef} className="account-detail-anchor">
            <AccountCard
              accountId={selectedAccountId}
              scamId={selectedScam}
              delay={delay}
              lam={lam}
              auditLog={auditLog}
              onApproveRelease={(entry) => setAuditLog((prev) => [entry, ...prev])}
            />
          </div>
        </main>
      )}
    </div>
  );
}
