import React, { useEffect, useRef } from 'react';

export default function ArtifactCard({ part }) {
  const { artifact_type, content } = part;

  if (!content) return null;

  if (artifact_type === 'url') {
    // Basic image/video rendering
    const isVideo = content.match(/\.(mp4|webm|ogg)$/i);
    return (
      <div style={{ marginTop: 10, border: '1px solid var(--sb-line)', borderRadius: 4, overflow: 'hidden' }}>
        {isVideo ? (
          <video src={content} controls style={{ width: '100%', display: 'block' }} />
        ) : (
          <img src={content} alt="Artifact" style={{ width: '100%', display: 'block' }} />
        )}
      </div>
    );
  }

  if (artifact_type === 'table') {
    // If it looks like HTML, render it as HTML. Otherwise, wrap in pre.
    const isHtml = content.trim().startsWith('<') && content.includes('>');
    
    return (
      <div 
        style={{ 
          marginTop: 10, 
          border: '1px solid var(--sb-line)', 
          borderRadius: 4, 
          overflow: 'auto',
          background: 'var(--sb-card)',
          padding: 12,
          fontSize: 12,
          fontFamily: 'var(--sb-font-mono)'
        }}
      >
        {isHtml ? (
          <div dangerouslySetInnerHTML={{ __html: content }} />
        ) : (
          <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>
            {content}
          </pre>
        )}
      </div>
    );
  }

  if (artifact_type === 'charts') {
    return <ChartArtifact configStr={content} />;
  }

  return null;
}

function ChartArtifact({ configStr }) {
  const canvasRef = useRef(null);
  const chartInstanceRef = useRef(null);

  useEffect(() => {
    let config;
    try {
      config = JSON.parse(configStr);
    } catch (e) {
      console.error('Failed to parse chart config', e);
      return;
    }

    const renderChart = () => {
      if (!canvasRef.current) return;
      if (chartInstanceRef.current) {
        chartInstanceRef.current.destroy();
      }
      chartInstanceRef.current = new window.Chart(canvasRef.current, config);
    };

    if (window.Chart) {
      renderChart();
    } else {
      let script = document.querySelector('script[src="https://cdn.jsdelivr.net/npm/chart.js"]');
      if (!script) {
        script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
        document.head.appendChild(script);
      }
      script.addEventListener('load', renderChart);
    }

    return () => {
      if (chartInstanceRef.current) {
        chartInstanceRef.current.destroy();
      }
    };
  }, [configStr]);

  return (
    <div style={{ marginTop: 10, border: '1px solid var(--sb-line)', borderRadius: 4, background: 'var(--sb-card)', padding: 12 }}>
      <canvas ref={canvasRef} style={{ width: '100%', maxHeight: 300 }} />
    </div>
  );
}
