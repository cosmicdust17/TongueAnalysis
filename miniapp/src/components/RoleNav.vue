<script setup lang="ts">
import { computed } from "vue";
import { useAuth } from "@/stores/auth";
import AppIcon from "./AppIcon.vue";
const props = defineProps<{ active: string }>();
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
            key: "mine",
            label: "我的",
            icon: "user",
            url: "/pages/mine/index",
          },
        ],
);
function go(url: string, key: string) {
  if (key !== props.active) uni.reLaunch({ url });
}
</script>
<template>
  <view class="role-nav"
    ><view
      v-for="tab in tabs"
      :key="tab.key"
      class="nav-item"
      :class="{ selected: active === tab.key }"
      @tap="go(tab.url, tab.key)"
      ><AppIcon :name="tab.icon" :size="42" /><text>{{ tab.label }}</text
      ><view class="nav-line" /></view
  ></view>
</template>
