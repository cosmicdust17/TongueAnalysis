<script setup lang="ts">
import { ref, computed } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import { api, dateText, download, toastError } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Report } from "@/types";
import AnnotatedPhoto from "@/components/AnnotatedPhoto.vue";
import AuthImage from "@/components/AuthImage.vue";
import AppIcon from "@/components/AppIcon.vue";
const report = ref<Report | null>(null),
  error = ref(""),
  exporting = ref(false),
  photoOpen = ref(false),
  analysisOpen = ref(false);
const view = computed(() => report.value?.content.presentation);
const age = computed(() => {
  const value = Number(view.value?.identity?.age);
  return Number.isInteger(value) && value > 0 ? value : null;
});
const gender = computed(() => {
  const value = view.value?.identity?.gender?.trim();
  return value && value !== "未填写" ? value : "";
});
const maskedId = computed(() => {
  const id = view.value?.identity?.user_id?.trim();
  if (!id) return "未填写";
  return id.length > 8 ? "•••• " + id.slice(-4) : "••••";
});
const summary = computed(() => view.value?.brief?.trim() || view.value?.analysis || "");
const readings = computed(() => {
  const content = view.value;
  if (!content) return [];
  return (content.evidence || []).filter(item => content.analysis?.includes("[" + item.number + "]"));
});
function openEvidence() {
  if (report.value) uni.navigateTo({ url: "/subpackages/user/evidence?id=" + encodeURIComponent(report.value.id) });
}
onLoad(async (opts) => {
  if (!requireAuth("user")) return;
  try {
    report.value = await api<Report>("/reports/" + (opts?.id || ""));
  } catch (e) {
    error.value = e instanceof Error ? e.message : "读取失败";
  }
});
async function exportPdf() {
  if (!report.value || exporting.value) return;
  exporting.value = true;
  try {
    const path = await download("/reports/" + report.value.id + "/pdf");
    await new Promise<void>((resolve, reject) =>
      uni.openDocument({
        filePath: path,
        fileType: "pdf",
        showMenu: true,
        success: () => resolve(),
        fail: reject,
      }),
    );
  } catch (e) {
    toastError(e);
  } finally {
    exporting.value = false;
  }
}
</script>
<template>
  <view class="page olive-sheet report-page">
    <view v-if="error" class="error">{{ error }}</view>
    <view v-else-if="!view" class="loading">正在读取报告…</view>
    <template v-if="report && view">
      <view class="report-header">
        <image class="report-branch" src="/static/branch.png" mode="aspectFit" />
        <view class="page-title">舌象综合分析报告</view>
        <view class="report-meta">{{ view.identity?.report_date || dateText(report.created_at) }}</view>
        <view class="report-identity">
          <view>用户 ID：{{ maskedId }}</view>
          <view class="row between">
            <text>年龄：{{ age ? age + " 岁" : "未填写" }}</text>
            <text>性别：{{ gender || "未填写" }}</text>
          </view>
        </view>
      </view>

      <view class="photo-card">
        <view class="row photo-row">
          <view class="photo-thumb"><AuthImage :file-id="report.image_id" /></view>
          <view class="grow">
            <view class="card-title">舌象信息</view>
            <view class="tiny muted">查看本次舌象照片</view>
          </view>
          <button class="photo-toggle" :aria-expanded="photoOpen" @tap="photoOpen = !photoOpen">
            {{ photoOpen ? "收起舌象" : "查看舌象" }}
            <view class="disclosure-icon" :class="photoOpen ? 'expanded' : 'right'" aria-hidden="true" />
          </button>
        </view>
        <view v-if="photoOpen" class="photo-content">
          <AnnotatedPhoto :file-id="report.image_id" :annotations="report.content.annotations" embedded />
        </view>
      </view>

      <view class="report-section symptoms-section">
        <image class="section-branch" src="/static/branch.png" mode="aspectFit" />
        <view class="row section-title">
          <view class="section-icon"><AppIcon name="document" :size="35" /></view>
          <text class="card-title">症状自述</text>
        </view>
        <view class="reading-text">{{ view.symptoms_text || "未填写" }}</view>
        <view class="report-duration">持续时间：{{ view.duration || "未填写" }}</view>
      </view>

      <view class="report-section analysis-section">
        <image class="section-branch" src="/static/branch.png" mode="aspectFit" />
        <button v-if="readings.length || (view.analysis && view.analysis !== summary)" class="analysis-toggle"
          :aria-expanded="analysisOpen" @tap="analysisOpen = !analysisOpen">
          <view class="row section-title">
            <view class="section-icon"><AppIcon name="leaf" :size="35" /></view>
            <text class="card-title">舌象分析与教材解读</text>
          </view>
          <view class="row analysis-summary">
            <text class="reading-text">{{ summary }}</text>
            <view class="disclosure-icon" :class="analysisOpen ? 'expanded' : 'right'" aria-hidden="true" />
          </view>
        </button>
        <template v-else>
          <view class="row section-title">
            <view class="section-icon"><AppIcon name="leaf" :size="35" /></view>
            <text class="card-title">舌象分析与教材解读</text>
          </view>
          <view class="reading-text">{{ summary }}</view>
        </template>
        <view v-if="analysisOpen" class="analysis-details">
          <view v-if="view.analysis !== summary" class="reading-group">
            <view class="reading-label">综合分析</view>
            <view class="reading-text">{{ view.analysis }}</view>
          </view>
          <template v-if="readings.length">
            <view class="reading-group">
              <view class="reading-label">教材白话解释</view>
              <view v-for="item in readings" :key="item.number" class="reading-entry reading-text">[{{ item.number }}] {{ item.explanation }}</view>
            </view>
            <view class="reading-group">
              <view class="reading-label">教材原文与出处</view>
              <view v-for="item in readings" :key="item.number" class="reading-entry">
                <view class="reading-text">[{{ item.number }}] {{ item.quote }}</view>
                <view v-if="item.reference" class="source-note">{{ item.reference }}</view>
              </view>
            </view>
          </template>
        </view>
      </view>

      <view v-if="view.advice_items?.length" class="report-section advice-section">
        <image class="section-branch" src="/static/branch.png" mode="aspectFit" />
        <view class="row section-title">
          <view class="section-icon"><AppIcon name="book" :size="35" /></view>
          <text class="card-title">日常调护建议</text>
        </view>
        <view v-for="(item, index) in view.advice_items" :key="index" class="advice-item">
          <view class="advice-marker" aria-hidden="true" />
          <view class="reading-text"><text v-if="item.category" class="advice-label">{{ item.category }}：</text>{{ item.text }}</view>
        </view>
      </view>

      <view v-if="view.notice" class="report-notice tiny reading-text">{{ view.notice }}</view>
      <view class="actions report-actions">
        <button class="outline report-evidence" @tap="openEvidence">查看知识依据</button>
        <button class="primary" :disabled="exporting" :loading="exporting" @tap="exportPdf">导出 PDF</button>
      </view>
    </template>
  </view>
</template>

<style scoped>
.report-page { padding-bottom: calc(26rpx + env(safe-area-inset-bottom)); }
.report-header { position: relative; margin: 10rpx 0 26rpx; }
.report-header .page-title, .report-meta, .report-identity { position: relative; }
.report-meta { color: var(--secondary-ink); margin: 6rpx 0 28rpx; font-size: var(--font-secondary); }
.report-branch, .section-branch { position: absolute; pointer-events: none; filter: var(--branch-tone); }
.report-branch { width: 145rpx; height: 180rpx; right: 0; top: -12rpx; opacity: .52; transform: rotate(13deg); }
.report-identity, .photo-card, .report-section {
  border: 1rpx solid var(--border);
  border-radius: 26rpx;
  box-shadow: var(--card-shadow);
}
.report-identity { display: grid; gap: 12rpx; padding: 18rpx 24rpx; background: var(--surface); font-size: var(--font-caption); overflow-wrap: anywhere; }
.photo-card { padding: 16rpx 22rpx; margin-bottom: 26rpx; background: var(--surface); }
.photo-row { gap: 18rpx; }
.photo-row .tiny { line-height: 1.4; }
.photo-thumb { width: 106rpx; height: 110rpx; flex-shrink: 0; overflow: hidden; border-radius: 16rpx; }
.photo-toggle { flex-shrink: 0; display: flex; align-items: center; justify-content: center; gap: 10rpx; min-height: 60rpx; padding: 0 18rpx; border-radius: 999rpx; color: #fff; background: var(--primary); font-size: var(--font-caption); }
.photo-toggle .disclosure-icon { width: 18rpx; height: 18rpx; flex: 0 0 18rpx; color: #fff; --chevron-size: 10rpx; }
.photo-content { margin-top: 20rpx; }
.report-section {
  position: relative;
  overflow: hidden;
  padding: 16rpx 28rpx 22rpx;
  margin-bottom: 24rpx;
  background: linear-gradient(135deg, var(--soft), var(--surface));
}
.analysis-section { background: linear-gradient(135deg, var(--sage-card), var(--surface)); }
.advice-section { background: linear-gradient(135deg, var(--gold-card), var(--surface) 70%); }
.section-branch { right: -2rpx; top: -33rpx; width: 142rpx; height: 161rpx; transform: rotate(42deg); opacity: .29; }
.advice-section .section-branch { opacity: .26; }
.section-title { position: relative; gap: 17rpx; margin-bottom: 12rpx; }
.section-icon { display: grid; place-items: center; flex-shrink: 0; width: 66rpx; height: 66rpx; border-radius: 50%; background: var(--accent); }
.section-icon :deep(.app-icon) { filter: brightness(0) invert(1); }
.analysis-section .section-icon { background: var(--trend-sage); }
.advice-section .section-icon { background: var(--gold); }
.report-section .reading-text, .report-duration { position: relative; font-size: var(--font-secondary); color: var(--ink); line-height: 1.56; }
.report-duration { margin-top: 6rpx; color: var(--secondary-ink); }
.analysis-toggle { position: relative; width: 100%; padding: 0; color: inherit; text-align: left; background: transparent; border-radius: 0; }
.analysis-toggle::after, .photo-toggle::after { border: 0; }
.analysis-summary { gap: 18rpx; }
.analysis-summary .disclosure-icon { width: 15rpx; height: 15rpx; margin-left: auto; flex-shrink: 0; }
.analysis-details { margin-top: 16rpx; position: relative; }
.reading-group { padding-top: 13rpx; margin-top: 13rpx; border-top: 1rpx solid var(--border); }
.reading-label, .advice-label { font-weight: 600; color: var(--deep); }
.reading-label { margin-bottom: 6rpx; }
.reading-entry + .reading-entry { margin-top: 14rpx; }
.advice-item { display: flex; align-items: flex-start; gap: 13rpx; margin-top: 5rpx; }
.advice-marker { flex: 0 0 11rpx; height: 11rpx; margin-top: 15rpx; border-radius: 50%; background: var(--accent); }
.report-notice { padding: 2rpx 8rpx 14rpx; color: var(--secondary-ink); line-height: 1.7; }
.report-actions { margin-top: 12rpx; }
.report-actions button { min-height: 86rpx; border-radius: 999rpx; font-size: var(--font-secondary); }
</style>
