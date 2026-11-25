<script setup lang="ts">
import { ref, computed } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { api, ApiError, upload, toastError } from "@/utils/request";
import { beijingDate } from "@/utils/beijing-date";
import { getTrackings, levels, saveCheckin, type Level, type Tracking, type Trackings } from "@/utils/health-trends";
import { requireAuth } from "@/stores/auth";
import type { Analysis, Report } from "@/types";
import PageHero from "@/components/PageHero.vue";
import AppIcon from "@/components/AppIcon.vue";
import RoleNav from "@/components/RoleNav.vue";
const image = ref(""),
  symptoms = ref(""),
  selected = ref<string[]>([]),
  duration = ref(1),
  busy = ref(false),
  active = ref("");
const tags = ["口干", "乏力", "睡眠不佳", "消化不佳", "咽干", "腹胀", "头痛", "心悸"],
  durations = ["近三天", "近一周", "近一个月", "一个月以上"];
const description = computed(() =>
  [...selected.value, symptoms.value].filter(value => value.trim()).join("，"),
);
const showAllTags = ref(false);
const visibleTags = computed(() => showAllTags.value ? tags : tags.filter((tag, index) => index < 4 || selected.value.includes(tag)));
const checkinOpen = ref(false);
const latestReport = ref("");
const trackingBoard = ref<Trackings | null>(null);
const trackingError = ref(false);
const activeTrackings = computed(() => trackingBoard.value?.items.filter(item => item.active).slice(0, 2) ?? []);
const savingTrackingId = ref("");
let trackingRequest = 0;

onShow(() => {
  if (requireAuth("user")) {
    active.value = uni.getStorageSync("active_analysis") || "";
    void refreshTrackings();
    if (!active.value) void loadLatestReport();
  }
});

async function loadLatestReport() {
  try {
    const result = await api<{ items: Report[] }>("/reports?page=1&page_size=1");
    latestReport.value = result.items[0]?.id ?? "";
  } catch {
    latestReport.value = "";
  }
}

async function refreshTrackings() {
  const request = ++trackingRequest;
  trackingError.value = false;
  try {
    const board = await getTrackings();
    if (request === trackingRequest) trackingBoard.value = board;
  } catch {
    if (request === trackingRequest) trackingError.value = true;
  }
}

async function checkIn(item: Tracking, level: Level) {
  if (savingTrackingId.value || (trackingBoard.value?.date === beijingDate() && item.today_level === level)) return;
  savingTrackingId.value = item.id;
  try {
    const saved = await saveCheckin(item.id, level);
    if (trackingBoard.value?.date === saved.date) {
      const current = trackingBoard.value.items.find(tracking => tracking.id === item.id);
      if (current) current.today_level = saved.level;
    }
    await refreshTrackings();
  } catch (error) {
    toastError(error);
    if (error instanceof ApiError && (error.code === "tracking_paused" || error.status === 404)) {
      await refreshTrackings();
    }
  } finally {
    savingTrackingId.value = "";
  }
}

function toggle(tag: string) {
  selected.value = selected.value.includes(tag)
    ? selected.value.filter((x) => x !== tag)
    : [...selected.value, tag];
}
function choose(sourceType: ("camera" | "album")[]) {
  uni.chooseImage({
    count: 1,
    sizeType: ["compressed"],
    sourceType,
    success: (r) => {
      image.value = r.tempFilePaths[0];
    },
    fail: () => {},
  });
}
function resume() {
  if (active.value) {
    uni.navigateTo({ url: "/pages/analysis/result?id=" + encodeURIComponent(active.value) });
  } else if (latestReport.value) {
    uni.navigateTo({ url: "/pages/report/index?id=" + encodeURIComponent(latestReport.value) });
  }
}
async function submit() {
  if (busy.value) return;
  if (!image.value || !description.value) {
    uni.showToast({ title: "请上传舌象并描述症状", icon: "none" });
    return;
  }
  if (description.value.length > 200) {
    uni.showToast({ title: "症状描述合计不能超过200字", icon: "none" });
    return;
  }
  busy.value = true;
  try {
    const file = await upload(image.value);
    const task = await api<Analysis>("/analyses", "POST", {
      image_id: file.id,
      symptoms: description.value,
      duration: durations[duration.value],
      confirmed_symptoms: selected.value.slice(0, 20),
    });
    uni.setStorageSync("active_analysis", task.id);
    active.value = task.id;
    uni.navigateTo({ url: "/pages/analysis/result?id=" + task.id });
  } catch (e) {
    toastError(e);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <view class="page olive-sheet with-nav analysis-home">
    <PageHero class="home-hero" title="从舌象，了解身体" subtitle="记录舌象与症状，获取综合分析" />
    <button v-if="active || latestReport" class="resume row between" hover-class="resume-pressed" @tap="resume">
      <view class="row resume-label"><AppIcon name="document" :size="34" /><text>有一条分析记录可继续查看</text></view>
      <text class="resume-action">查看 ›</text>
    </button>

    <view class="panel upload-panel">
      <view class="card-title form-heading">上传舌象</view>
      <view class="upload-zone" @tap="choose(['camera', 'album'])">
        <image v-if="image" :src="image" mode="aspectFit" class="preview" aria-label="已选舌象" />
        <template v-else>
          <AppIcon name="camera" :size="58" />
          <view class="upload-title">拍照或选择照片</view>
          <view class="tiny helper">使用自然光，保持舌面清晰</view>
        </template>
      </view>
      <view class="actions photo-actions">
        <button class="secondary" @tap="choose(['camera'])">
          <AppIcon name="camera" :size="34" />{{ image ? "重新拍摄" : "拍照" }}
        </button>
        <button class="secondary" @tap="choose(['album'])">
          <AppIcon name="image" :size="34" />{{ image ? "重新选择" : "相册" }}
        </button>
      </view>
    </view>

    <view class="panel tag-panel">
      <view class="card-title form-heading">症状标签 <text class="tiny tag-note">（可多选）</text></view>
      <view class="row tag-row">
        <view class="chips grow">
          <button v-for="tag in visibleTags"
            :key="tag" class="chip symptom-chip" :class="{ active: selected.includes(tag) }"
            :aria-pressed="selected.includes(tag)" @tap="toggle(tag)">{{ tag }}</button>
        </view>
        <button class="tag-toggle" aria-label="更多症状" :aria-expanded="showAllTags" @tap="showAllTags = !showAllTags">
          <view class="disclosure-icon" :class="{ expanded: showAllTags }" />
        </button>
      </view>
    </view>

    <view class="panel symptoms-panel">
      <view class="card-title form-heading">症状描述</view>
      <view class="field-area symptom-field">
        <textarea v-model="symptoms" :maxlength="200" aria-label="近期症状"
          placeholder="描述近期身体感受，例如容易疲倦、睡眠较浅、食欲一般等" placeholder-class="symptom-placeholder" />
        <view class="counter tiny" :class="{ danger: description.length > 200 }">{{ description.length }}/200</view>
        <view v-if="description.length > 200" class="tiny danger">症状标签与文字合计最多 200 字</view>
      </view>
    </view>

    <view class="daily-checkin">
      <button class="checkin-entry" :aria-expanded="checkinOpen" @tap="checkinOpen = !checkinOpen">
        <AppIcon name="calendar" :size="36" />
        <text class="checkin-title">每日自查</text>
        <text class="grow tiny checkin-caption">简单记录当日状态，长周期了解体质</text>
        <view class="disclosure-icon" :class="{ expanded: checkinOpen }" aria-hidden="true" />
      </button>
      <view v-if="checkinOpen" class="checkin-content">
        <view v-if="trackingError" class="row between checkin-empty">
          <text class="tiny">暂时无法读取追踪项目</text>
          <text class="link tiny" @tap="refreshTrackings">重试</text>
        </view>
        <view v-else-if="!trackingBoard" class="tiny checkin-caption">正在读取追踪项目…</view>
        <view v-else-if="!activeTrackings.length" class="row between checkin-empty">
          <text class="tiny">前往健康趋势开启症状追踪</text>
          <navigator url="/subpackages/user/trends" open-type="reLaunch" class="link tiny">健康趋势 ›</navigator>
        </view>
        <view v-for="item in activeTrackings" :key="item.id" class="checkin-row">
          <view class="row between">
            <text class="checkin-symptom">{{ item.symptom_name }}</text>
            <text v-if="savingTrackingId === item.id" class="tiny checkin-caption" role="status">保存中…</text>
          </view>
          <view class="checkin-levels">
            <button v-for="(label, index) in levels" :key="label" class="checkin-level"
              :class="{ selected: item.today_level === index }" :aria-pressed="item.today_level === index"
              :aria-label="item.symptom_name + ' ' + label" :disabled="!!savingTrackingId"
              @tap="checkIn(item, index as Level)">{{ label }}</button>
          </view>
        </view>
      </view>
    </view>

    <picker :range="durations" :value="duration" @change="duration = Number($event.detail.value)">
      <view class="field select-field duration">
        <text class="duration-label">持续时间</text>
        <view class="select-value">{{ durations[duration] }}<view class="disclosure-icon" aria-hidden="true" /></view>
      </view>
    </picker>

    <button class="primary analyze-button" :loading="busy" :disabled="busy" @tap="submit">
      {{ busy ? "正在提交" : "开始分析" }}
    </button>
    <RoleNav active="analysis" />
  </view>
</template>

<style scoped>
.analysis-home { padding-top: 10rpx; }
.home-hero { min-height: 156rpx; padding: 20rpx 14rpx 18rpx; }
.home-hero :deep(.hero-title) { font-size: 44rpx; }
.home-hero :deep(.hero-branch) { width: 178rpx; height: 174rpx; opacity: 0.7; }
.analysis-home .panel { margin-bottom: 14rpx; padding: 16rpx 24rpx; }
.form-heading { margin-bottom: 12rpx; }
.resume {
  width: 100%;
  min-height: 76rpx;
  margin: 0 0 18rpx;
  padding: 8rpx 16rpx;
  border: 1rpx solid var(--border);
  border-radius: 18rpx;
  background: var(--soft);
  color: var(--deep);
  font-size: var(--font-caption);
  text-align: left;
}
.resume::after, .tag-toggle::after, .checkin-entry::after { border: 0; }
.resume.resume-pressed { opacity: 0.78; }
.resume-label { min-width: 0; gap: 8rpx; }
.resume-action {
  padding: 6rpx 14rpx;
  border: 1rpx solid var(--border);
  border-radius: 44rpx;
  background: var(--surface);
  font-weight: 600;
  flex-shrink: 0;
}
.upload-zone {
  height: 216rpx;
  border: 2rpx dashed var(--dash);
  border-radius: 18rpx;
  background: var(--tint);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6rpx;
  overflow: hidden;
}
.preview { height: 100%; width: 100%; }
.upload-title { color: var(--deep); font-weight: 600; }
.helper, .counter, .tag-note, .checkin-caption { color: var(--secondary-ink); }
.photo-actions { margin-top: 12rpx; }
.photo-actions button { min-height: 68rpx; border-radius: 16rpx; font-size: var(--font-secondary); }
.tag-row, .tag-row .chips { gap: 8rpx; }
.tag-note { font-weight: 400; }
.symptom-chip {
  margin: 0;
  min-height: 52rpx;
  padding: 4rpx 12rpx;
  border-color: var(--border);
  color: var(--deep);
  font-size: var(--font-caption);
}
.symptom-chip.active { background: var(--soft); color: var(--deep); border-color: var(--dash); font-weight: 600; }
.tag-toggle {
  min-width: 44rpx;
  min-height: 56rpx;
  padding: 0;
  display: flex;
  justify-content: center;
  align-items: center;
  background: transparent;
}
.symptom-field { padding: 0 16rpx 8rpx; background: var(--page); }
.symptom-field textarea {
  height: 100rpx;
  min-height: 100rpx;
  padding: 10rpx 0 0;
  font-size: var(--font-body);
  line-height: 1.45;
}
:deep(.symptom-placeholder) { color: var(--secondary-ink); }
.counter { text-align: right; }
.counter.danger { color: #a94237; }
.daily-checkin { border-radius: 16rpx; background: var(--soft); }
.checkin-entry {
  width: 100%;
  min-height: 72rpx;
  display: flex;
  gap: 8rpx;
  align-items: center;
  padding: 8rpx 16rpx;
  text-align: left;
  color: var(--deep);
  background: transparent;
}
.checkin-title { flex-shrink: 0; font-weight: 600; font-size: var(--font-body); }
.checkin-caption { line-height: 1.4; }
.checkin-content { padding: 0 16rpx 14rpx; }
.checkin-empty { gap: 8rpx; }
.checkin-empty .link { flex-shrink: 0; }
.checkin-row { margin-top: 8rpx; }
.checkin-symptom { font-size: var(--font-secondary); font-weight: 600; overflow-wrap: anywhere; }
.checkin-levels { display: flex; gap: 6rpx; margin-top: 6rpx; }
.checkin-level {
  flex: 1 1 0;
  min-width: 0;
  min-height: 66rpx;
  margin: 0;
  padding: 4rpx;
  border-radius: 10rpx;
  background: var(--surface);
  color: var(--deep);
  font-size: var(--font-caption);
  line-height: 1.35;
}
.checkin-level::after { border: 0; }
.checkin-level.selected { background: var(--primary); color: #fff; }
.duration { margin-top: 14rpx; min-height: 72rpx; background: var(--surface); }
.duration-label { font-weight: 600; }
.analyze-button { margin-top: 18rpx; min-height: 80rpx; border-radius: 44rpx; }
</style>
