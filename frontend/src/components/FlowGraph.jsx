import React, { useMemo, useState, useEffect, useRef } from 'react';
import { forceSimulation, forceLink, forceManyBody, forceCenter } from 'd3-force';

export default function FlowGraph({ graphData, selectedAccountId, onSelectAccount }) {
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [hoveredNode, setHoveredNode] = useState(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const containerRef = useRef(null);

  const startTime = graphData?.start_time || 0;
  const asOf = graphData?.as_of || 0;
  const duration = Math.max(1, asOf - startTime);

  // Initialize/reset replay time when graphData changes
  useEffect(() => {
    if (graphData?.as_of) {
      setCurrentTime(graphData.as_of);
      setIsPlaying(false);
    }
  }, [graphData?.start_time, graphData?.as_of]);

  // Replay playback loop: finishes in ~12 seconds
  useEffect(() => {
    let timerId;
    if (isPlaying) {
      const intervalMs = 50;
      const step = (duration * intervalMs) / 12000;

      timerId = setInterval(() => {
        setCurrentTime((prev) => {
          const next = prev + step;
          if (next >= asOf) {
            setIsPlaying(false);
            return asOf;
          }
          return next;
        });
      }, intervalMs);
    }
    return () => {
      if (timerId) clearInterval(timerId);
    };
  }, [isPlaying, duration, asOf]);

  const width = 760;
  const height = 520;

  // Maximum values for normalization
  const maxBalance = useMemo(() => {
    if (!graphData?.nodes || graphData.nodes.length === 0) return 1;
    return Math.max(...graphData.nodes.map((n) => n.balance || 0), 1);
  }, [graphData]);

  const maxAmount = useMemo(() => {
    if (!graphData?.edges || graphData.edges.length === 0) return 1;
    return Math.max(...graphData.edges.map((e) => e.amount || 0), 1);
  }, [graphData]);

  const getNodeRadius = (balance) => {
    const sqrtBal = Math.sqrt(Math.max(0, balance || 0));
    const sqrtMax = Math.sqrt(maxBalance);
    const r = 7 + 19 * (sqrtBal / (sqrtMax || 1));
    return Math.max(6, Math.min(26, r));
  };

  const getNodeColor = (taintedMax, balance) => {
    const share = balance > 0 ? Math.min(1.0, Math.max(0.0, (taintedMax || 0) / balance)) : 0.0;
    // Interpolate from pale pink (#FEE2E2) to deep crimson red (#991B1B)
    const r = Math.round(254 + (153 - 254) * share);
    const g = Math.round(226 + (27 - 226) * share);
    const b = Math.round(226 + (27 - 226) * share);
    return `rgb(${r}, ${g}, ${b})`;
  };

  const getEdgeWidth = (amount) => {
    const sqrtAmt = Math.sqrt(Math.max(0, amount || 0));
    const sqrtMax = Math.sqrt(maxAmount);
    return Math.max(1.2, Math.min(6.5, 1.2 + 4.8 * (sqrtAmt / (sqrtMax || 1))));
  };

  // Run d3-force deterministically on initial load per graphData
  const { nodes, links } = useMemo(() => {
    if (!graphData?.nodes || graphData.nodes.length === 0) {
      return { nodes: [], links: [] };
    }

    const n = graphData.nodes.length;
    const circleRadius = Math.min(width, height) * 0.35;

    // Seed positions deterministically on a circle
    const simNodes = graphData.nodes.map((node, i) => {
      const angle = (2 * Math.PI * i) / Math.max(1, n);
      return {
        ...node,
        x: width / 2 + circleRadius * Math.cos(angle),
        y: height / 2 + circleRadius * Math.sin(angle),
      };
    });

    const simLinks = graphData.edges.map((e) => ({
      ...e,
      source: e.src,
      target: e.dst,
    }));

    const simulation = forceSimulation(simNodes)
      .force(
        'link',
        forceLink(simLinks)
          .id((d) => d.id)
          .distance(75)
      )
      .force('charge', forceManyBody().strength(-220))
      .force('center', forceCenter(width / 2, height / 2));

    // Run synchronously to fixed equilibrium
    simulation.tick(160);
    simulation.stop();

    // Clamp within padding
    simNodes.forEach((node) => {
      node.x = Math.max(38, Math.min(width - 38, node.x));
      node.y = Math.max(38, Math.min(height - 38, node.y));
    });

    return { nodes: simNodes, links: simLinks };
  }, [graphData]);

  // Connected nodes up to currentTime
  const activeNodeIds = useMemo(() => {
    const set = new Set();
    links.forEach((l) => {
      if (l.time <= currentTime) {
        const sId = typeof l.source === 'object' ? l.source.id : l.source;
        const tId = typeof l.target === 'object' ? l.target.id : l.target;
        set.add(sId);
        set.add(tId);
      }
    });
    return set;
  }, [links, currentTime]);

  const handleMouseMove = (e, node) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    setTooltipPos({
      x: e.clientX - rect.left + 15,
      y: e.clientY - rect.top - 10,
    });
    setHoveredNode(node);
  };

  const handleMouseLeave = () => {
    setHoveredNode(null);
  };

  const currentHrs = Math.max(0, (currentTime - startTime) / 60);
  const totalHrs = Math.max(0, (asOf - startTime) / 60);

  return (
    <div className="card" style={{ padding: '20px', position: 'relative' }} ref={containerRef}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
        <div>
          <h3 style={{ fontSize: '1.25rem' }}>Money-Flow Graph</h3>
          <p style={{ fontSize: '0.82rem', color: 'var(--muted)' }}>
            Showing transactions up to {currentHrs.toFixed(1)} hrs since scam start
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--ink)' }}>
            Time: +{currentHrs.toFixed(1)}h / {totalHrs.toFixed(1)}h
          </span>
        </div>
      </div>

      {/* SVG Canvas */}
      <div style={{ position: 'relative', overflow: 'hidden', background: '#FCFBF9', borderRadius: '12px', border: '1px solid var(--border-light)' }}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          style={{ width: '100%', height: 'auto', display: 'block', maxHeight: '520px' }}
        >
          <defs>
            <marker
              id="arrow-marker"
              viewBox="0 -5 10 10"
              refX="10"
              refY="0"
              markerWidth="6"
              markerHeight="6"
              orient="auto"
            >
              <path d="M0,-4L8,0L0,4" fill="#64748B" />
            </marker>
          </defs>

          {/* Edges */}
          <g className="edges">
            {links.map((link, idx) => {
              const source = link.source;
              const target = link.target;
              if (!source || !target || typeof source.x !== 'number' || typeof target.x !== 'number') {
                return null;
              }

              const isVisible = link.time <= currentTime;
              const dx = target.x - source.x;
              const dy = target.y - source.y;
              const dist = Math.sqrt(dx * dx + dy * dy) || 1;
              const targetR = getNodeRadius(target.balance);
              const sourceR = getNodeRadius(source.balance);

              const startX = source.x + (dx / dist) * (sourceR + 2);
              const startY = source.y + (dy / dist) * (sourceR + 2);
              const endX = target.x - (dx / dist) * (targetR + 6);
              const endY = target.y - (dy / dist) * (targetR + 6);

              return (
                <line
                  key={`edge-${idx}`}
                  x1={startX}
                  y1={startY}
                  x2={endX}
                  y2={endY}
                  stroke="#64748B"
                  strokeWidth={getEdgeWidth(link.amount)}
                  strokeOpacity={isVisible ? 0.75 : 0.05}
                  markerEnd={isVisible ? 'url(#arrow-marker)' : undefined}
                  style={{ transition: 'stroke-opacity 0.25s ease' }}
                />
              );
            })}
          </g>

          {/* Nodes */}
          <g className="nodes">
            {nodes.map((node) => {
              const r = getNodeRadius(node.balance);
              const isSelected = selectedAccountId === node.id;
              const isConnected = activeNodeIds.has(node.id);
              const fillColor = getNodeColor(node.tainted_max, node.balance);
              const opacity = isConnected ? 1.0 : 0.25;

              return (
                <g
                  key={`node-${node.id}`}
                  transform={`translate(${node.x}, ${node.y})`}
                  style={{ cursor: 'pointer', transition: 'opacity 0.25s ease' }}
                  opacity={opacity}
                  onClick={() => onSelectAccount && onSelectAccount(node.id)}
                  onMouseMove={(e) => handleMouseMove(e, node)}
                  onMouseLeave={handleMouseLeave}
                >
                  {/* Selected outline */}
                  {isSelected && (
                    <circle
                      r={r + 5}
                      fill="none"
                      stroke="var(--teal)"
                      strokeWidth={3}
                      strokeDasharray="4 2"
                    />
                  )}

                  {/* Main Node Circle */}
                  <circle
                    r={r}
                    fill={fillColor}
                    stroke={isSelected ? 'var(--teal)' : '#64748B'}
                    strokeWidth={isSelected ? 2.5 : 1.2}
                  />

                  {/* Node label if tainted_max > 1 */}
                  {node.tainted_max > 1.0 && (
                    <text
                      y={-r - 5}
                      textAnchor="middle"
                      fontSize="10px"
                      fontWeight="600"
                      fill="var(--ink)"
                      style={{ pointerEvents: 'none' }}
                    >
                      {node.id}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>

        {/* Floating Tooltip */}
        {hoveredNode && (
          <div
            style={{
              position: 'absolute',
              left: `${tooltipPos.x}px`,
              top: `${tooltipPos.y}px`,
              background: '#FFFFFF',
              border: '1px solid #D9D5CB',
              borderRadius: '8px',
              padding: '8px 12px',
              pointerEvents: 'none',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.1)',
              fontSize: '0.8rem',
              zIndex: 20,
              maxWidth: '240px',
            }}
          >
            <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--ink)' }}>
              {hoveredNode.id}
            </div>
            <div style={{ color: 'var(--muted)', textTransform: 'capitalize' }}>
              Type: {hoveredNode.type}
            </div>
            <div style={{ marginTop: '4px' }}>
              <strong>Balance:</strong> ₹{Number(hoveredNode.balance || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
            </div>
            <div>
              <strong>Tainted:</strong> ₹{Number(hoveredNode.tainted_min || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })} .. ₹{Number(hoveredNode.tainted_max || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
            </div>
            <div>
              <strong>Priority S:</strong> {Number(hoveredNode.S || 0).toFixed(4)}
            </div>
          </div>
        )}
      </div>

      {/* Replay Controls */}
      <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            style={{
              padding: '6px 14px',
              borderRadius: '8px',
              background: isPlaying ? 'var(--amber)' : 'var(--teal)',
              color: '#FFFFFF',
              fontWeight: 600,
              fontSize: '0.85rem',
            }}
          >
            {isPlaying ? '⏸ Pause' : '▶ Play'}
          </button>
          <button
            onClick={() => {
              setCurrentTime(startTime);
              setIsPlaying(true);
            }}
            style={{
              padding: '6px 14px',
              borderRadius: '8px',
              background: '#E2DFD8',
              color: 'var(--ink)',
              fontWeight: 600,
              fontSize: '0.85rem',
            }}
          >
            ↺ Restart
          </button>

          <input
            type="range"
            min={startTime}
            max={asOf}
            step={(asOf - startTime) / 100 || 1}
            value={currentTime}
            onChange={(e) => {
              setCurrentTime(parseFloat(e.target.value));
              setIsPlaying(false);
            }}
            style={{ flex: 1, cursor: 'pointer', accentColor: 'var(--teal)' }}
          />

          <span style={{ fontSize: '0.82rem', fontWeight: 600, minWidth: '95px', textAlign: 'right' }}>
            +{currentHrs.toFixed(1)} hrs
          </span>
        </div>
      </div>
    </div>
  );
}
