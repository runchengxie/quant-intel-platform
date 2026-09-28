import * as echarts from 'echarts/core';
import { BarChart } from 'echarts/charts';
import {
  AriaComponent, DataZoomComponent, GridComponent, LegendComponent,
  MarkLineComponent, TooltipComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  BarChart, GridComponent, TooltipComponent, LegendComponent,
  DataZoomComponent, MarkLineComponent, AriaComponent, CanvasRenderer,
]);

export function initChart(container) {
  return echarts.init(container);
}
