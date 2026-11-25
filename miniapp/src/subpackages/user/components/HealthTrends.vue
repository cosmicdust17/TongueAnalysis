<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import AppIcon from "@/components/AppIcon.vue";
import type { Report } from "@/types";
import { api, ApiError, toastError } from "@/utils/request";
import { shiftDate } from "@/utils/beijing-date";
import {
  getTrackings, getTrend, levels, startTracking, stopTracking,
  type Tracking, type Trackings, type Trend,
} from "@/utils/health-trends";
import TrendLine from "./TrendLine.vue";

const board = ref<Trackings | null>(null);
const pausedId = ref("");
const symptom = ref("");
const days = ref(7);
const ranges = [
  { days: 7, label: "近7天" },
  { days: 30, label: "近30天" },
  { days: 90, label: "近3个月" },
];
const loading = ref(false);
const saving = ref(false);
const listError = ref("");
const limitMessage = ref("");
const series = ref<Trend[]>([]);
const trendBusy = ref(false);
const trendError = ref("");
const latestReport = ref<Report>();
let trendVersion = 0;
let disposed = false;

const items = computed(() => board.value?.items ?? []);
const activeItems = computed(() => items.value.filter(item => item.active).slice(0, 2));
const pausedItem = computed(() => items.value.find(item => !item.active && item.id === pausedId.value));
const chartItems = computed(() => pausedItem.value ? [pausedItem.value] : activeItems.value);
const startDate = computed(() => board.value ? shiftDate(board.value.date, 1 - days.value) : "");
const rangeLabel = computed(() => ranges.find(range => range.days === days.value)?.label);
const advice = computed(() => latestReport.value?.content.presentation?.advice_items?.[0]?.text?.trim());
const totalCheckins = computed(() => series.value.flatMap(trend => trend.items));
const average = computed(() => {
  const entries = totalCheckins.value;
  return entries.length ? (entries.reduce((sum, entry) => sum + entry.level, 0) / entries.length).toFixed(1) : null;
});
const spread = computed(() => {
  const values = series.value.filter(trend => trend.items.length >= 2).map(trend => {
    const values = trend.items.map(item => item.level);
    return Math.max(...values) - Math.min(...values);
  });
  return values.length ? Math.max(...values) : null;
});
const interpretation = computed(() => series.value.flatMap(trend => {
  if (trend.items.length < 2) return [];
  const sorted = [...trend.items].sort((a, b) => a.date.localeCompare(b.date));
  const first = sorted[0], last = sorted[sorted.length - 1];
  return [trend.symptom_name + "记录 " + sorted.length + " 次，首条为「" + levels[first.level] + "」，末条为「" + levels[last.level] + "」。"];
}).join(""));

async function loadTrend() {
  const version = ++trendVersion;
  const end = board.value?.date;
  series.value = [];
  trendError.value = "";
  const selections = chartItems.value;
  trendBusy.value = Boolean(end && selections.length);
  if (!end || !selections.length) return;
  try {
    const result = await Promise.all(selections.map(item => getTrend(item.id, startDate.value, end)));
    if (version === trendVersion) series.value = result;
  } catch (e) {
    if (version === trendVersion) trendError.value = e instanceof Error ? e.message : "无法读取趋势";
  } finally {
    if (version === trendVersion) trendBusy.value = false;
  }
}

async function loadTrackings() {
  if (loading.value) return;
  loading.value = true;
  listError.value = "";
  try {
    const result = await getTrackings();
    if (disposed) return;
    board.value = result;
    if (!pausedItem.value) pausedId.value = "";
    void loadTrend();
  } catch (e) {
    if (!disposed) listError.value = e instanceof Error ? e.message : "无法读取症状追踪";
  } finally {
    loading.value = false;
  }
}

function showPaused(id = "") {
  pausedId.value = id;
  void loadTrend();
  uni.pageScrollTo({ scrollTop: 0, duration: 200 });
}

function chooseRange(value: number) {
  if (days.value === value) return;
  days.value = value;
  void loadTrend();
}

async function loadLatestReport() {
  try {
    const result = await api<{ items: Report[] }>("/reports?page=1&page_size=1");
    if (!disposed) latestReport.value = result.items[0];
  } catch {
    // Tracking data remains available if the report request fails.
  }
}

function openReport() {
  if (latestReport.value && advice.value) {
    uni.navigateTo({ url: "/pages/report/index?id=" + encodeURIComponent(latestReport.value.id) });
  }
}

async function changeTracking(action: () => Promise<void>, message: string) {
  if (saving.value || loading.value) return;
  saving.value = true;
  limitMessage.value = "";
  try {
    await action();
    if (disposed) return;
    uni.showToast({ title: message, icon: "success" });
    await loadTrackings();
  } catch (e) {
    if (disposed) return;
    if (e instanceof ApiError && e.code === "tracking_limit_reached") {
      limitMessage.value = e.message;
      await loadTrackings();
    } else toastError(e);
  } finally {
    saving.value = false;
  }
}

function start(name: string, manual = false) {
  const value = name.trim();
  if (!value) {
    toastError(new Error("请输入症状名称"));
    return;
  }
  void changeTracking(async () => {
    await startTracking(value);
    if (manual) symptom.value = "";
  }, manual ? "已开始追踪" : "已恢复追踪");
}

function stop(item: Tracking) {
  void changeTracking(async () => { await stopTracking(item.id); }, "已暂停追踪");
}

function label(item: Tracking) {
  return item.today_level === null ? "未填写" : levels[item.today_level];
}

onMounted(() => {
  void loadTrackings();
  void loadLatestReport();
});
onUnmounted(() => { disposed = true; trendVersion++; });
</script>

<template>
  <view class="health-trends">
    <view class="range-buttons">
      <button v-for="range in ranges" :key="range.days" class="range-button"
        :class="{ selected: days === range.days }" :aria-pressed="days === range.days"
        @tap="chooseRange(range.days)">{{ range.label }}</button>
    </view>

    <view v-if="loading && !board" class="loading">正在读取症状追踪…</view>
    <view v-if="listError" class="error">
      {{ listError }}
      <button class="outline button-small spaced" :disabled="loading" @tap="loadTrackings">重试</button>
    </view>
    <template v-if="board">
      <view class="panel trend-panel">
        <view class="row between">
          <view class="card-title">症状趋势</view>
          <button v-if="pausedItem" class="text-action" @tap="showPaused()">返回追踪趋势</button>
        </view>
        <view v-if="trendBusy" class="loading">正在读取趋势…</view>
        <view v-else-if="trendError" class="error spaced">
          {{ trendError }} <text class="link" @tap="loadTrend">重试</text>
        </view>
        <TrendLine v-else-if="series.length" :start="startDate" :end="board.date" :series="series" :paused="!!pausedItem" />
        <view v-else class="empty">
          可在下方或分析完成页开启症状追踪。
        </view>
      </view>

      <view class="panel overview-panel">
        <view class="row overview-title">
          <view class="card-title">健康概览</view>
          <text class="tiny muted">（{{ rangeLabel }}）</text>
        </view>
        <view class="metrics">
          <view class="metric">
            <AppIcon name="leaf" :size="36" />
            <view class="metric-title">平均状态</view>
            <view class="metric-value" :class="{ unavailable: average === null }">{{ average ?? "暂无数据" }}</view>
            <view v-if="average !== null" class="metric-caption">自评均值 / 3</view>
          </view>
          <view class="metric">
            <AppIcon name="trend" :size="36" />
            <view class="metric-title">症状波动</view>
            <view class="metric-value" :class="{ unavailable: spread === null }">{{ spread ?? "暂无数据" }}</view>
            <view v-if="spread !== null" class="metric-caption">最大等级差</view>
          </view>
          <view class="metric">
            <AppIcon name="moon" :size="36" />
            <view class="metric-title">睡眠评分</view>
            <view class="metric-value unavailable">暂无数据</view>
          </view>
        </view>
      </view>

      <view class="panel insight">
        <AppIcon name="document" :size="38" />
        <view class="grow">
          <view class="card-title">趋势解读</view>
          <view class="insight-text">{{ interpretation || "当前记录较少，继续记录后可查看变化趋势。" }}</view>
        </view>
      </view>

      <view class="panel reminder">
        <AppIcon name="bell" :size="38" />
        <view class="grow">
          <view class="card-title">调护提醒</view>
          <view class="insight-text">{{ advice || "暂无报告调护建议。" }}</view>
        </view>
        <button v-if="advice" class="report-link" aria-label="查看调护建议报告" @tap="openReport"><view class="disclosure-icon right" /></button>
      </view>

      <view class="panel tracking-panel">
        <view class="row between">
          <view class="card-title">追踪管理</view>
          <view class="tiny muted">正在追踪 {{ board.active_count }} / {{ board.max_active }} 项</view>
        </view>
        <view class="row add-row">
          <input v-model="symptom" class="field grow" :maxlength="80" placeholder="输入症状名称"
            aria-label="输入症状名称" confirm-type="done" @confirm="start(symptom, true)" />
          <button class="secondary button-small" :disabled="saving || loading || !symptom.trim()"
            @tap="start(symptom, true)">开始追踪</button>
        </view>
        <view v-if="limitMessage" class="limit-message tiny" role="status">{{ limitMessage }}</view>
        <view v-for="item in items" :key="item.id" class="row between tracking-row">
          <view class="grow">
            <view class="symptom-name">{{ item.symptom_name }}</view>
            <view class="tiny muted">{{ item.active ? "追踪中" : "已暂停" }} · 今日自评 {{ label(item) }}</view>
          </view>
          <button v-if="item.active" class="outline button-small" :disabled="saving || loading" @tap="stop(item)">暂停</button>
          <template v-else>
            <button class="text-action" @tap="showPaused(item.id)">查看历史</button>
            <button class="secondary button-small" :disabled="saving || loading" @tap="start(item.symptom_name)">恢复</button>
          </template>
        </view>
      </view>
    </template>
  </view>
</template>

<style scoped>
.range-buttons {
  display: flex;
  padding: 2rpx;
  margin-bottom: 26rpx;
  border: 1rpx solid var(--border);
  border-radius: 999rpx;
  background: var(--surface);
  box-shadow: var(--card-shadow);
}
.range-button {
  flex: 1;
  min-height: 66rpx;
  padding: 5rpx 8rpx;
  border-radius: 999rpx;
  background: transparent;
  color: var(--deep);
  font-size: var(--font-body);
}
.range-button::after, .report-link::after, .text-action::after { border: 0; }
.range-button.selected { color: #fff; background: var(--primary); font-weight: 600; }
.trend-panel, .overview-panel { padding: 22rpx 24rpx 26rpx; }
.overview-title { gap: 0; }
.metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); align-items: stretch; gap: 18rpx; margin-top: 18rpx; }
.metric { width: auto; display: flex; flex-direction: column; align-items: center; gap: 5rpx; padding: 20rpx 6rpx 16rpx; border-radius: 24rpx; text-align: center; background: var(--soft); }
.metric:nth-child(2) { background: var(--tint); }
.metric:nth-child(3) { background: var(--paper); }
.metric-title, .metric-caption { font-size: var(--font-caption); color: var(--secondary-ink); }
.metric-value { color: var(--primary); font-size: 40rpx; font-weight: 680; line-height: 1.25; }
.metric-value.unavailable { padding-top: 3rpx; font-size: var(--font-body); }
.insight, .reminder { display: flex; align-items: flex-start; gap: 16rpx; padding: 20rpx 23rpx; }
.insight { background: linear-gradient(130deg, var(--soft), var(--surface)); }
.reminder { background: linear-gradient(130deg, var(--paper), var(--surface)); }
.insight :deep(.app-icon), .reminder :deep(.app-icon) { flex-shrink: 0; margin-top: 3rpx; }
.insight-text { margin-top: 5rpx; font-size: var(--font-secondary); line-height: 1.55; overflow-wrap: anywhere; }
.report-link { align-self: center; display: grid; place-items: center; min-width: 56rpx; min-height: 56rpx; padding: 0; background: transparent; }
.tracking-row { margin-top: 16rpx; padding-top: 14rpx; gap: 12rpx; border-top: 1rpx solid var(--border); }
.symptom-name { font-weight: 600; overflow-wrap: anywhere; }
.add-row { flex-wrap: wrap; gap: 10rpx; margin-top: 14rpx; }
.add-row input { margin-top: 0; min-width: 180rpx; min-height: 70rpx; }
.add-row button { flex-shrink: 0; }
.limit-message { color: var(--secondary-ink); margin-top: 12rpx; }
.text-action { flex-shrink: 0; padding: 0 5rpx; min-height: 56rpx; color: var(--primary); background: transparent; font-size: var(--font-caption); }
</style>
