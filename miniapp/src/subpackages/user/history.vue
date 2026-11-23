<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { api, query, dateText } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Report } from "@/types";
import AuthImage from "@/components/AuthImage.vue";
import AppIcon from "@/components/AppIcon.vue";
const rows = ref<Report[]>([]),
  total = ref(0),
  q = ref(""),
  page = ref(1),
  busy = ref(false),
  error = ref("");
onShow(() => {
  if (requireAuth("user")) load(true);
});
async function load(reset = false) {
  if (busy.value) return;
  if (reset) page.value = 1;
  busy.value = true;
  error.value = "";
  try {
    const data = await api<{ items: Report[]; total: number }>(
      "/reports" + query({ q: q.value, page: page.value, page_size: 20 }),
    );
    rows.value = reset ? data.items : [...rows.value, ...data.items];
    total.value = data.total;
    page.value++;
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
  <view class="page"
    ><view class="row search"
      ><AppIcon name="search" :size="36" /><input
        v-model="q"
        placeholder="搜索分析报告或症状"
        confirm-type="search"
        @confirm="load(true)"
      /><text class="link" @tap="load(true)">搜索</text></view
    ><view class="row between section"
      ><view class="title">全部记录</view
      ><text class="muted">共 {{ total }} 份</text></view
    ><view v-if="error" class="error"
      >{{ error }}<text class="link" @tap="load(true)"> 重试</text></view
    ><view
      v-for="r in rows"
      :key="r.id"
      class="panel history-card"
      @tap="open(r.id)"
      ><view class="thumb"><AuthImage :file-id="r.image_id" /></view
      ><view class="grow"
        ><view class="row between"
          ><text>{{ dateText(r.created_at, true) }}</text
          ><text class="pill">已归档</text></view
        ><view class="history-summary">{{ r.content.presentation.symptoms_text }}</view
        ><view class="row between"
          ><text class="link">查看报告 ›</text
          ></view
        ></view
      ></view
    ><view v-if="!rows.length && !busy && !error" class="empty"
      >还没有分析记录，完成分析后会自动保存。</view
    ><view v-if="busy" class="loading">正在加载…</view
    ><button
      v-if="rows.length < total"
      class="outline"
      :disabled="busy"
      @tap="load(false)"
    >
      加载更多</button
    ><view class="footer-mark row"
      ><AppIcon name="layers" :size="38" /><text
        >报告生成后自动保存于此</text
      ></view
    ></view
  >
</template>
<style scoped>
.history-card {
  display: flex;
  gap: 24rpx;
  padding: 22rpx;
}
.thumb {
  width: 150rpx;
  height: 170rpx;
  flex-shrink: 0;
}
.history-summary {
  margin: 16rpx 0;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.footer-mark {
  justify-content: center;
}
</style>
