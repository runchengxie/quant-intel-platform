import { useEffect, useRef, useState } from 'react';
import { loadChart, toOption } from '../lib/chart-data.mjs';

export default function ChartIsland({ reportId, chartKey }) {
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState('');
  const container = useRef(null);

  useEffect(() => {
    if (!expanded) return undefined;
    let active = true;
    let instance;
    let observer;
    (async () => {
      try {
        const report = await loadChart(reportId);
        const card = report.charts.find((item) => item.key === chartKey);
        if (!card || !['ok', 'degraded'].includes(card.status) || !card.points?.length) {
          throw new Error('该图暂无可展示的已审核数据');
        }
        const { initChart } = await import('../lib/chart-engine.mjs');
        if (!active || !container.current) return;
        instance = initChart(container.current);
        instance.setOption(toOption(card));
        observer = new ResizeObserver(() => instance?.resize());
        observer.observe(container.current);
      } catch {
        if (active) setError('交互图暂不可用；请查看下方静态数值与来源。');
      }
    })();
    return () => {
      active = false;
      observer?.disconnect();
      instance?.dispose();
    };
  }, [expanded, reportId, chartKey]);

  return <div className="chart-interaction">
    <button type="button" className="chart-open" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
      {expanded ? '收起交互图' : '展开交互图'}
    </button>
    {expanded && <div className="chart-drawing">
      {error && <p role="status">{error}</p>}
      <div ref={container} className="chart-canvas" role="img" aria-label={`${chartKey} 图形；原始值、观测日和来源见下方表格`} />
    </div>}
  </div>;
}
