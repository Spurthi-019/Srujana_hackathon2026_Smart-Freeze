import React, { useState, useEffect } from 'react';
import FlowGraph from './components/FlowGraph';
import './App.css';

export default function App() {
  const [scams, setScams] = useState([]);
  const [selectedScam, setSelectedScam] = useState('');
  const [delay, setDelay] = useState(60);
  const [logLam, setLogLam] = useState(-1.30103); // default 0.05
  const [graphData, setGraphData] = useState(null);
  const [decisions, setDecisions] = useState([]);
  const [selectedAccountId, setSelectedAccountId] = useState(null);

  const [loadingScams, setLoadingScams] = useState(true);
  const [loadingData, setLoadingData] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

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

    const graphPromise = fetch(`/api/graph?scam_id=${selectedScam}&delay=${delay}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Graph API returned ${res.status}`);
        return res.json();
      });

    const decPromise = fetch(`/api/decisions?scam_id=${selectedScam}&delay=${delay}&lam=${lam}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Decisions API returned ${res.status}`);
        return res.json();
      });

    Promise.all([graphPromise, decPromise])
      .then(([gData, dData]) => {
        setGraphData(gData);
        setDecisions(dData);
        // Default selection to first review account if none selected
        if (dData.length > 0 && !selectedAccountId) {
          setSelectedAccountId(dData[0].account_id);
        }
      })
      .catch((err) => {
        setErrorMsg(`Error loading case data: ${err.message}. Is the API running on port 8000?`);
      })
      .finally(() => {
        setLoadingData(false);
      });
  }, [selectedScam, delay, lam]);

  const selectedDecision = decisions.find((d) => d.account_id === selectedAccountId);

  return (
    <div className="app-container">
      {/* Top Banner */}
      <header className="top-banner">
        <div className="banner-content">
          <span>⚠️</span>
          <span>SIMULATED DATA - prototype, a human approves every action</span>
        </div>
        <div style={{ fontSize: '0.8rem', opacity: 0.9 }}>
          Draft RBI Directions Model
        </div>
      </header>

      {/* Main Body */}
      <main className="app-body">
        {/* Left Sidebar */}
        <aside className="card sidebar">
          <div>
            <h2 className="sidebar-title">Smart Freeze</h2>
            <p style={{ fontSize: '0.82rem', color: 'var(--muted)' }}>
              Targeted hold & lien prototype
            </p>
          </div>

          {/* Scam Selector */}
          <div className="control-group">
            <label className="control-label">Scam Incident</label>
            <select
              className="select-input"
              value={selectedScam}
              onChange={(e) => {
                setSelectedScam(e.target.value);
                setSelectedAccountId(null);
              }}
              disabled={loadingScams || scams.length === 0}
            >
              {scams.map((s) => (
                <option key={s.scam_id} value={s.scam_id}>
                  {s.scam_id} (Stolen: ₹{Number(s.total_stolen || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })})
                </option>
              ))}
            </select>
          </div>

          {/* Delay Selector */}
          <div className="control-group">
            <label className="control-label">Decision Delay</label>
            <select
              className="select-input"
              value={delay}
              onChange={(e) => setDelay(parseInt(e.target.value, 10))}
            >
              <option value={60}>60 min after scam start</option>
              <option value={180}>180 min after scam start</option>
              <option value={300}>300 min after scam start</option>
            </select>
          </div>

          {/* Lambda Slider */}
          <div className="control-group">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label className="control-label">Trade-off λ</label>
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--teal)' }}>
                λ = {lam.toFixed(4)}
              </span>
            </div>
            <p style={{ fontSize: '0.75rem', color: 'var(--muted)', margin: '2px 0 6px 0' }}>
              max recovery &lt;—&gt; min harm
            </p>
            <input
              type="range"
              min={-3.0}
              max={-0.60206}
              step={0.05}
              value={logLam}
              onChange={(e) => setLogLam(parseFloat(e.target.value))}
              style={{ width: '100%', accentColor: 'var(--teal)', cursor: 'pointer' }}
            />
            <div className="slider-values">
              <span>0.001 (Aggressive)</span>
              <span>0.250 (Protective)</span>
            </div>
          </div>
        </aside>

        {/* Main Content Area */}
        <section className="main-area">
          {errorMsg ? (
            <div className="error-banner">
              <strong>Connection Error</strong>
              <p>{errorMsg}</p>
              <button
                onClick={() => window.location.reload()}
                style={{
                  padding: '6px 14px',
                  borderRadius: '8px',
                  background: '#991B1B',
                  color: '#FFFFFF',
                  marginTop: '8px',
                }}
              >
                Retry
              </button>
            </div>
          ) : loadingData && !graphData ? (
            <div className="card" style={{ padding: '60px', textAlign: 'center', color: 'var(--muted)' }}>
              Loading scam flow graph...
            </div>
          ) : (
            graphData && (
              <FlowGraph
                graphData={graphData}
                selectedAccountId={selectedAccountId}
                onSelectAccount={setSelectedAccountId}
              />
            )
          )}
        </section>

        {/* Right Panel: Accounts to Review & Card Placeholder */}
        <aside className="right-panel">
          {/* Review List */}
          <div className="card" style={{ padding: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <h3 style={{ fontSize: '1.15rem' }}>Accounts to review</h3>
              <span style={{ fontSize: '0.8rem', color: 'var(--muted)', fontWeight: 600 }}>
                {decisions.length} flagged
              </span>
            </div>

            {decisions.length === 0 ? (
              <div style={{ padding: '24px 8px', textAlign: 'center', color: 'var(--muted)', fontSize: '0.85rem' }}>
                No candidate accounts with tainted money &gt; ₹1.00.
              </div>
            ) : (
              <div className="review-list">
                {decisions.map((item) => {
                  const isSelected = selectedAccountId === item.account_id;
                  const heldAmt =
                    item.action === 'timed_hold'
                      ? item.balance
                      : item.action === 'lien'
                      ? item.lien_amount
                      : item.action === 'lien_cap'
                      ? item.lien_amount + item.cap_share * Math.max(0, item.balance - item.lien_amount)
                      : 0;

                  return (
                    <div
                      key={item.account_id}
                      className={`account-item ${isSelected ? 'selected' : ''}`}
                      onClick={() => setSelectedAccountId(item.account_id)}
                    >
                      <div className="account-info">
                        <span className="account-id">{item.account_id}</span>
                        <span className="account-type">{item.type}</span>
                      </div>
                      <div className="account-action">
                        <span className={`badge badge-${item.action}`}>
                          {item.action}
                        </span>
                        <span className="account-held">
                          ₹{Number(heldAmt || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Account Card Placeholder */}
          <div className="card placeholder-card">
            <h4 style={{ fontSize: '1.05rem', color: 'var(--ink)' }}>Account Details</h4>
            {selectedDecision ? (
              <div>
                <p style={{ fontWeight: 600, fontSize: '0.95rem' }}>
                  Account: <code>{selectedDecision.account_id}</code> ({selectedDecision.type})
                </p>
                <p style={{ fontSize: '0.82rem', color: 'var(--muted)', marginTop: '4px' }}>
                  Balance: ₹{Number(selectedDecision.balance || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                </p>
                <div style={{ marginTop: '10px' }}>
                  <span className={`badge badge-${selectedDecision.action}`}>
                    {selectedDecision.action}
                  </span>
                </div>
                <div
                  style={{
                    marginTop: '16px',
                    padding: '12px',
                    borderRadius: '8px',
                    background: '#F6F4EF',
                    fontSize: '0.8rem',
                    color: 'var(--muted)',
                    border: '1px dashed #D9D5CB',
                  }}
                >
                  ℹ️ Full Account Card (tracing breakdown, priority score details, harm assessment, and clear-me flow) comes in the next step.
                </div>
              </div>
            ) : (
              <p style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
                Click an account from the graph or review list above to inspect.
              </p>
            )}
          </div>
        </aside>
      </main>
    </div>
  );
}
