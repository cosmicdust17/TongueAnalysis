<script setup lang="ts">
import { ref, computed } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import { api, download, toastError } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Report } from "@/types";
import AppIcon from "@/components/AppIcon.vue";
import AnnotatedPhoto from "@/components/AnnotatedPhoto.vue";
const report = ref<Report | null>(null),
  error = ref(""),
  showEvidence = ref(false),
  exporting = ref(false);
const view = computed(() => report.value?.content.presentation);
onLoad(async (opts) => {
  if (!requireAuth("user")) return;
  try {
    report.value = await api<Report>("/reports/" + (opts?.id || ""));
  } catch (e) {
    error.value = e instanceof Error ? e.message : "读取失败";
  }
});
async function exportPdf() {
  if (!report.value) return;
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
    <view v-if="error" class="error">{{error}}</view>
    <view v-if="!view && !error" class="loading">正在读取报告…</view>
    <template v-if="report && view">
      <view class="report-header">
        <view class="report-title">{{view.title}}</view>
        <view class="muted small">{{view.identity.report_date}}</view>
      </view>
      <view class="panel">
        <view class="small identity">用户 ID：{{view.identity.user_id}}</view>
        <view class="row between spaced"><text>年龄：{{view.identity.age}}</text><text>性别：{{view.identity.gender}}</text></view>
      </view>
      <AnnotatedPhoto :file-id="report.image_id" :annotations="report.content.annotations"/>
      <view class="panel"><view class="title">症状自述</view><view class="spaced original-text">{{view.symptoms_text}}</view><view class="muted small spaced">持续时间：{{view.duration}}</view></view>
      <view class="panel"><view class="title">舌象分析</view>
        <view class="spaced original-text report-analysis">{{view.analysis}}</view>
      </view>
      <view class="panel"><view class="title">日常建议</view><view v-for="item in view.advice_items" :key="item.category" class="spaced"><view class="subtitle">{{item.category}}</view><view class="spaced">{{item.text}}</view></view></view>
      <view class="panel"><view class="title">知识依据</view><button class="outline spaced" @tap="showEvidence=true">查看知识依据</button></view>
      <view class="actions section"><button class="primary" :disabled="exporting" :loading="exporting" @tap="exportPdf"><AppIcon name="download" :size="34"/>导出报告</button></view>
      <view v-if="view.evidence.length" class="references muted small"><view class="reference-title">参考</view><view v-for="item in view.evidence" :key="item.number" class="reference-item">[{{item.number}}] {{item.reference}}</view></view>
      <view class="muted small spaced">{{view.notice}}</view>
      <view v-if="showEvidence" class="overlay" @tap="showEvidence=false"><view class="sheet" @tap.stop>
        <view class="row between section"><view class="title">知识依据</view><view class="chevron" @tap="showEvidence=false">×</view></view>
        <scroll-view scroll-y class="sheet-scroll"><view v-if="!view.evidence.length" class="empty">暂缺可直接对应的教材依据。</view>
          <view v-for="item in view.evidence" :key="item.number" class="panel spaced"><view class="subtitle">[{{item.number}}] 白话解读</view><view class="spaced">{{item.explanation}}</view><view class="subtitle spaced">教材原文</view><view class="spaced original-text">{{item.quote}}</view><view class="muted small spaced">{{item.reference}}</view></view>
        </scroll-view>
      </view></view>
    </template>
  </view>
</template>
<style scoped>
page { background: #fff; }
.report-page { background: #fff; color: #272727; }
.report-header { padding: 12rpx 0 24rpx; margin-bottom: 24rpx; border-bottom: 1rpx solid #dedede; }
.report-title { font-size: 47rpx; font-weight: 700; line-height: 1.35; margin-bottom: 10rpx; color: #214a39; }
.panel { border-color: #e2e2e2; box-shadow: none; }
.identity { word-break: break-all; }
.original-text { white-space: pre-wrap; overflow-wrap: anywhere; }
.report-analysis { line-height: 1.75; }
.muted, .empty, .loading { color: #666; }
.chevron { color: #087f56; }
.error { color: #272727; background: #f5f5f5; border-color: #ddd; }
.primary { background: #07875e; color: #fff; }
.outline { border: 1rpx solid #0a885f; color: #087f56; }
.overlay { background: rgba(0, 0, 0, .38); }
.references { border-top: 1rpx solid #dedede; padding-top: 18rpx; }
.reference-title { font-weight: 600; color: #214a39; }
.reference-item { margin-top: 10rpx; }
</style>
