import React, { useMemo, useState, useEffect, useRef, useCallback } from 'react';
import { forceSimulation, forceLink, forceManyBody, forceCenter } from 'd3-force';
import { Play, Pause, RotateCcw, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';
import { formatMoney, formatMoneyExact } from '../utils/format';

export default function FlowGraph({ graphData, selectedAccountId, onSelectAccount }) {
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [hoveredNode, setHoveredNode] = useState(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  // Pan & Zoom state
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 });

  const containerRef = useRef(null);
  const svgRef = useRef(null);

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

  const width = 840;
  const height = 500;

  // Maximum values for normalization
  const maxBalance = useMemo(() => {
    if (!graphData?.nodes || graphData.nodes.length === 0) return 1;
    return Math.max(...graphData.nodes.map((n) => n.balance || 0), 1);
  }, [graphData]);

  const maxAmount = useMemo(() => {
    if (!graphData?.edges || graphData.edges.length === 0) return 1;
    return Math.max(...graphData.edges.map((e) => e.amount || 0), 1);
  }, [graphData]);

  const getNodeRadius = useCallback(
    (balance) => {
      const sqrtBal = Math.sqrt(Math.max(0, balance || 0));
      const sqrtMax = Math.sqrt(maxBalance);
      const r = 8 + 20 * (sqrtBal / (sqrtMax || 1));
      return Math.max(7, Math.min(28, r));
    },
    [maxBalance]
  );

  const getNodeColor = (taintedMax, balance) => {
    const share = balance > 0 ? Math.min(1.0, Math.max(0.0, (taintedMax || 0) / balance)) : 0.0;
    // Dark theme interpolation: from cool slate (#334155) to vibrant red/rose (#F43F5E)
    const r = Math.round(51 + (244 - 51) * share);
    const g = Math.round(65 + (63 - 65) * share);
    const b = Math.round(85 + (94 - 85) * share);
    return `rgb(${r}, ${g}, ${b})`;
  };

  const getEdgeWidth = (amount) => {
    const sqrtAmt = Math.sqrt(Math.max(0, amount || 0));
    const sqrtMax = Math.sqrt(maxAmount);
    return Math.max(1.5, Math.min(6.5, 1.5 + 4.5 * (sqrtAmt / (sqrtMax || 1))));
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
          .distance(85)
      )
      .force('charge', forceManyBody().strength(-240))
      .force('center', forceCenter(width / 2, height / 2));

    // Run synchronously to fixed equilibrium
    simulation.tick(180);
    simulation.stop();

    // Clamp within padding
    simNodes.forEach((node) => {
      node.x = Math.max(45, Math.min(width - 45, node.x));
      node.y = Math.max(45, Math.min(height - 45, node.y));
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

  // Mouse wheel zoom
  const handleWheel = (e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
    setZoom((prev) => Math.min(2.8, Math.max(0.6, prev * zoomFactor)));
  };

  // Pan handlers
  const handleMouseDown = (e) => {
    // Only pan if clicking canvas, not node
    if (e.target.tagName === 'circle' || e.target.tagName === 'text') return;
    setIsPanning(true);
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      panX: pan.x,
      panY: pan.y,
    };
  };

  const handleMouseMoveCanvas = (e) => {
    if (isPanning) {
      const dx = e.clientX - dragStartRef.current.x;
      const dy = e.clientY - dragStartRef.current.y;
      setPan({
        x: dragStartRef.current.panX + dx,
        y: dragStartRef.current.panY + dy,
      });
    }
  };

  const handleMouseUpCanvas = () => {
    setIsPanning(false);
  };

  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  const handleNodeMouseMove = (e, node) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    setTooltipPos({
      x: e.clientX - rect.left + 14,
      y: e.clientY - rect.top - 10,
    });
    setHoveredNode(node);
  };

  const handleNodeMouseLeave = () => {
    setHoveredNode(null);
  };

  const currentHrs = Math.max(0, (currentTime - startTime) / 60);

  return (
    <div className="card graph-card" ref={containerRef}>
      {/* Graph Card Header */}
      <div className="graph-header">
        <div>
          <h3 className="graph-title">Money-Flow Network</h3>
          <p className="graph-subtitle">
            Forensic graph showing scam dispersal across recipient accounts
          </p>
        </div>

        {/* Zoom Controls & Time Badge */}
        <div className="graph-header-controls">
          <div className="zoom-btn-group">
            <button
              type="button"
              className="zoom-btn"
              onClick={() => setZoom((z) => Math.min(2.8, z * 1.15))}
              title="Zoom In"
            >
              <ZoomIn size={14} />
            </button>
            <button
              type="button"
              className="zoom-btn"
              onClick={() => setZoom((z) => Math.max(0.6, z * 0.85))}
              title="Zoom Out"
            >
              <ZoomOut size={14} />
            </button>
            <button
              type="button"
              className="zoom-btn"
              onClick={resetView}
              title="Reset View (100%)"
            >
              <Maximize2 size={13} />
            </button>
          </div>

          <span className="time-badge tabular-nums">
            Hour {currentHrs.toFixed(1)} after scam start
          </span>
        </div>
      </div>

      {/* SVG Canvas Container */}
      <div
        className="graph-canvas-wrapper"
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMoveCanvas}
        onMouseUp={handleMouseUpCanvas}
        onMouseLeave={handleMouseUpCanvas}
        style={{ cursor: isPanning ? 'grabbing' : 'grab' }}
      >
        <svg
          ref={svgRef}
          viewBox={`0 0 ${width} ${height}`}
          className="graph-svg"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            {/* Subtle Grid Pattern for Dark Control Room Canvas */}
            <pattern
              id="graph-grid"
              width="32"
              height="32"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 32 0 L 0 0 0 32"
                fill="none"
                stroke="#18233B"
                strokeWidth="0.8"
              />
            </pattern>

            {/* Glowing red node filter */}
            <filter id="glow-red" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="3.5" result="coloredBlur" />
              <feMerge>
                <feMergeNode in="coloredBlur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Teal marker arrow */}
            <marker
              id="arrow-marker"
              viewBox="0 -5 10 10"
              refX="10"
              refY="0"
              markerWidth="6"
              markerHeight="6"
              orient="auto"
            >
              <path d="M0,-4L8,0L0,4" fill="#60A5FA" />
            </marker>
          </defs>

          {/* Grid Background */}
          <rect width="100%" height="100%" fill="url(#graph-grid)" />

          {/* Pan & Zoom Master Group */}
          <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
            {/* Edges Layer */}
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
                    stroke={isVisible ? '#60A5FA' : '#334155'}
                    strokeWidth={getEdgeWidth(link.amount)}
                    strokeOpacity={isVisible ? 0.75 : 0.08}
                    strokeDasharray={isPlaying && isVisible ? '6 4' : undefined}
                    className={isPlaying && isVisible ? 'animated-edge-pulse' : ''}
                    markerEnd={isVisible ? 'url(#arrow-marker)' : undefined}
                    style={{ transition: 'stroke-opacity 0.25s ease' }}
                  />
                );
              })}
            </g>

            {/* Nodes Layer */}
            <g className="nodes">
              {nodes.map((node) => {
                const r = getNodeRadius(node.balance);
                const isSelected = selectedAccountId === node.id;
                const isConnected = activeNodeIds.has(node.id);
                const taintShare =
                  node.balance > 0
                    ? Math.min(1.0, Math.max(0.0, (node.tainted_max || 0) / node.balance))
                    : 0.0;
                const fillColor = getNodeColor(node.tainted_max, node.balance);
                const opacity = isConnected ? 1.0 : 0.2;

                return (
                  <g
                    key={`node-${node.id}`}
                    transform={`translate(${node.x}, ${node.y})`}
                    style={{ cursor: 'pointer', transition: 'opacity 0.25s ease' }}
                    opacity={opacity}
                    onClick={() => onSelectAccount && onSelectAccount(node.id)}
                    onMouseMove={(e) => handleNodeMouseMove(e, node)}
                    onMouseLeave={handleNodeMouseLeave}
                  >
                    {/* Red Glow Aura proportional to taint share */}
                    {taintShare > 0.05 && (
                      <circle
                        r={r + 4 + taintShare * 8}
                        fill={`rgba(244, 63, 94, ${0.12 + 0.38 * taintShare})`}
                        style={{ pointerEvents: 'none' }}
                      />
                    )}

                    {/* Teal ring on selected node */}
                    {isSelected && (
                      <>
                        <circle
                          r={r + 8}
                          fill="none"
                          stroke="rgba(45, 212, 191, 0.25)"
                          strokeWidth={5}
                          style={{ pointerEvents: 'none' }}
                        />
                        <circle
                          r={r + 4}
                          fill="none"
                          stroke="var(--teal)"
                          strokeWidth={2.5}
                          style={{ pointerEvents: 'none' }}
                        />
                      </>
                    )}

                    {/* Main Node Circle */}
                    <circle
                      r={r}
                      fill={fillColor}
                      stroke={isSelected ? 'var(--teal)' : '#475569'}
                      strokeWidth={isSelected ? 2.5 : 1.2}
                      filter={taintShare > 0.4 ? 'url(#glow-red)' : undefined}
                    />

                    {/* Node label if tainted_max > 1 */}
                    {node.tainted_max > 1.0 && (
                      <text
                        y={-r - 5}
                        textAnchor="middle"
                        fontSize="10px"
                        fontWeight="600"
                        fill="var(--text)"
                        style={{ pointerEvents: 'none', userSelect: 'none' }}
                      >
                        {node.id}
                      </text>
                    )}
                  </g>
                );
              })}
            </g>
          </g>
        </svg>

        {/* Legend for node colour and size */}
        <div className="graph-legend">
          <div className="legend-section">
            <span className="legend-header">Taint Share:</span>
            <div className="legend-gradient-bar">
              <span className="legend-dot" style={{ background: '#334155' }} />
              <div className="gradient-track" />
              <span className="legend-dot" style={{ background: '#F43F5E', boxShadow: '0 0 6px #F43F5E' }} />
            </div>
            <div className="legend-labels">
              <span>0% clean</span>
              <span>100% tainted</span>
            </div>
          </div>

          <div className="legend-section">
            <span className="legend-header">Node Size:</span>
            <div className="legend-size-dots">
              <span className="size-dot small" title="Low balance" />
              <span className="size-dot med" title="Medium balance" />
              <span className="size-dot large" title="High balance" />
              <span className="legend-size-label">Account Balance</span>
            </div>
          </div>
        </div>

        {/* Styled Floating Tooltip Card */}
        {hoveredNode && (
          <div
            className="graph-tooltip-card"
            style={{
              left: `${tooltipPos.x}px`,
              top: `${tooltipPos.y}px`,
            }}
          >
            <div className="tooltip-header">
              <span className="tooltip-id">{hoveredNode.id}</span>
              <span className="tooltip-type">{hoveredNode.type}</span>
            </div>
            <div className="tooltip-row">
              <span className="tooltip-label">Balance:</span>
              <span className="tooltip-val tabular-nums" title={formatMoneyExact(hoveredNode.balance)}>
                {formatMoney(hoveredNode.balance)}
              </span>
            </div>
            <div className="tooltip-row">
              <span className="tooltip-label">Tainted range:</span>
              <span
                className="tooltip-val text-amber tabular-nums"
                title={`${formatMoneyExact(hoveredNode.tainted_min)} to ${formatMoneyExact(hoveredNode.tainted_max)}`}
              >
                {formatMoney(hoveredNode.tainted_min)} .. {formatMoney(hoveredNode.tainted_max)}
              </span>
            </div>
            <div className="tooltip-row">
              <span className="tooltip-label">Investigation S:</span>
              <span className="tooltip-val text-teal tabular-nums">
                {Number(hoveredNode.S || 0).toFixed(4)}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Replay Controls Docked at Bottom */}
      <div className="replay-dock">
        <button
          type="button"
          onClick={() => setIsPlaying(!isPlaying)}
          className={`replay-btn ${isPlaying ? 'btn-pause' : 'btn-play'}`}
          title={isPlaying ? 'Pause replay' : 'Play transaction sequence'}
        >
          {isPlaying ? <Pause size={15} /> : <Play size={15} />}
          <span>{isPlaying ? 'Pause' : 'Play'}</span>
        </button>

        <button
          type="button"
          onClick={() => {
            setCurrentTime(startTime);
            setIsPlaying(true);
          }}
          className="replay-btn btn-restart"
          title="Restart replay from scam start"
        >
          <RotateCcw size={14} />
          <span>Restart</span>
        </button>

        <div className="time-slider-wrap">
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
            className="replay-slider"
          />
        </div>

        <span className="replay-time-label tabular-nums">
          Hour {currentHrs.toFixed(1)} after scam start
        </span>
      </div>
    </div>
  );
}
