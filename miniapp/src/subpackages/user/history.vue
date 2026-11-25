<script setup lang="ts">
import { computed, ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { api, query, dateText } from "@/utils/request";
import { beijingDate, daysBetween, shiftDate, weekOf } from "@/utils/beijing-date";
import { requireAuth } from "@/stores/auth";
import type { Report } from "@/types";
import AuthImage from "@/components/AuthImage.vue";
import AppIcon from "@/components/AppIcon.vue";
import RoleNav from "@/components/RoleNav.vue";

interface CalendarMonth {
  month: string;
  dates: string[];
  counts: Record<string, number>;
}

const showSearch = ref(false);
const scopes = ["全部记录", "选中日"];
const today = ref(beijingDate());
const selectedDate = ref("");
const weekDate = ref(today.value);
const monthOpen = ref(false);
const visibleMonth = ref(today.value.slice(0, 7));
const week = computed(() => weekOf(weekDate.value));
const month = computed(() => monthOpen.value ? visibleMonth.value : weekDate.value.slice(0, 7));
const monthDays = computed(() => {
  const first = visibleMonth.value + "-01";
  const next = shiftDate(first, 32).slice(0, 7) + "-01";
  const leading = daysBetween(weekOf(first)[0], first);
  const length = daysBetween(first, next);
  const cells = Math.ceil((leading + length) / 7) * 7;
  return Array.from({ length: cells }, (_, index) => {
    const day = index - leading;
    return day >= 0 && day < length ? shiftDate(first, day) : "";
  });
});
const weekdays = ["一", "二", "三", "四", "五", "六", "日"];
const calendars = ref<Record<string, CalendarMonth>>({});
const calendarError = ref("");
let calendarVersion = 0;
let initialVisit = true;

const rows = ref<Report[]>([]);
const total = ref(0);
const q = ref("");
const searchTerm = ref("");
const listTitle = computed(() => {
  if (!selectedDate.value) return searchTerm.value ? "搜索结果" : "全部记录";
  const [, month, day] = selectedDate.value.split("-");
  return Number(month) + "月" + Number(day) + "日记录";
});
const nextPage = ref(1);
const busy = ref(false);
const error = ref("");
let reportsVersion = 0;

async function loadCalendar(force = false) {
  const version = ++calendarVersion;
  const months = monthOpen.value ? [visibleMonth.value] : [...new Set(week.value.map(date => date.slice(0, 7)))];
  const pending = months.filter(key => force || !calendars.value[key]);
  calendarError.value = "";
  if (!pending.length) return;
  try {
    const results = await Promise.all(pending.map(month => api<CalendarMonth>("/reports/calendar" + query({ month }))));
    if (version !== calendarVersion) return;
    for (const result of results) calendars.value[result.month] = result;
  } catch (e) {
    if (version === calendarVersion) calendarError.value = e instanceof Error ? e.message : "无法加载日历";
  }
}

function hasReports(date: string) {
  const calendar = calendars.value[date.slice(0, 7)];
  return !!calendar && (calendar.dates.includes(date) || (calendar.counts[date] ?? 0) > 0);
}

function dayLabel(date: string) {
  return date + (date === today.value ? " 今天" : "") + (hasReports(date) ? " 有分析记录" : "");
}

async function loadReports(reset = false) {
  if (!reset && busy.value) return;
  const version = ++reportsVersion;
  if (reset) {
    rows.value = [];
    total.value = 0;
    nextPage.value = 1;
  }
  const page = nextPage.value;
  const params: Record<string, string | number> = { page, page_size: 20 };
  if (selectedDate.value) params.date = selectedDate.value;
  if (searchTerm.value) params.q = searchTerm.value;
  busy.value = true;
  error.value = "";
  try {
    const result = await api<{ items: Report[]; total: number; page: number }>(
      "/reports" + query(params),
    );
    if (version !== reportsVersion) return;
    rows.value = reset ? result.items : [...rows.value, ...result.items];
    total.value = result.total;
    nextPage.value = result.page + 1;
  } catch (e) {
    if (version === reportsVersion) error.value = e instanceof Error ? e.message : "读取失败";
  } finally {
    if (version === reportsVersion) busy.value = false;
  }
}

function search() {
  searchTerm.value = q.value.trim();
  void loadReports(true);
}

function chooseDate(date: string) {
  selectedDate.value = date;
  weekDate.value = date;
  visibleMonth.value = date.slice(0, 7);
  void loadCalendar();
  void loadReports(true);
}

function moveWeek(offset: number) {
  weekDate.value = shiftDate(weekDate.value, offset * 7);
  void loadCalendar();
}

function moveMonth(offset: -1 | 1) {
  visibleMonth.value = shiftDate(visibleMonth.value + "-01", offset < 0 ? -1 : 32).slice(0, 7);
  void loadCalendar(true);
}

function toggleMonth() {
  if (monthOpen.value) {
    if (selectedDate.value) {
      weekDate.value = selectedDate.value;
    } else if (visibleMonth.value !== weekDate.value.slice(0, 7)) {
      weekDate.value = visibleMonth.value + "-01";
    }
    monthOpen.value = false;
    void loadCalendar();
  } else {
    visibleMonth.value = weekDate.value.slice(0, 7);
    monthOpen.value = true;
    void loadCalendar(true);
  }
}

function goToday() {
  today.value = beijingDate();
  chooseDate(today.value);
}

function selectScope(index: string | number) {
  if (Number(index) === 1) {
    chooseDate(selectedDate.value || weekDate.value);
    return;
  }
  selectedDate.value = "";
  void loadReports(true);
}

onShow(() => {
  if (!requireAuth("user")) return;
  today.value = beijingDate();
  if (!initialVisit) return;
  initialVisit = false;
  weekDate.value = today.value;
  void loadCalendar();
  void loadReports(true);
});

function open(id: string) {
  uni.navigateTo({ url: "/pages/report/index?id=" + encodeURIComponent(id) });
}
</script>


<template>
  <view class="page olive-sheet with-nav history-page">
    <view class="calendar">
      <view class="row between date-overview">
        <text class="month-heading">{{ month.slice(0, 4) }}年{{ Number(month.slice(5)) }}月</text>
        <view class="row calendar-controls">
          <template v-if="monthOpen">
            <button class="calendar-arrow" aria-label="上一月" @tap="moveMonth(-1)">‹</button>
            <button class="calendar-arrow" aria-label="下一月" @tap="moveMonth(1)">›</button>
          </template>
          <button v-else-if="!week.includes(today)" class="calendar-action" @tap="goToday">返回今天</button>
          <button class="calendar-icon" :class="{ 'is-open': monthOpen }" :aria-expanded="monthOpen"
            :aria-label="monthOpen ? '收起月历' : '展开月历'" @tap="toggleMonth">
            <AppIcon name="calendar" :size="36" />
          </button>
        </view>
      </view>

      <view v-if="monthOpen" class="month-panel calendar-panel">
        <view class="month-grid">
          <text v-for="day in weekdays" :key="day" class="weekday">{{ day }}</text>
          <template v-for="(date, index) in monthDays" :key="date || index">
            <button v-if="date" class="month-day"
              :class="{ selected: date === selectedDate, today: date === today, 'has-reports': hasReports(date) }"
              :aria-label="dayLabel(date)" :aria-pressed="date === selectedDate" @tap="chooseDate(date)">
              <view class="calendar-day">{{ Number(date.slice(-2)) }}</view>
            </button>
            <view v-else aria-hidden="true" />
          </template>
        </view>
        <view class="row between month-actions">
          <button class="calendar-action" @tap="goToday">返回今天</button>
          <button class="calendar-action" @tap="toggleMonth">收起月历 <view class="disclosure-icon expanded" aria-hidden="true" /></button>
        </view>
      </view>
      <view v-else class="week-picker calendar-panel">
        <button class="week-arrow calendar-arrow" aria-label="上一周" @tap="moveWeek(-1)">‹</button>
        <view class="week-days">
          <button v-for="(date, index) in week" :key="date" class="week-day"
            :class="{ selected: date === selectedDate, today: date === today, 'has-reports': hasReports(date) }"
            :aria-label="dayLabel(date)" :aria-pressed="date === selectedDate" @tap="chooseDate(date)">
            <text class="weekday">{{ weekdays[index] }}</text>
            <view class="calendar-day">{{ Number(date.slice(-2)) }}</view>
          </button>
        </view>
        <button class="week-arrow calendar-arrow" aria-label="下一周" @tap="moveWeek(1)">›</button>
      </view>
    </view>
    <view v-if="calendarError" class="error">
      {{ calendarError }} <text class="link" @tap="loadCalendar(true)">重试日历</text>
    </view>

    <view class="row between history-heading">
      <view class="row history-caption">
        <text class="card-title">{{ listTitle }}</text>
        <text v-if="!busy && !error" class="tiny muted">（共{{ total }}份）</text>
      </view>
      <view class="row history-controls">
        <button class="search-toggle" aria-label="搜索记录" :aria-expanded="showSearch" @tap="showSearch = !showSearch">
          <AppIcon name="search" :size="30" />
        </button>
        <picker :range="scopes" :value="selectedDate ? 1 : 0" @change="selectScope($event.detail.value)">
          <view class="scope-picker">{{ selectedDate ? "选中日" : "全部" }}<view class="disclosure-icon" /></view>
        </picker>
      </view>
    </view>
    <view v-if="showSearch || searchTerm" class="row search history-search">
      <input v-model="q" :maxlength="100" aria-label="搜索报告或症状"
        placeholder="搜索报告或症状" confirm-type="search" @confirm="search" />
      <button class="search-button" @tap="search">搜索</button>
    </view>
    <view v-if="error" class="error">
      {{ error }} <text class="link" @tap="loadReports(rows.length === 0)">重试</text>
    </view>
    <view v-if="rows.length" class="day-records">
      <button v-for="report in rows" :key="report.id" class="history-card" @tap="open(report.id)">
        <view class="thumb"><AuthImage :file-id="report.image_id" /></view>
        <view class="record-content">
          <view class="row between record-heading">
            <text class="record-time">{{ dateText(report.created_at, true) }}</text>
            <text class="record-status">已归档</text>
          </view>
          <view class="record-summary">
            <text class="record-symptoms">{{ report.content.presentation?.symptoms_text || report.title }}</text>
            <view class="disclosure-icon right" aria-hidden="true" />
          </view>
        </view>
      </button>
    </view>
    <view v-if="!rows.length && !busy && !error" class="empty">
      {{ searchTerm ? "没有匹配的报告" : selectedDate ? "当天暂无舌照分析报告" : "暂无分析记录" }}
    </view>
    <view v-if="busy" class="loading">正在加载…</view>
    <button v-if="rows.length < total" class="outline spaced" :disabled="busy" @tap="loadReports()">加载更多</button>
    <RoleNav active="history" />
  </view>
</template>

<style scoped>
.calendar, .history-card {
  background: var(--surface);
  border: 1rpx solid var(--border);
  border-radius: 28rpx;
  box-shadow: var(--card-shadow);
}
.calendar { padding: 16rpx 12rpx 22rpx; }
.date-overview { margin: 0 14rpx 12rpx; }
.month-heading { font-size: var(--font-card); font-weight: 650; }
.calendar-controls { gap: 4rpx; }
.calendar-icon, .calendar-arrow, .calendar-action {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 60rpx;
  padding: 0;
  background: transparent;
  color: var(--primary);
}
.calendar-icon { min-width: 64rpx; border-radius: 18rpx; }
.calendar-icon.is-open { background: var(--soft); }
.calendar-arrow { min-width: 54rpx; font-size: 40rpx; line-height: 1; }
.calendar-action { padding: 0 10rpx; font-size: var(--font-caption); gap: 4rpx; }
.calendar button::after, .history-card::after, .search-toggle::after, .search-button::after { border: 0; }
.calendar-panel { animation: calendar-in 150ms ease-out; }
@keyframes calendar-in {
  from { opacity: 0; transform: translateY(-5rpx); }
  to { opacity: 1; transform: translateY(0); }
}
@media (prefers-reduced-motion: reduce) {
  .calendar-panel { animation: none; }
}
.week-picker, .week-days { display: flex; align-items: stretch; min-width: 0; }
.week-days { flex: 1; justify-content: space-between; }
.week-picker .week-arrow { min-width: 0; flex: 0 0 30rpx; align-self: flex-end; min-height: 64rpx; font-size: 36rpx; }
.week-day, .month-day {
  min-width: 0;
  overflow: visible;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0;
  color: var(--ink);
  background: transparent;
  line-height: 1.25;
}
.week-day { flex: 1 1 0; gap: 14rpx; }
.weekday { font-size: var(--font-caption); color: var(--secondary-ink); text-align: center; }
.calendar-day {
  position: relative;
  width: 66rpx;
  height: 66rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: var(--font-body);
  font-variant-numeric: tabular-nums;
}
.has-reports .calendar-day {
  background: var(--nav-background);
  color: var(--gold-card);
  font-weight: 650;
}
.has-reports .calendar-day::after {
  content: "";
  position: absolute;
  bottom: 9rpx;
  left: 50%;
  width: 7rpx;
  height: 7rpx;
  transform: translateX(-50%);
  border-radius: 50%;
  background: var(--surface);
}
.today .calendar-day { box-shadow: 0 0 0 2rpx var(--surface), 0 0 0 4rpx var(--accent); }
.selected .calendar-day::before {
  content: "";
  position: absolute;
  top: -7rpx;
  right: -7rpx;
  bottom: -7rpx;
  left: -7rpx;
  border: 3rpx solid var(--gold-card);
  border-radius: 50%;
  pointer-events: none;
}
.selected.has-reports .calendar-day::before { border-color: var(--gold); }
.month-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); row-gap: 5rpx; margin: 0 15rpx; }
.month-grid .weekday { padding-bottom: 9rpx; }
.month-day { min-height: 91rpx; }
.month-actions { margin: 3rpx 10rpx -8rpx; }
.month-actions .disclosure-icon { --chevron-size: 13rpx; }

.history-heading { margin: 30rpx 0 12rpx; padding-left: 8rpx; }
.history-caption, .history-controls { gap: 4rpx; }
.history-caption { flex-wrap: wrap; }
.history-controls { flex-shrink: 0; }
.history-caption .card-title { white-space: nowrap; }
.search-toggle, .search-button {
  padding: 0;
  background: transparent;
  font-size: var(--font-caption);
  color: var(--primary);
}
.search-toggle { min-width: 56rpx; min-height: 56rpx; display: grid; place-items: center; }
.scope-picker {
  display: flex;
  align-items: center;
  gap: 12rpx;
  min-height: 54rpx;
  padding: 0 22rpx;
  border: 1rpx solid var(--border);
  border-radius: 999rpx;
  background: var(--surface);
  color: var(--secondary-ink);
  font-size: var(--font-caption);
  white-space: nowrap;
}
.scope-picker .disclosure-icon { width: 14rpx; height: 14rpx; }
.history-search { margin: 0 0 12rpx; height: 76rpx; }
.search-button { padding: 0 12rpx; }
.day-records { display: grid; gap: 12rpx; }
.history-card {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 22rpx;
  margin: 0;
  padding: 20rpx 22rpx 20rpx 28rpx;
  text-align: left;
  color: var(--ink);
  line-height: 1.45;
}
.thumb { width: 138rpx; height: 144rpx; border-radius: 18rpx; flex-shrink: 0; overflow: hidden; }
.record-content { flex: 1; min-width: 0; align-self: stretch; padding-top: 4rpx; }
.record-heading { gap: 8rpx; }
.record-time { font-size: var(--font-body); font-weight: 650; font-variant-numeric: tabular-nums; }
.record-status {
  flex: none;
  padding: 2rpx 12rpx;
  border-radius: 999rpx;
  background: var(--soft);
  color: var(--deep);
  font-size: 21rpx;
}
.record-summary { display: flex; align-items: center; gap: 12rpx; margin-top: 12rpx; }
.record-summary .disclosure-icon { margin-left: auto; flex-shrink: 0; width: 15rpx; height: 15rpx; }
.record-symptoms {
  font-size: var(--font-body);
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
</style>
