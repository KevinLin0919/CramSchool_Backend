// A thin React wrapper over ECharts, with only the pieces these pages use so
// the bundle stays small. One theme for every chart: the app's palette, the
// Noto Sans TC face for words and IBM Plex Mono for figures.
import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, MarkAreaComponent, MarkLineComponent, ToolboxComponent, TooltipComponent, AriaComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption, ECharts } from "echarts/core";

echarts.use([BarChart, LineChart, GridComponent, LegendComponent, MarkAreaComponent, MarkLineComponent, ToolboxComponent, TooltipComponent, AriaComponent, CanvasRenderer]);

export const C = {
  ink: "#16211b", ink2: "#4b5a51", ink3: "#85918a", line: "#e1e7e3", grid: "#eef1ef",
  brand: "#2d5a3d", choice: "#3f8f63", choiceL: "#9cc9ae", mark: "#6e5bd1", markL: "#a99be6",
  bad: "#c8412f", badL: "#e9a397", muted: "#b9c3bd", low: "#b7c9bd",
};
export const SANS = '"Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif';
export const MONO = '"IBM Plex Mono", Menlo, Consolas, monospace';

echarts.registerTheme("fudao", {
  color: [C.ink, C.choice, C.mark, C.bad, C.muted],
  backgroundColor: "transparent",
  textStyle: { fontFamily: SANS, color: C.ink2 },
  animationDuration: 700,
  animationEasing: "cubicOut",
  categoryAxis: { axisLine: { lineStyle: { color: "#dfe5e1" } }, axisTick: { show: false }, axisLabel: { color: C.ink3, fontFamily: MONO, fontSize: 11 }, splitLine: { show: false } },
  valueAxis: { axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: C.ink3, fontFamily: MONO, fontSize: 11 }, splitLine: { lineStyle: { color: C.grid } } },
  tooltip: { backgroundColor: "#ffffff", borderColor: C.line, borderWidth: 1, padding: [8, 12], textStyle: { fontFamily: SANS, color: C.ink, fontSize: 12.5 }, extraCssText: "box-shadow: 0 8px 24px rgba(22,33,27,.12); border-radius: 10px;" },
  legend: { textStyle: { color: C.ink2, fontFamily: SANS }, itemWidth: 14, itemHeight: 8 },
});

/** The download button every chart carries: a picture for a slide or a parent. */
export function saveButton(name: string) {
  return {
    right: 4, top: 0, itemSize: 14,
    feature: { saveAsImage: { name, title: "存成圖片", pixelRatio: 2, backgroundColor: "#ffffff" } },
    iconStyle: { borderColor: C.ink3 }, emphasis: { iconStyle: { borderColor: C.brand, textFill: C.brand, textPosition: "left" } },
  };
}

type Handlers = Record<string, (params: any) => void>;

export function EChart({ option, height, onEvents, ariaLabel }: { option: EChartsCoreOption; height: number; onEvents?: Handlers; ariaLabel: string }) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<ECharts | null>(null);
  const handlers = useRef<Handlers | undefined>(onEvents);
  handlers.current = onEvents;

  useEffect(() => {
    if (!el.current) return;
    const c = echarts.init(el.current, "fudao", { renderer: "canvas" });
    chart.current = c;
    const names = ["click", "mouseover", "legendselectchanged"];
    names.forEach((n) => c.on(n, (p) => handlers.current?.[n]?.(p)));
    // A click anywhere in a category's column, not only on its bar: a bar
    // for a question almost nobody got right is a few pixels tall.
    c.getZr().on("click", (e) => {
      const fn = handlers.current?.axisclick;
      if (!fn || !c.containPixel({ gridIndex: 0 }, [e.offsetX, e.offsetY])) return;
      const [index] = c.convertFromPixel({ gridIndex: 0 }, [e.offsetX, e.offsetY]) as number[];
      if (Number.isFinite(index)) fn({ dataIndex: Math.round(index) });
    });
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(el.current);
    return () => { ro.disconnect(); c.dispose(); chart.current = null; };
  }, []);

  useEffect(() => {
    chart.current?.setOption({ aria: { enabled: true, label: { description: ariaLabel } }, ...option }, { notMerge: true });
  }, [option, ariaLabel]);

  return <div ref={el} className="chart" style={{ height }} role="img" aria-label={ariaLabel} />;
}
