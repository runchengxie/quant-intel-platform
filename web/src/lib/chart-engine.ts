import * as echarts from 'echarts/core';
import { BarChart } from 'echarts/charts';
import {
  AriaComponent, DataZoomComponent, GridComponent, LegendComponent,
  MarkLineComponent, TooltipComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsType } from 'echarts/core';

echarts.use([
  BarChart, GridComponent, TooltipComponent, LegendComponent,
  DataZoomComponent, MarkLineComponent, AriaComponent, CanvasRenderer,
]);

export function initChart(container: HTMLElement): EChartsType {
  return echarts.init(container);
}
