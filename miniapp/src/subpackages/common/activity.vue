<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { requireAuth } from "@/stores/auth";
import { api, dateText } from "@/utils/request";
import type { Log } from "@/types";
const logs = ref<Log[]>([]),
  error = ref("");
onShow(async () => {
  if (!requireAuth()) return;
  try {
    logs.value = (await api<{ items: Log[] }>("/users/me/logs")).items;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载失败";
  }
});
</script>
<template>
  <view class="page"
    ><view class="title section">我的操作记录</view
    ><view v-if="error" class="error">{{ error }}</view
    ><view v-for="log in logs" :key="log.id" class="panel"
      ><view class="row between"
        ><text class="subtitle">{{ log.action }}</text
        ><text class="pill">{{
          log.status === "success" ? "成功" : log.status
        }}</text></view
      ><view class="muted small">{{ dateText(log.created_at) }}</view></view
    ><view v-if="!logs.length && !error" class="empty">暂无操作记录</view
    ><view class="muted small center">显示最近100条本人的操作记录</view></view
  >
</template>
