<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { api, query, dateText } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Report } from "@/types";
import AuthImage from "@/components/AuthImage.vue";
import AppIcon from "@/components/AppIcon.vue";
import RoleNav from "@/components/RoleNav.vue";
const rows = ref<Report[]>([]),
  total = ref(0),
  q = ref(""),
  searchTerm = ref(""),
  page = ref(1),
  busy = ref(false),
  error = ref("");
onShow(() => {
  if (requireAuth("user")) load(true);
});
async function load(reset = false) {
  if (busy.value) return;
  const term = reset ? q.value.trim() : searchTerm.value;
  const requestedPage = reset ? 1 : page.value;
  busy.value = true;
  error.value = "";
  try {
    const data = await api<{ items: Report[]; total: number }>(
      "/reports" + query({ q: term, page: requestedPage, page_size: 20 }),
    );
    rows.value = reset ? data.items : [...rows.value, ...data.items];
    total.value = data.total;
    searchTerm.value = term;
    page.value = requestedPage + 1;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "读取失败";
  } finally {
    busy.value = false;
  }
}
function open(id: string) {
  uni.navigateTo({ url: "/pages/report/index?id=" + id });
}
</script>
<template>
  <view class="page with-nav history-page">
    <view class="row search history-search">
      <AppIcon name="search" :size="32" />
      <input v-model="q" :maxlength="100" aria-label="搜索分析报告或症状"
        placeholder="搜索分析报告或症状" confirm-type="search" @confirm="load(true)" />
      <button class="search-button" :disabled="busy" @tap="load(true)">搜索</button>
    </view>
    <view class="row between history-heading">
      <view class="page-title">{{ searchTerm ? "搜索结果" : "全部记录" }}</view>
      <text class="record-count">共 {{ total }} 份</text>
    </view>

    <view v-if="error" class="error">
      {{ error }} <text class="link" @tap="load(true)">重试</text>
    </view>
    <view v-for="r in rows" :key="r.id" class="panel history-card" hover-class="history-pressed" @tap="open(r.id)">
      <view class="thumb"><AuthImage :file-id="r.image_id" /></view>
      <view class="grow record-content">
        <view class="record-date">{{ dateText(r.created_at) }}</view>
        <view class="history-summary">{{ r.content.presentation?.symptoms_text }}</view>
        <view class="link open-report">查看报告 <text aria-hidden="true">›</text></view>
      </view>
    </view>
    <view v-if="!rows.length && !busy && !error" class="empty">
      {{ searchTerm ? "没有找到匹配的报告。" : "还没有分析记录，完成分析后会自动保存。" }}
    </view>
    <view v-if="busy" class="loading">正在加载…</view>
    <button v-if="rows.length < total" class="outline" :disabled="busy" @tap="load(false)">加载更多</button>
    <RoleNav active="history" />
  </view>
</template>

<style scoped>
.history-search { height: 84rpx; margin: 0; padding: 0 12rpx 0 18rpx; gap: 12rpx; }
.history-search input { font-size: var(--font-body); }
.search-button { padding: 0 12rpx; min-height: 72rpx; color: var(--primary); background: transparent; font-size: 26rpx; font-weight: 600; }
.search-button::after { border: 0; }
.history-heading { margin: 32rpx 0 16rpx; }
.record-count { font-size: var(--font-caption); color: var(--secondary-ink); }
.history-card { display: flex; align-items: center; gap: 20rpx; padding: 20rpx; margin-bottom: 14rpx; border: 0; border-radius: 20rpx; }
.history-card.history-pressed { background: #edf2ec; }
.thumb { width: 144rpx; height: 144rpx; border-radius: 16rpx; flex-shrink: 0; overflow: hidden; }
.record-date { font-size: var(--font-caption); color: var(--secondary-ink); font-variant-numeric: tabular-nums; }
.history-summary { margin: 6rpx 0 8rpx; font-size: var(--font-secondary); line-height: 1.55; overflow-wrap: anywhere; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.open-report { font-size: var(--font-secondary); font-weight: 500; }
</style>
