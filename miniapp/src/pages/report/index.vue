<script setup lang="ts">
import { ref, computed } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import { api, download, toastError } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Report } from "@/types";
import AnnotatedPhoto from "@/components/AnnotatedPhoto.vue";
const report = ref<Report | null>(null),
  error = ref(""),
  exporting = ref(false);
const view = computed(() => report.value?.content.presentation);
const age = computed(() => {
  const value = Number(view.value?.identity?.age);
  return Number.isInteger(value) && value > 0 ? value : null;
});
const gender = computed(() => {
  const value = view.value?.identity?.gender?.trim();
  return value && value !== "未填写" ? value : "";
});
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
  <view class="page report-page">
    <view v-if="error" class="error">{{ error }}</view>
    <view v-else-if="!view" class="loading">正在读取报告…</view>
    <template v-if="report && view">
      <view class="report-header">
        <view class="page-title">舌象综合分析报告</view>
        <view class="report-meta row wrap">
          <text>{{ view.identity.report_date }}</text>
          <text v-if="age">{{ age }} 岁</text>
          <text v-if="gender">{{ gender }}</text>
        </view>
      </view>

      <AnnotatedPhoto :file-id="report.image_id" :annotations="report.content.annotations" />
      <view class="panel symptoms">
        <view class="card-title">症状自述</view>
        <view class="reading-text symptoms-body">{{ view.symptoms_text }}</view>
        <view v-if="view.duration && view.duration !== '未填写'" class="tiny report-meta">持续时间 · {{ view.duration }}</view>
      </view>

      <view class="report-reading">
        <view class="title reading-heading">舌象分析与教材解读</view>
        <view class="card-title reading-label">综合分析</view>
        <view class="reading-text">{{ view.analysis }}</view>

        <template v-if="readings.length">
          <view class="plain-reading">
            <view class="reading-label">教材白话解释</view>
            <view v-for="item in readings" :key="item.number" class="reading-entry reading-text">
              <text class="source-number">[{{ item.number }}]</text> {{ item.explanation }}
            </view>
          </view>
          <view class="textbook-quote">
            <view class="reading-label">对应教材原文</view>
            <view v-for="item in readings" :key="item.number" class="reading-entry">
              <view class="reading-text"><text class="source-number">[{{ item.number }}]</text> {{ item.quote }}</view>
              <view v-if="item.reference" class="source-note">{{ item.reference }}</view>
            </view>
          </view>
        </template>
      </view>

      <view v-if="view.advice_items?.length" class="panel advice">
        <view class="title">日常调护建议</view>
        <view v-for="(item, index) in view.advice_items" :key="index" class="advice-item">
          <view class="advice-category">{{ item.category }}</view>
          <view class="reading-text">{{ item.text }}</view>
        </view>
      </view>

      <view v-if="view.notice" class="report-notice tiny reading-text">{{ view.notice }}</view>

      <view class="report-actions">
        <view class="actions report-actions-inner">
          <button class="outline report-evidence" @tap="openEvidence">查看知识依据</button>
          <button class="primary" :disabled="exporting" :loading="exporting" @tap="exportPdf">导出 PDF</button>
        </view>
      </view>
    </template>
  </view>
</template>

<style scoped>
.report-page { padding-bottom: calc(148rpx + env(safe-area-inset-bottom)); }
.report-header { padding: 12rpx 0 20rpx; }
.report-meta { color: var(--secondary-ink); margin-top: 12rpx; overflow-wrap: anywhere; }
.report-header .report-meta { font-size: var(--font-caption); }
.report-header .report-meta text + text { padding-left: 16rpx; border-left: 1rpx solid var(--border); }
.symptoms-body { margin-top: 12rpx; }
.report-reading { margin: 34rpx 0 30rpx; }
.reading-heading { border-bottom: 1rpx solid var(--border); padding-bottom: 16rpx; margin-bottom: 22rpx; }
.reading-label { font-weight: 600; margin-bottom: 10rpx; }
.plain-reading { background: var(--soft); padding: 22rpx; border-radius: 16rpx; margin: 20rpx 0 10rpx; }
.reading-entry + .reading-entry { margin-top: 14rpx; }
.source-number { font-size: var(--font-caption); color: var(--secondary-ink); }
.advice-item { padding: 18rpx 0; font-size: var(--font-body); }
.advice-item + .advice-item { border-top: 1rpx solid var(--border); }
.advice-item:last-child { padding-bottom: 0; }
.advice-category { font-size: 28rpx; font-weight: 600; color: var(--primary); margin-bottom: 6rpx; }
.report-notice {
  border-top: 1rpx solid var(--border);
  padding: 18rpx 0 0;
  color: var(--secondary-ink);
  line-height: 1.7;
}
.report-actions {
  position: fixed;
  z-index: 20;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 14rpx var(--page-edge) calc(14rpx + env(safe-area-inset-bottom));
  border-top: 1rpx solid var(--border);
  background: var(--surface);
}
.report-actions-inner { margin: 0 auto; max-width: calc(var(--page-width) - var(--page-edge) - var(--page-edge)); }
.report-actions button { min-height: 88rpx; border-radius: 14rpx; font-size: var(--font-secondary); }
.report-actions .report-evidence { border-color: #b6c8bb; font-weight: 500; }
</style>
