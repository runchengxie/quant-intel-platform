import { useEffect, useRef, useState } from 'react';
import type { EChartsOption } from 'echarts';
import { chartUnits, loadChart, toOption } from '../lib/chart-data.ts';

interface ChartIslandProps {
  reportId: string;
  chartKey: string;
}

interface ChartInstance {
  setOption: (option: EChartsOption) => void;
  resize: () => void;
  dispose: () => void;
}

export default function ChartIsland({ reportId, chartKey }: ChartIslandProps) {
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState('');
  const [units, setUnits] = useState<string[]>([]);
  const [selectedUnit, setSelectedUnit] = useState('');
  const container = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!expanded) return undefined;
    setError('');
    let active = true;
    let instance: ChartInstance | undefined;
    let observer: ResizeObserver | undefined;
    (async () => {
      try {
        const report = await loadChart(reportId);
        const card = report.charts.find((item) => item.key === chartKey);
        if (!card || !['ok', 'degraded'].includes(card.status) || !card.points?.length) {
          throw new Error('该图暂无可展示的已审核数据');
        }
        const { initChart } = await import('../lib/chart-engine.ts');
        if (!active || !container.current) return;
        instance = initChart(container.current);
        setUnits(chartUnits(card));
        instance?.setOption(toOption(card, selectedUnit));
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
  }, [expanded, reportId, chartKey, selectedUnit]);

  return <div className="chart-interaction">
    <button type="button" className="chart-open" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
      {expanded ? '收起交互图' : '展开交互图'}
    </button>
    {expanded && <div className="chart-drawing">
      {units.length > 1 && <label>按单位查看（不同单位不共轴） <select
        value={selectedUnit || units[0]}
        onChange={(event) => setSelectedUnit(event.target.value)}
      >{units.map((unit) => <option key={unit} value={unit}>{unit}</option>)}</select></label>}
      {chartKey === 'sentiment' && <p>观察分范围 0–100；亏钱风险越高表示风险越大，其他维度越高表示越强。</p>}
      {error && <p role="status">{error}</p>}
      <div ref={container} className="chart-canvas" role="img" aria-label={`${chartKey} 图形；原始值、观测日和来源见下方表格`} />
    </div>}
  </div>;
}
