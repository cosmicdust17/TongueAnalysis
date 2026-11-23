<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 40 });
</script>
<template>
  <image
    v-if="name"
    :src="'/static/icons/' + name + '.png'"
    :style="{ width: size + 'rpx', height: size + 'rpx' }"
    mode="aspectFit"
    class="app-icon"
  />
</template>
