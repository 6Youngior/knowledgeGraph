import { useEffect, useRef, type CSSProperties } from 'react';
import * as echarts from 'echarts';
import type { EChartsOption, EChartsType } from 'echarts';

interface EChartProps {
  option: EChartsOption;
  className?: string;
  style?: CSSProperties;
  onReady?: (chart: EChartsType) => void;
  onClick?: (params: unknown) => void;
}

export function EChart({ option, className, style, onReady, onClick }: EChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<EChartsType | null>(null);
  const onReadyRef = useRef(onReady);
  const onClickRef = useRef(onClick);

  onReadyRef.current = onReady;
  onClickRef.current = onClick;

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const chart = echarts.init(element, undefined, { renderer: 'canvas' });
    chartRef.current = chart;
    onReadyRef.current?.(chart);

    const resizeObserver = new ResizeObserver(() => {
      chart.resize();
    });
    resizeObserver.observe(element);

    return () => {
      resizeObserver.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, { notMerge: false, lazyUpdate: true });
  }, [option]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const handler = (params: unknown) => onClickRef.current?.(params);
    chart.on('click', handler);
    return () => {
      chart.off('click', handler);
    };
  }, []);

  return <div ref={containerRef} className={className} style={style} />;
}
