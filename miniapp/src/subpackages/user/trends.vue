<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { requireAuth } from "@/stores/auth";
import RoleNav from "@/components/RoleNav.vue";
import HealthTrends from "./components/HealthTrends.vue";

onShow(() => requireAuth("user"));
</script>

<template>
  <view class="page olive-sheet with-nav">
    <HealthTrends />
    <RoleNav active="trends" />
  </view>
</template>
