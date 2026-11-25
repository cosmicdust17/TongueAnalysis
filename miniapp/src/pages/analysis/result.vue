<script setup lang="ts">
import { computed, ref } from "vue";
import { onLoad, onShow, onHide, onUnload } from "@dcloudio/uni-app";
import { api, ApiError, toastError } from "@/utils/request";
import { dismissSuggestion, getSuggestion, getTrackings, startTracking, type Suggestion } from "@/utils/health-trends";
import { requireAuth } from "@/stores/auth";
import type { Analysis, Report } from "@/types";
import PageHero from "@/components/PageHero.vue";
import AppIcon from "@/components/AppIcon.vue";
import AnnotatedPhoto from "@/components/AnnotatedPhoto.vue";
import RoleNav from "@/components/RoleNav.vue";
const task = ref<Analysis | null>(null),
  report = ref<Report | null>(null),
  error = ref(""),
  aid = ref(""),
  busy = ref(false);
const suggestion = ref<Suggestion | null>(null);
const suggestionBusy = ref(false);
const suggestionError = ref("");
let suggestionRequested = false;
let timer: ReturnType<typeof setTimeout> | undefined,
  visible = false,
  polling = false;

const stages = ["舌象与症状信息整理", "知识检索与关联分析", "分析报告生成"];
const activeStage = computed(() => {
  if (task.value?.status === "completed") return stages.length;
  if (task.value?.status !== "running") return -1;
  // The service records 55 after processing the image and symptoms.
  return task.value.progress >= 55 ? 1 : 0;
});
const waiting = computed(() => !error.value && !report.value && task.value?.status !== "failed");
const brief = computed(() => {
  const saved = report.value?.content.presentation;
  return saved?.brief || saved?.analysis || "";
});

onLoad((opts) => {
  aid.value = opts?.id || "";
});
onShow(() => {
  if (requireAuth("user")) {
    visible = true;
    if (!report.value) void poll();
  }
});
function stop() {
  visible = false;
  if (timer) clearTimeout(timer);
}
onHide(stop);
onUnload(stop);
async function poll() {
  if (polling) return;
  if (timer) clearTimeout(timer);
  if (!aid.value) {
    error.value = "缺少分析任务编号";
    return;
  }
  error.value = "";
  polling = true;
  try {
    const next = await api<Analysis>("/analyses/" + aid.value);
    task.value = next;
    if (next.status === "completed" && next.report_id) {
      report.value = await api<Report>("/reports/" + next.report_id);
      void loadSuggestion();
      if (uni.getStorageSync("active_analysis") === aid.value) uni.removeStorageSync("active_analysis");
    } else if (next.status !== "failed" && visible) {
      timer = setTimeout(poll, 1500);
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : "查询失败";
  } finally {
    polling = false;
  }
}
async function loadSuggestion() {
  if (suggestionRequested) return;
  suggestionRequested = true;
  suggestionError.value = "";
  try {
    const result = await getSuggestion(aid.value);
    suggestion.value = result.suggestion;
  } catch (e) {
    suggestionRequested = false;
    suggestionError.value = e instanceof Error ? e.message : "无法读取追踪建议";
  }
}
async function respondToSuggestion(start: boolean) {
  const item = suggestion.value;
  if (!item || suggestionBusy.value) return;
  suggestionBusy.value = true;
  suggestionError.value = "";
  try {
    if (start) await startTracking(item.symptom_name);
    else await dismissSuggestion(aid.value, item.symptom_name);
    suggestion.value = null;
    if (start) uni.showToast({ title: "已开始追踪", icon: "success" });
  } catch (e) {
    toastError(e);
    if (e instanceof ApiError && e.code === "suggestion_unavailable") suggestion.value = null;
    if (e instanceof ApiError && e.code === "tracking_limit_reached") {
      suggestionError.value = e.message;
      try {
        const board = await getTrackings();
        suggestionError.value = e.message + "（" + board.active_count + "/" + board.max_active + "）";
      } catch {
        // Keep the original conflict message if the refresh fails.
      }
    }
  } finally {
    suggestionBusy.value = false;
  }
}
async function retry() {
  if (busy.value) return;
  busy.value = true;
  try {
    await api("/analyses/" + aid.value + "/retry", "POST");
    await poll();
  } catch (e) {
    toastError(e);
  } finally {
    busy.value = false;
  }
}
function goHome() {
  uni.reLaunch({ url: '/pages/analysis/index' });
}
function openReport() {
  if (report.value)
    uni.navigateTo({ url: "/pages/report/index?id=" + report.value.id });
}
</script>
<template>
  <view class="page with-nav result-page">
    <template v-if="report">
      <view class="complete-header">
        <AppIcon name="check" :size="84" />
        <view class="page-title">本次分析已完成</view>
        <view class="tiny result-meta">报告已自动保存</view>
      </view>
      <AnnotatedPhoto :file-id="report.image_id" :annotations="report.content.annotations" compact />
      <view v-if="brief" class="panel summary">
        <view class="card-title">分析摘要</view>
        <view class="reading-text">{{ brief }}</view>
      </view>
      <view v-if="suggestion || suggestionError" class="panel suggestion">
        <template v-if="suggestion">
          <view class="card-title">是否追踪这项症状？</view>
          <view class="suggestion-name">{{ suggestion.symptom_name }}</view>
          <view class="actions">
            <button class="secondary button-small" :disabled="suggestionBusy" @tap="respondToSuggestion(true)">开始追踪</button>
            <button class="outline button-small" :disabled="suggestionBusy" @tap="respondToSuggestion(false)">暂不追踪</button>
          </view>
        </template>
        <view v-if="suggestionError" class="suggestion-error tiny">
          {{ suggestionError }}
          <button v-if="!suggestion" class="outline button-small spaced" @tap="loadSuggestion">重试</button>
        </view>
      </view>
      <button class="primary" @tap="openReport">查看完整报告</button>
      <button class="outline spaced home-button" @tap="goHome">返回首页</button>
    </template>

    <template v-else>
      <PageHero class="status-hero"
        :title="task?.status === 'failed' ? '分析暂未完成' : '正在整理分析报告'"
        :subtitle="task?.status === 'failed' ? undefined : '请稍候，完成后即可查看本次分析结果。'" />
      <view v-if="error" class="error">
        {{ error }}
        <button class="outline spaced" @tap="poll">重新查询</button>
      </view>
      <view v-else-if="waiting" class="panel progress-panel">
        <view class="card-title">分析进度</view>
        <view v-if="!task || task.status === 'queued'" class="result-meta tiny">{{ task ? "等待处理" : "正在查询任务状态" }}</view>
        <view v-else-if="task.status === 'completed'" class="result-meta tiny">正在读取已保存的报告</view>

        <view class="steps">
          <view v-for="(stage, index) in stages" :key="stage" class="step row"
            :class="{ current: index === activeStage, done: index < activeStage }">
            <view class="step-marker">
              <AppIcon v-if="index < activeStage" name="check" :size="24" />
              <view v-else class="step-dot" />
            </view>
            <text class="grow">{{ stage }}</text>
            <text class="tiny step-state">{{ index < activeStage ? "已完成" : index === activeStage ? "进行中" : "未开始" }}</text>
          </view>
        </view>
      </view>
      <view v-else-if="task?.status === 'failed'" class="panel">
        <view class="reading-text">分析暂时无法完成，请稍后重试。</view>
        <button class="primary spaced" :disabled="busy" :loading="busy" @tap="retry">重新尝试</button>
      </view>
      <view v-if="waiting" class="tiny result-meta">可离开本页，稍后从首页继续查看。</view>
    </template>
    <RoleNav active="analysis" />
  </view>
</template>

<style scoped>
.status-hero :deep(.hero-branch) { width: 116rpx; height: 134rpx; }
.result-meta { color: var(--secondary-ink); margin-top: 8rpx; }
.steps { margin-top: 18rpx; }
.step { position: relative; min-height: 88rpx; gap: 16rpx; color: var(--secondary-ink); font-size: 26rpx; }
.step + .step { border-top: 1rpx solid var(--border); }
.step-marker { width: 42rpx; height: 42rpx; flex-shrink: 0; border: 1rpx solid var(--border); border-radius: 50%; display: flex; align-items: center; justify-content: center; }
.step-dot { width: 12rpx; height: 12rpx; border-radius: 50%; background: var(--border); }
.current { color: var(--primary); font-weight: 600; }
.current .step-marker { border-color: var(--accent); background: var(--soft); }
.current .step-dot { background: var(--primary); }
.done .step-marker { background: var(--soft); }
.complete-header { padding: 22rpx 0 28rpx; text-align: center; }
.complete-header :deep(.app-icon) { margin: 0 auto 16rpx; }
.summary .reading-text { margin-top: 10rpx; }
.home-button { min-height: 82rpx; }
.suggestion { background: var(--tint); border: none; }
.suggestion-name { margin: 8rpx 0 16rpx; color: var(--deep); }
.suggestion-error { margin-top: 12rpx; color: var(--secondary-ink); }
</style>
