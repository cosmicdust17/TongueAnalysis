<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { api, dateText, toastError, confirmAction } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Alert } from "@/types";
const rows = ref<Alert[]>([]),
  error = ref("");
onShow(() => {
  if (requireAuth("ops_admin")) load();
});
async function load() {
  error.value = "";
  try {
    rows.value = (await api<{ items: Alert[] }>("/operations/alerts")).items;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "读取失败";
  }
}
async function resolve(id: string) {
  if (!(await confirmAction("确认已检查该问题，将告警标记为已处理？"))) return;
  try {
    await api("/operations/alerts/" + id + "/resolve", "POST");
    load();
  } catch (e) {
    toastError(e);
  }
}
</script>
<template>
  <view class="page"
    ><view class="title section">告警处理</view
    ><view v-if="error" class="error">{{ error }}</view
    ><view v-for="alert in rows" :key="alert.id" class="panel"
      ><view class="row between"
        ><text class="subtitle">{{ alert.service }}</text
        ><text class="pill" :class="alert.resolved ? '' : 'pending'">{{
          alert.resolved ? "已处理" : "待处理"
        }}</text></view
      ><view class="spaced">{{ alert.message }}</view
      ><view class="muted small">{{ dateText(alert.created_at) }}</view
      ><button
        v-if="!alert.resolved"
        class="outline button-small spaced"
        @tap="resolve(alert.id)"
      >
        标记已处理
      </button></view
    ><view v-if="!rows.length && !error" class="empty">暂无告警</view
    ><button class="outline" @tap="load">刷新</button></view
  >
</template>
