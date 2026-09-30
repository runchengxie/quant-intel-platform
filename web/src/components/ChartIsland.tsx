import { useEffect, useRef, useState } from 'react';
import type { EChartsOption } from 'echarts';
import { chartUnits, loadChart, toOption } from '../lib/chart-data.ts';
import { toEnglishPresentation } from '../lib/english-content.ts';

interface ChartIslandProps {
  reportId: string;
  chartKey: string;
  locale?: 'zh' | 'en';
}

interface ChartInstance {
  setOption: (option: EChartsOption) => void;
  resize: () => void;
  dispose: () => void;
}

export default function ChartIsland({ reportId, chartKey, locale = 'zh' }: ChartIslandProps) {
  const english = locale === 'en';
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
        instance?.setOption(toOption(card, selectedUnit, locale));
        observer = new ResizeObserver(() => instance?.resize());
        observer.observe(container.current);
      } catch {
        if (active) setError(english ? 'Interactive chart unavailable; see the values and sources below.' : '交互图暂不可用；请查看下方静态数值与来源。');
      }
    })();
    return () => {
      active = false;
      observer?.disconnect();
      instance?.dispose();
    };
  }, [expanded, reportId, chartKey, selectedUnit, locale]);

  return <div className="chart-interaction">
    <button type="button" className="chart-open" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
      {english ? (expanded ? 'Collapse chart' : 'Open interactive chart') : (expanded ? '收起交互图' : '展开交互图')}
    </button>
    {expanded && <div className="chart-drawing">
      {units.length > 1 && <label>{english ? 'View by unit (different units use separate axes)' : '按单位查看（不同单位不共轴）'} <select
        value={selectedUnit || units[0]}
        onChange={(event) => setSelectedUnit(event.target.value)}
      >{units.map((unit) => <option key={unit} value={unit}>{english ? toEnglishPresentation(unit) : unit}</option>)}</select></label>}
      {chartKey === 'sentiment' && <p>{english ? 'Scores range from 0 to 100. A higher loss-risk score indicates more risk; higher scores in other dimensions indicate strength.' : '观察分范围 0–100；亏钱风险越高表示风险越大，其他维度越高表示越强。'}</p>}
      {error && <p role="status">{error}</p>}
      <div ref={container} className="chart-canvas" role="img" aria-label={english ? `${chartKey} chart; original values, observation dates and sources appear in the table below` : `${chartKey} 图形；原始值、观测日和来源见下方表格`} />
    </div>}
  </div>;
}
