<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { api, query, dateText } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Log } from "@/types";
import PageHero from "@/components/PageHero.vue";
import RoleNav from "@/components/RoleNav.vue";
const rows = ref<Log[]>([]),
  total = ref(0),
  page = ref(1),
  q = ref(""),
  category = ref(""),
  date = ref(""),
  busy = ref(false),
  error = ref("");
onShow(() => {
  if (requireAuth("ops_admin")) load(true);
});
async function load(reset = false) {
  if (busy.value) return;
  if (reset) page.value = 1;
  busy.value = true;
  error.value = "";
  try {
    const data = await api<{ items: Log[]; total: number }>(
      "/operations/logs" +
        query({
          q: q.value,
          category: category.value,
          date: date.value,
          page: page.value,
        }),
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
function openAlerts() {
  uni.navigateTo({ url: "/subpackages/ops-admin/alerts" });
}
function filter(value: string) {
  category.value = value;
  load(true);
}
function dateChange(value: string) {
  date.value = value;
  load(true);
}
</script>
<template>
  <view class="page with-nav"
    ><PageHero
      title="日志与告警"
      subtitle="查看系统事件与处理结果"
      badge="运维管理员" /><view class="row search"
      ><input
        v-model="q"
        placeholder="搜索日志内容"
        @confirm="load(true)"
      /><text class="link" @tap="load(true)">搜索</text></view
    ><view class="chips section"
      ><view
        v-for="tab in [
          { key: '', text: '全部' },
          { key: 'operation', text: '操作日志' },
          { key: 'exception', text: '服务异常' },
        ]"
        :key="tab.key"
        class="chip"
        :class="{ active: category === tab.key }"
        @tap="filter(tab.key)"
        >{{ tab.text }}</view
      ></view
    ><view class="row between section"
      ><picker
        mode="date"
        :value="date"
        @change="dateChange($event.detail.value)"
        ><view class="field date-picker"
          >{{ date || "选择日期" }} ⌄</view
        ></picker
      ><text v-if="date" class="link" @tap="dateChange('')">清除</text
      ><text class="link" @tap="openAlerts">处理告警 ›</text></view
    ><view v-if="error" class="error">{{ error }}</view
    ><view class="muted small section">共 {{ total }} 条 · 北京时间</view
    ><view v-for="log in rows" :key="log.id" class="panel timeline-row"
      ><view class="time">{{ dateText(log.created_at, true) }}</view
      ><view class="grow"
        ><view class="subtitle">{{ log.action }}</view
        ><view class="muted small">操作人：{{ log.actor_name }}</view></view
      ><text class="pill" :class="log.status === 'failed' ? 'pending' : ''">{{
        log.status === "success" ? "成功" : "失败"
      }}</text></view
    ><view v-if="busy" class="loading">正在读取…</view
    ><view v-if="!rows.length && !busy && !error" class="empty"
      >暂无符合条件的日志</view
    ><button v-if="rows.length < total" class="outline" @tap="load(false)">
      加载更多</button
    ><RoleNav active="logs"
  /></view>
</template>
<style scoped>
.timeline-row {
  display: flex;
  gap: 16rpx;
  align-items: center;
  padding: 23rpx 20rpx;
}
.time {
  font-size: 23rpx;
  width: 130rpx;
  color: #78877e;
}
.date-picker {
  margin: 0;
  padding: 12rpx 18rpx;
}
</style>
