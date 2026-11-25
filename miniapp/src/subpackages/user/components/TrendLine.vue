<script setup lang="ts">
import { computed, getCurrentInstance, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { daysBetween, shiftDate } from "@/utils/beijing-date";
import { type Trend } from "@/utils/health-trends";

const props = defineProps<{ start: string; end: string; series: Trend[] }>();
const component = getCurrentInstance()?.proxy;
const size = ref({ width: 0, height: 0 });
const selected = ref("");
const span = computed(() => daysBetween(props.start, props.end));
const scale = ["较重", "中等", "较轻", "无"];
const ticks = computed(() => {
  const count = span.value <= 6 ? span.value : 3;
  return Array.from({ length: count + 1 }, (_, index) => {
    const offset = count ? Math.round(span.value * index / count) : 0;
    return { date: shiftDate(props.start, offset), x: position(offset) };
  });
});

function position(offset: number) {
  return span.value ? 4 + 92 * offset / span.value : 50;
}

const tracks = computed(() => props.series.map((trend, index) => [...trend.items]
  .sort((a, b) => a.date.localeCompare(b.date))
  .map(item => ({
    ...item,
    key: trend.tracking_id + "/" + item.date,
    name: trend.symptom_name,
    sage: index === 1,
    x: position(daysBetween(props.start, item.date)),
    y: 5 + 30 * (3 - item.level),
  }))));
const points = computed(() => tracks.value.flat().sort((a, b) => a.date.localeCompare(b.date)));
const current = computed(() => points.value.find(point => point.key === selected.value));
const labels = computed(() => ["选择日期和症状", ...points.value.map(point => point.date + " · " + point.name + " · " + point.level_name)]);
watch(points, () => {
  if (!current.value) selected.value = "";
});

const segments = computed(() => tracks.value.flatMap(track => track.slice(1).flatMap((b, index) => {
  const a = track[index];
  if (daysBetween(a.date, b.date) !== 1 || !size.value.width) return [];
  const dx = (b.x - a.x) * size.value.width / 100;
  const dy = (b.y - a.y) * size.value.height / 100;
  return [{
    key: a.key,
    sage: a.sage,
    style: {
      left: a.x + "%", top: a.y + "%",
      width: Math.hypot(dx, dy) + "px",
      transform: "rotate(" + Math.atan2(dy, dx) + "rad)",
    },
    fill: {
      left: a.x + "%", width: (b.x - a.x) + "%",
      clipPath: "polygon(0 " + a.y / .95 + "%, 100% " + b.y / .95 + "%, 100% 100%, 0 100%)",
    },
  }];
})));

function measure() {
  void nextTick(() => uni.createSelectorQuery().in(component).select(".trend-plot").boundingClientRect(rect => {
    if (rect && "width" in rect) size.value = { width: rect.width ?? 0, height: rect.height ?? 0 };
  }).exec());
}
function selectPoint(index: string | number) {
  selected.value = points.value[Number(index) - 1]?.key || "";
}

onMounted(() => { measure(); uni.onWindowResize(measure); });
onUnmounted(() => uni.offWindowResize(measure));
</script>

<template>
  <view>
    <view class="chart">
      <view class="level-axis" aria-hidden="true">
        <text v-for="(label, index) in scale" :key="label" :style="{ top: (5 + 30 * index) + '%' }">{{ label }}</text>
      </view>
      <view class="chart-content">
        <view class="trend-plot">
          <view v-for="(_, index) in scale" :key="index" class="grid-line" :style="{ top: (5 + 30 * index) + '%' }" />
          <view v-for="line in segments" :key="line.key + '-fill'" class="trend-fill" :class="{ sage: line.sage }" :style="line.fill" />
          <view v-for="line in segments" :key="line.key" class="trend-segment" :class="{ sage: line.sage }" :style="line.style" />
          <button v-for="point in points" :key="point.key" class="trend-point"
            :class="{ selected: point.key === current?.key, sage: point.sage }"
            :style="{ left: point.x + '%', top: point.y + '%' }"
            :aria-label="point.date + ' ' + point.name + ' ' + point.level_name"
            @tap="selected = point.key"><view /></button>
        </view>
        <view class="date-axis">
          <text v-for="tick in ticks" :key="tick.date" :style="{ left: tick.x + '%' }">{{ tick.date.slice(5).replace('-', '/') }}</text>
        </view>
      </view>
    </view>
    <picker :range="labels" :value="current ? points.indexOf(current) + 1 : 0" @change="selectPoint($event.detail.value)">
      <view class="point-reading">
        <view>{{ current ? current.date.slice(5) + " · " + current.name + " · " + current.level_name : "查看自评记录" }}</view>
        <view class="disclosure-icon" aria-hidden="true" />
      </view>
    </picker>
  </view>
</template>

<style scoped>
.chart { display: flex; gap: 14rpx; margin-top: 14rpx; }
.chart-content { flex: 1; min-width: 0; }
.level-axis { position: relative; height: 282rpx; flex: 0 0 55rpx; }
.level-axis text {
  position: absolute;
  right: 0;
  transform: translateY(-50%);
  white-space: nowrap;
  font-size: 22rpx;
  color: var(--secondary-ink);
}
.trend-plot { position: relative; height: 282rpx; margin: 0 8rpx; border-left: 1rpx solid var(--border); }
.grid-line, .trend-segment, .trend-fill { position: absolute; }
.grid-line { left: 0; right: 0; height: 1rpx; background: var(--border); }
.trend-segment { height: 2px; background: var(--trend-olive); transform-origin: left center; pointer-events: none; }
.trend-segment.sage { background: var(--trend-sage); }
.trend-fill { top: 0; bottom: 5%; background: linear-gradient(var(--trend-olive-fill), transparent); pointer-events: none; }
.trend-fill.sage { background: linear-gradient(var(--trend-sage-fill), transparent); }
.trend-point {
  position: absolute;
  min-width: 0;
  width: 38rpx;
  height: 38rpx;
  transform: translate(-50%, -50%);
  padding: 0;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
}
.trend-point::after { border: 0; }
.trend-point view { width: 14rpx; height: 14rpx; border-radius: 50%; background: var(--surface); border: 3rpx solid var(--trend-olive); }
.trend-point.sage view { border-color: var(--trend-sage); }
.trend-point.selected { z-index: 1; }
.trend-point.selected view { box-shadow: 0 0 0 5rpx var(--soft); }
.date-axis { position: relative; margin: 0 8rpx; min-height: 30rpx; color: var(--secondary-ink); font-size: 21rpx; }
.date-axis text { position: absolute; transform: translateX(-50%); white-space: nowrap; }
.point-reading { margin-top: 8rpx; min-height: 46rpx; display: flex; justify-content: flex-end; align-items: center; gap: 16rpx; color: var(--primary); font-size: var(--font-caption); }
.point-reading .disclosure-icon { width: 13rpx; height: 13rpx; }
</style>
