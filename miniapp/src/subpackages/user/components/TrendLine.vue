<script setup lang="ts">
import { computed, getCurrentInstance, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { daysBetween, shiftDate } from "@/utils/beijing-date";
import { levels, type Trend } from "@/utils/health-trends";

interface Point {
  key: string;
  date: string;
  name: string;
  label: string;
  kind: "report" | "checkin";
  sage: boolean;
  x: number;
  y: number;
  reportId?: string | null;
}

const props = defineProps<{ start: string; end: string; series: Trend[]; paused: boolean }>();
const component = getCurrentInstance()?.proxy;
const size = ref({ width: 0, height: 0 });
const selection = ref("");
const span = computed(() => daysBetween(props.start, props.end));
const showHistory = computed(() => props.series.some(trend => trend.report_history?.length));
const showCheckins = computed(() => props.series.some(trend => !trend.started_date || trend.started_date <= props.end));
const unknownDates = computed(() => props.series.filter(trend => !trend.started_date).map(trend => trend.symptom_name));
const countMax = computed(() => {
  const peak = Math.max(1, ...props.series.flatMap(trend => (trend.report_history ?? []).map(item => item.mention_count)));
  // With both scales visible, align four integer report ticks with the four self-rating ticks.
  return showCheckins.value ? 3 * Math.ceil(peak / 3) : peak;
});
const countTicks = computed(() => {
  const steps = Math.min(3, countMax.value);
  return Array.from({ length: steps + 1 }, (_, index) => Math.round(countMax.value * index / steps));
});
const dateTicks = computed(() => {
  const count = Math.min(span.value, span.value <= 6 ? 6 : 3);
  return Array.from({ length: count + 1 }, (_, index) => {
    const offset = count ? Math.round(span.value * index / count) : 0;
    const date = shiftDate(props.start, offset);
    return { date, x: position(date) };
  });
});

function position(date: string) {
  return span.value ? 4 + 92 * daysBetween(props.start, date) / span.value : 50;
}

function height(value: number, maximum: number) {
  return 94 - 78 * value / maximum;
}

const boundaries = computed(() => {
  const dates = new Map<string, { date: string; names: string[]; sage: boolean; x: number }>();
  props.series.forEach((trend, index) => {
    const date = trend.started_date;
    if (!date || date < props.start || date > props.end) return;
    const existing = dates.get(date);
    if (existing) existing.names.push(trend.symptom_name);
    else dates.set(date, { date, names: [trend.symptom_name], sage: index === 1, x: position(date) });
  });
  return [...dates.values()].sort((a, b) => a.date.localeCompare(b.date));
});

const tracks = computed(() => props.series.map((trend, index) => {
  const base = { name: trend.symptom_name, sage: index === 1 };
  const reports: Point[] = (trend.report_history ?? []).map(item => ({
    ...base, key: trend.tracking_id + "/report/" + item.date,
    date: item.date, kind: "report", label: item.mention_count + " 次", reportId: item.report_id,
    x: position(item.date), y: height(item.mention_count, countMax.value),
  }));
  const checkins: Point[] = trend.items.map(item => ({
    ...base, key: trend.tracking_id + "/checkin/" + item.date,
    date: item.date, kind: "checkin", label: item.level_name,
    x: position(item.date), y: height(item.level, 3),
  }));
  return [...reports, ...checkins].sort((a, b) => a.date.localeCompare(b.date));
}));

const points = computed(() => tracks.value.flat().sort((a, b) => a.date.localeCompare(b.date)));
const pointGroups = computed(() => {
  const groups = new Map<string, { key: string; x: number; y: number; entries: Point[] }>();
  for (const point of points.value) {
    const key = point.date + "/" + point.y;
    const group = groups.get(key);
    if (group) group.entries.push(point);
    else groups.set(key, { key, x: point.x, y: point.y, entries: [point] });
  }
  return [...groups.values()];
});

function pointLabel(point: Point) {
  const kind = point.kind === "report" ? "报告提及" : "自评";
  return point.name + " " + kind + " " + point.label;
}

const selected = computed(() => points.value.find(point => point.key === selection.value));
const labels = computed(() => ["选择日期和症状", ...points.value.map(point => point.date + " · " + pointLabel(point))]);
watch(points, () => { if (!selected.value) selection.value = ""; });

const segments = computed(() => tracks.value.flatMap(track => track.slice(1).flatMap((end, index) => {
  const start = track[index];
  if (start.kind !== end.kind || daysBetween(start.date, end.date) !== 1 || !size.value.width) return [];
  const dx = (end.x - start.x) * size.value.width / 100;
  const dy = (end.y - start.y) * size.value.height / 100;
  return [{
    key: start.key,
    kind: start.kind,
    sage: start.sage,
    style: {
      left: start.x + "%", top: start.y + "%",
      width: Math.hypot(dx, dy) + "px",
      transform: "rotate(" + Math.atan2(dy, dx) + "rad)",
    },
  }];
})));

function measure() {
  void nextTick(() => uni.createSelectorQuery().in(component).select(".trend-plot").boundingClientRect(rect => {
    if (rect && "width" in rect) size.value = { width: rect.width ?? 0, height: rect.height ?? 0 };
  }).exec());
}

function openReport(reportId: string) {
  uni.navigateTo({ url: "/pages/report/index?id=" + encodeURIComponent(reportId) });
}

function tapPoint(point: Point) {
  selection.value = point.key;
  if (point.reportId) openReport(point.reportId);
}

function tapGroup(entries: Point[]) {
  if (entries.length === 1) {
    tapPoint(entries[0]);
    return;
  }
  uni.showActionSheet({
    itemList: entries.map(pointLabel),
    success: ({ tapIndex }) => tapPoint(entries[tapIndex]),
  });
}

function selectPoint(index: string | number) {
  selection.value = points.value[Number(index) - 1]?.key ?? "";
}

onMounted(() => { measure(); uni.onWindowResize(measure); });
onUnmounted(() => uni.offWindowResize(measure));
</script>

<template>
  <view class="symptom-chart">
    <view class="chart-legend symptom-legend">
      <view v-for="(trend, index) in series" :key="trend.tracking_id" class="legend-item symptom-color" :class="{ sage: index === 1 }">
        <view class="symptom-key" aria-hidden="true" />
        <text>{{ trend.symptom_name }}{{ paused ? "（已暂停）" : "" }}</text>
      </view>
    </view>
    <view v-if="points.length || boundaries.length" class="chart-legend data-legend">
      <view v-if="showHistory" class="legend-item">
        <view class="data-key report" aria-hidden="true" />报告提及（次）
      </view>
      <view v-if="showCheckins" class="legend-item checkin-legend">
        <view class="data-key" aria-hidden="true" />自评档位
      </view>
    </view>
    <view v-if="points.length || boundaries.length" class="chart">
      <view v-if="showHistory" class="value-axis report-axis" aria-label="报告提及次数">
        <text v-for="value in countTicks" :key="value" :style="{ top: height(value, countMax) + '%' }">{{ value }}</text>
      </view>
      <view class="chart-content">
        <view class="trend-plot">
          <view v-for="value in showCheckins ? [0, 1, 2, 3] : countTicks" :key="value" class="grid-line"
            :style="{ top: height(value, showCheckins ? 3 : countMax) + '%' }" />
          <view v-for="(boundary, index) in boundaries" :key="boundary.date" class="tracking-boundary symptom-color"
            :class="{ sage: boundary.sage, shared: boundary.names.length > 1 }" :style="{ left: boundary.x + '%' }">
            <text v-if="boundaries.length === 1" class="start-label" :class="{ 'label-before': boundary.x >= 50 }">开始追踪</text>
            <text v-else class="start-number" :class="{ lower: index === 1 && boundary.x - boundaries[0].x < 9 }">{{ index + 1 }}</text>
          </view>
          <view v-for="line in segments" :key="line.key" class="trend-segment symptom-color" :class="[line.kind, { sage: line.sage }]" :style="line.style" />
          <button v-for="group in pointGroups" :key="group.key" class="trend-point"
            :class="{ selected: group.entries.some(point => point.key === selection) }"
            :style="{ left: group.x + '%', top: group.y + '%' }"
            :aria-label="group.entries[0].date + ' ' + group.entries.map(pointLabel).join('，')"
            @tap="tapGroup(group.entries)">
            <view v-for="point in group.entries" :key="point.key" class="point-marker symptom-color" :class="[point.kind, { sage: point.sage }]" />
          </button>
        </view>
        <view class="date-axis">
          <text v-for="tick in dateTicks" :key="tick.date" :style="{ left: tick.x + '%' }">{{ tick.date.slice(5).replace('-', '/') }}</text>
        </view>
      </view>
      <view v-if="showCheckins" class="value-axis checkin-axis" aria-label="自评档位">
        <text v-for="(label, value) in levels" :key="label" :style="{ top: height(value, 3) + '%' }">{{ label }}</text>
      </view>
    </view>
    <view v-if="boundaries.length" class="tracking-notes">
      <view v-for="(boundary, index) in boundaries" :key="boundary.date" class="legend-item symptom-color"
        :class="{ sage: boundary.sage, shared: boundary.names.length > 1 }">
        <text v-if="boundaries.length > 1" class="note-number" aria-hidden="true">{{ index + 1 }}</text>
        <text>{{ boundary.date.slice(5).replace("-", "/") }} · {{ boundary.names.join("、") }}{{ boundaries.length > 1 ? "开始追踪" : "" }}</text>
      </view>
    </view>
    <view v-if="unknownDates.length" class="tiny muted unknown-start">{{ unknownDates.join("、") }}的首次开启日期未记录，显示已有自评。</view>
    <view v-if="!points.length" class="empty">这段时间暂无趋势记录</view>
    <view v-else class="point-tools">
      <picker :range="labels" :value="selected ? points.indexOf(selected) + 1 : 0" @change="selectPoint($event.detail.value)">
        <view class="point-reading">
          <text>{{ selected ? selected.date.slice(5) + " · " + pointLabel(selected) : "查看数据点" }}</text>
          <view class="disclosure-icon" aria-hidden="true" />
        </view>
      </picker>
      <button v-if="selected?.reportId" class="point-link" @tap="openReport(selected.reportId)">查看匹配报告 ›</button>
    </view>
  </view>
</template>

<style scoped>
.symptom-chart { margin-top: 14rpx; }
.symptom-color { --line-color: var(--trend-olive); }
.symptom-color.sage { --line-color: var(--trend-sage); }
.symptom-color.shared { --line-color: var(--primary); }
.chart-legend, .tracking-notes { display: flex; flex-wrap: wrap; gap: 6rpx 20rpx; color: var(--secondary-ink); font-size: var(--font-caption); }
.symptom-legend { justify-content: center; }
.data-legend { justify-content: space-between; margin-top: 12rpx; }
.checkin-legend { margin-left: auto; }
.legend-item { display: flex; align-items: center; gap: 8rpx; min-width: 0; overflow-wrap: anywhere; }
.symptom-key, .data-key { position: relative; flex: 0 0 26rpx; height: 0; border-top: 2rpx solid var(--line-color, var(--muted)); }
.symptom-key::after, .data-key::after { content: ""; position: absolute; left: 50%; top: -1rpx; width: 10rpx; height: 10rpx; transform: translate(-50%, -50%); border: 2rpx solid var(--line-color, var(--muted)); background: var(--line-color, var(--muted)); border-radius: 50%; }
.data-key.report { border-top-style: dashed; }
.data-key.report::after { background: var(--surface); }
.chart { display: flex; gap: 8rpx; margin-top: 8rpx; }
.chart-content { flex: 1; min-width: 0; }
.value-axis, .trend-plot { position: relative; height: 270rpx; }
.value-axis { flex: 0 0 46rpx; }
.checkin-axis { flex-basis: 72rpx; }
.value-axis text { position: absolute; transform: translateY(-50%); white-space: nowrap; font-size: 22rpx; color: var(--secondary-ink); }
.report-axis text { right: 0; }
.checkin-axis text { left: 0; }
.trend-plot { margin: 0 9rpx; border-left: 1rpx solid var(--border); }
.grid-line, .trend-segment { position: absolute; }
.grid-line { left: 0; right: 0; height: 1rpx; background: var(--border); }
.tracking-boundary { position: absolute; top: 14%; bottom: 6%; border-left: 1px dashed var(--line-color); pointer-events: none; }
.start-label { position: absolute; top: -33rpx; left: 5rpx; color: var(--deep); font-size: 22rpx; white-space: nowrap; }
.start-label.label-before { left: -5rpx; transform: translateX(-100%); }
.start-number, .note-number { display: inline-flex; align-items: center; justify-content: center; width: 28rpx; height: 28rpx; border-radius: 50%; color: var(--deep); background: var(--surface); border: 1px solid var(--line-color); font-size: 20rpx; line-height: 1; }
.start-number { position: absolute; top: -31rpx; left: 0; transform: translateX(-50%); }
.start-number.lower { top: 0; }
.trend-segment { border-top: 2px solid var(--line-color); transform-origin: left top; pointer-events: none; }
.trend-segment.report { border-top-style: dashed; }
.trend-point {
  position: absolute;
  min-width: 0;
  width: 40rpx;
  height: 34rpx;
  transform: translate(-50%, -50%);
  padding: 0;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2rpx;
}
.trend-point::after, .point-link::after { border: 0; }
.point-marker { flex: 0 0 14rpx; width: 14rpx; height: 14rpx; border-radius: 50%; background: var(--line-color); border: 2rpx solid var(--line-color); }
.point-marker.report { background: var(--surface); }
.trend-point.selected { z-index: 1; }
.trend-point.selected .point-marker { box-shadow: 0 0 0 5rpx var(--soft); }
.date-axis { position: relative; margin: 0 9rpx; min-height: 30rpx; color: var(--secondary-ink); font-size: 21rpx; }
.date-axis text { position: absolute; transform: translateX(-50%); white-space: nowrap; }
.tracking-notes, .unknown-start { margin-top: 10rpx; }
.tracking-notes { font-size: 22rpx; }
.point-tools { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6rpx 14rpx; }
.point-reading, .point-link { min-height: 54rpx; display: flex; align-items: center; color: var(--primary); font-size: var(--font-caption); }
.point-reading { gap: 8rpx; }
.point-reading .disclosure-icon { width: 13rpx; height: 13rpx; }
.point-link { padding: 0; background: transparent; }
</style>
