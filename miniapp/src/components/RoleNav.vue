<script setup lang="ts">
import { computed } from "vue";
import { useAuth } from "@/stores/auth";
import AppIcon from "./AppIcon.vue";
defineProps<{ active: string }>();
const auth = useAuth();
const tabs = computed(() =>
  auth.user?.role === "knowledge_admin"
    ? [
        {
          key: "library",
          label: "知识库",
          icon: "layers",
          url: "/subpackages/knowledge-admin/library",
        },
        {
          key: "graph",
          label: "图谱",
          icon: "graph",
          url: "/subpackages/knowledge-admin/graph",
        },
        { key: "mine", label: "我的", icon: "user", url: "/pages/mine/index" },
      ]
    : auth.user?.role === "ops_admin"
      ? [
          {
            key: "overview",
            label: "运行概览",
            icon: "server",
            url: "/subpackages/ops-admin/overview",
          },
          {
            key: "logs",
            label: "日志",
            icon: "document",
            url: "/subpackages/ops-admin/logs",
          },
          {
            key: "mine",
            label: "我的",
            icon: "user",
            url: "/pages/mine/index",
          },
        ]
      : [
          {
            key: "analysis",
            label: "舌象分析",
            icon: "leaf",
            url: "/pages/analysis/index",
          },
          {
            key: "history",
            label: "分析记录",
            icon: "clock",
            url: "/subpackages/user/history",
          },
          { key: "trends", label: "健康趋势", icon: "trend", url: "/subpackages/user/trends" },
          {
            key: "mine",
            label: "我的",
            icon: "user",
            url: "/pages/mine/index",
          },
        ],
);
function go(url: string) {
  const pages = getCurrentPages();
  if ("/" + pages[pages.length - 1]?.route !== url) uni.reLaunch({ url });
}
</script>
<template>
  <view class="role-nav">
    <view class="role-nav-inner">
      <button v-for="tab in tabs" :key="tab.key" class="nav-item"
        :class="{ selected: active === tab.key }" :aria-current="active === tab.key ? 'page' : undefined"
        @tap="go(tab.url)">
        <view class="nav-icon" aria-hidden="true"><AppIcon :name="tab.icon" :size="38" /></view>
        <text>{{ tab.label }}</text>
      </button>
    </view>
  </view>
</template>
