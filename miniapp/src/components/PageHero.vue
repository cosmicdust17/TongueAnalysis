<script setup lang="ts">
defineProps<{ title: string; subtitle?: string; badge?: string }>();
</script>
<template>
  <view class="hero"
    ><image
      class="hero-branch"
      src="/static/branch.png"
      mode="aspectFit"
    /><text v-if="badge" class="badge">{{ badge }}</text
    ><view class="hero-title">{{ title }}</view
    ><view v-if="subtitle" class="muted hero-subtitle">{{
      subtitle
    }}</view></view
  >
</template>
