<script setup lang="ts">
import { ref, computed } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import { requireAuth } from "@/stores/auth";
import { api } from "@/utils/request";
import { evidenceTitle } from "@/utils/evidence-title";
import type { Evidence, Report, TextbookReading } from "@/types";

const id = ref("");
const report = ref<Report | null>(null);
const snapshots = ref<Evidence[]>([]);
const loading = ref(true);
const error = ref("");
const expanded = ref<number[]>([]);

const entries = computed(() => {
  const saved = report.value?.content.presentation?.evidence || [];
  const remaining = new Set(saved);
  const rows: { source?: Evidence; reading?: TextbookReading }[] = snapshots.value.map(source => {
    const key = source.chunk_id || source.entity_id;
    const reading = saved.find(item => (key && item.chunk_id === key) ||
      (!item.chunk_id && !!source.text && item.quote === source.text.trim()));
    if (reading) remaining.delete(reading);
    return { source, reading };
  });
  return rows.concat([...remaining].map(reading => ({ reading })))
    .map(entry => ({ ...entry, title: evidenceTitle(entry.source, entry.reading) }));
});

function sourceLocation(source?: Evidence) {
  const loc = source?.location;
  if (!loc) return [];
  const reviewed = source?.source_review_status === "approved" || source?.ocr_status === "approved";
  const page = loc.printed_page != null && reviewed
    ? "印刷第 " + loc.printed_page + " 页"
    : loc.pdf_page != null ? "PDF 第 " + loc.pdf_page + " 页" : "";
  const paragraph = loc.paragraph != null && reviewed
    ? "第 " + loc.paragraph + " 段"
    : loc.block_on_page != null ? "页内第 " + loc.block_on_page + " 块" : "";
  return [loc.chapter, page, paragraph].filter(Boolean);
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const path = "/reports/" + encodeURIComponent(id.value);
    const [detail, snapshot] = await Promise.all([
      api<Report>(path),
      api<{ items: Evidence[] }>(path + "/evidence"),
    ]);
    report.value = detail;
    snapshots.value = snapshot.items;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "读取知识依据失败";
  } finally {
    loading.value = false;
  }
}
onLoad(opts => {
  if (!requireAuth("user")) return;
  id.value = opts?.id || "";
  if (id.value) void load();
  else {
    loading.value = false;
    error.value = "缺少报告编号";
  }
});
function toggle(index: number) {
  expanded.value = expanded.value.includes(index)
    ? expanded.value.filter(value => value !== index)
    : [...expanded.value, index];
}
function cited(reading?: TextbookReading) {
  return reading && report.value?.content.presentation?.analysis?.includes("[" + reading.number + "]");
}
</script>

<template>
  <view class="page evidence-page">
    <view class="page-title evidence-heading">知识依据</view>
    <view v-if="loading" class="loading">正在读取知识依据…</view>
    <view v-else-if="error" class="error">
      {{ error }}
      <button v-if="id" class="outline spaced" @tap="load">重新读取</button>
    </view>
    <view v-else-if="!entries.length" class="empty">本次分析暂无可查看的教材依据。</view>
    <template v-else>
      <view class="small evidence-count">共 {{ entries.length }} 条</view>
      <view class="evidence-list">
        <view v-for="({ source, reading, title }, index) in entries" :key="index" class="evidence-entry">
          <button class="evidence-toggle row" hover-class="evidence-pressed" :aria-expanded="expanded.includes(index)" @tap="toggle(index)">
            <text class="grow">{{ title }}</text>
            <text class="toggle-label">{{ expanded.includes(index) ? "收起" : "展开" }}</text>
            <view class="disclosure-icon" :class="{ expanded: expanded.includes(index) }" aria-hidden="true" />
          </button>
          <view v-if="expanded.includes(index)" class="evidence-body">
            <view class="evidence-association">
              <text v-if="source?.is_demo">示例资料 · </text>
              {{ cited(reading) ? "综合分析引用了这段内容。" : source ? "本次分析检索到的资料。" : "报告中保存的教材解读。" }}
            </view>
            <view v-if="reading?.explanation" class="evidence-item">
              <view class="evidence-label">白话解释</view>
              <view class="reading-text">{{ reading.explanation }}</view>
            </view>
            <view v-if="source?.text || reading?.quote" class="evidence-item">
              <view class="evidence-label">{{ source?.is_demo ? "资料原文" : "教材原文" }}</view>
              <view class="reading-text">{{ source?.text || reading?.quote }}</view>
              <view v-if="reading?.reference" class="source-note evidence-source">{{ reading.reference }}</view>
              <view v-else class="source-note evidence-source reading-text">
                <view v-if="source?.source_title">{{ source.source_title }}</view>
                <view v-if="sourceLocation(source).length">{{ sourceLocation(source).join(" · ") }}</view>
                <view v-else-if="source?.citation && !source.citation.trim().startsWith('{')">{{ source.citation }}</view>
              </view>
            </view>
          </view>
        </view>
      </view>
    </template>
  </view>
</template>

<style scoped>
.evidence-heading {
  margin-bottom: 8rpx;
}
.evidence-count {
  color: var(--secondary-ink);
  margin-bottom: 20rpx;
}
.evidence-list {
  padding: 0 22rpx;
  background: var(--surface);
  border-radius: 20rpx;
}
.evidence-entry {
  display: flex;
  flex-direction: column;
}
.evidence-entry + .evidence-entry {
  border-top: 1rpx solid var(--border);
}
.evidence-toggle {
  width: 100%;
  min-height: 96rpx;
  padding: 16rpx 0;
  gap: 10rpx;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--ink);
  text-align: left;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.evidence-toggle::after {
  border: 0;
}
.evidence-toggle.evidence-pressed {
  opacity: 0.72;
}
.toggle-label {
  color: var(--deep);
  font-size: var(--font-caption);
  font-weight: 400;
  white-space: nowrap;
}
.evidence-body {
  margin: 0 0 18rpx;
  padding: 20rpx 22rpx 22rpx;
  border-radius: 14rpx;
  background: var(--paper);
}
.evidence-association {
  color: var(--secondary-ink);
  font-size: var(--font-secondary);
}
.evidence-item {
  margin-top: 22rpx;
}
.evidence-label {
  font-weight: 600;
  margin-bottom: 8rpx;
}
.evidence-source {
  margin-top: 18rpx;
  padding-top: 14rpx;
  border-top: 1rpx solid #e8e1cf;
}
</style>
