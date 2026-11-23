<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { api, dateText } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Overview } from "@/types";
import PageHero from "@/components/PageHero.vue";
import AppIcon from "@/components/AppIcon.vue";
import RoleNav from "@/components/RoleNav.vue";
const overview = ref<Overview | null>(null),
  error = ref(""),
  busy = ref(false);
onShow(() => {
  if (requireAuth("ops_admin")) load();
});
async function load() {
  error.value = "";
  busy.value = true;
  try {
    overview.value = await api<Overview>("/operations/overview");
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载失败";
  } finally {
    busy.value = false;
  }
}
function go(path: string) {
  uni.navigateTo({ url: "/subpackages/ops-admin/" + path });
}
</script>
<template>
  <view class="page with-nav"
    ><PageHero
      title="运行概览"
      :subtitle="
        overview
          ? '最近更新 ' + dateText(overview.updated_at)
          : '查看系统服务与运行状态'
      "
      badge="运维管理员" /><view v-if="error" class="error"
      >{{ error }}<text class="link" @tap="load"> 重试</text></view
    ><view v-if="busy" class="loading">正在检查服务…</view
    ><template v-if="overview"
      ><view class="panel row status-banner"
        ><AppIcon name="check" :size="70" /><view class="grow"
          ><view class="title">{{
            overview.status === "degraded"
              ? "部分服务需要检查"
              : overview.status === "mock"
                ? "系统处于模拟联调模式"
                : "系统检查通过"
          }}</view
          ><view class="muted small">{{
            overview.status === "mock"
              ? "业务功能可用，真实模型尚未接入"
              : "状态来自当前连接检查"
          }}</view></view
        ></view
      ><view class="metric-grid"
        ><view class="metric" @tap="go('services')"
          ><view class="row"
            ><AppIcon name="image" :size="34" /><text>分析服务</text></view
          ><view class="metric-value">{{
            overview.services.find((s) => s.key === "model")?.status === "mock"
              ? "模拟"
              : overview.services.find((s) => s.key === "model")?.status ===
                  "online"
                ? "在线"
                : "异常"
          }}</view></view
        ><view class="metric"
          ><view>已生成报告</view
          ><view class="metric-value">{{ overview.report_count }}</view></view
        ><view class="metric"
          ><view>今日分析</view
          ><view class="metric-value">{{ overview.today_analyses }}</view></view
        ><view class="metric" @tap="go('alerts')"
          ><view>待处理告警 ›</view
          ><view class="metric-value">{{ overview.pending_alerts }}</view></view
        ></view
      ><view class="panel"
        ><view class="row between"
          ><text class="title">服务监控</text
          ><text class="link" @tap="go('services')">查看全部 ›</text></view
        ><view
          v-for="s in overview.services.slice(1, 4)"
          :key="s.key"
          class="menu row between"
          ><text>{{ s.name }}</text
          ><text
            class="pill"
            :class="
              s.status === 'online'
                ? ''
                : s.status === 'mock'
                  ? 'demo'
                  : 'pending'
            "
            >{{
              s.status === "online"
                ? "运行中"
                : s.status === "mock"
                  ? "模拟模式"
                  : "异常"
            }}</text
          ></view
        ></view
      ><view class="panel row" @tap="go('users')"
        ><view class="icon-box"><AppIcon name="user" /></view
        ><view class="grow"
          ><view class="title">用户管理</view
          ><view class="muted small">查看账号与使用状态</view></view
        ><text class="chevron">›</text></view
      ><view class="panel"
        ><view class="title section">最近操作</view
        ><view v-for="log in overview.recent_logs" :key="log.id" class="menu"
          ><view class="grow"
            ><view>{{ log.action }}</view
            ><view class="muted small">{{
              dateText(log.created_at, true)
            }}</view></view
          ><text
            class="pill"
            :class="log.status === 'failed' ? 'pending' : ''"
            >{{ log.status === "success" ? "成功" : "失败" }}</text
          ></view
        ><view v-if="!overview.recent_logs.length" class="muted"
          >暂无操作记录</view
        ></view
      ></template
    ><button class="outline" :disabled="busy" @tap="load">刷新运行状态</button
    ><RoleNav active="overview"
  /></view>
</template>
<style scoped>
.status-banner {
  background: #e4f5eb;
  padding: 30rpx 24rpx;
}
</style>
