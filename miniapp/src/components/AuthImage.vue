<script setup lang="ts">
import { ref, watch } from "vue";
import { download } from "@/utils/request";
const props = defineProps<{ fileId: string }>();
const src = ref(""),
  failed = ref(false);
watch(
  () => props.fileId,
  async (value) => {
    src.value = "";
    failed.value = false;
    if (!value) return;
    try {
      const path = await download("/uploads/" + value + "/content");
      if (props.fileId === value) src.value = path;
    } catch {
      failed.value = true;
    }
  },
  { immediate: true },
);
</script>
<template>
  <image v-if="src" :src="src" mode="aspectFill" class="auth-image" /><view
    v-else
    class="image-placeholder"
    >{{ failed ? "图片暂不可用" : "加载图片…" }}</view
  >
</template>
<style scoped>
.auth-image,
.image-placeholder {
  width: 100%;
  height: 100%;
  border-radius: 18rpx;
}
.image-placeholder {
  background: #edf6f1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22rpx;
  color: #718078;
}
</style>
