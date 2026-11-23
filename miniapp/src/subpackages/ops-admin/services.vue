<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { api } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Overview } from "@/types";
const data = ref<Overview | null>(null),
  config = ref<Record<string, unknown>>({}),
  busy = ref(false),
  error = ref("");
onShow(() => {
  if (requireAuth("ops_admin")) load();
});
async function load() {
  busy.value = true;
  error.value = "";
  try {
    const [a, b] = await Promise.all([
      api<Overview>("/operations/overview"),
      api<Record<string, unknown>>("/operations/configuration"),
    ]);
    data.value = a;
    config.value = b;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "检查失败";
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <view class="page"
    ><view class="title section">服务监控</view
    ><view v-if="error" class="error">{{ error }}</view
    ><view v-for="s in data?.services || []" :key="s.key" class="panel"
      ><view class="row between"
        ><text class="subtitle">{{ s.name }}</text
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
                : "连接异常"
          }}</text
        ></view
      ><view class="muted small spaced">{{ s.message }}</view></view
    ><view class="panel"
      ><view class="subtitle">当前配置</view
      ><view class="spaced">模型方式：{{ config.model_provider }}</view
      ><view>模型超时：{{ config.model_timeout_seconds }} 秒</view
      ><view>图谱方式：{{ config.graph_provider }}</view
      ><view
        >微信登录：{{ config.wechat_configured ? "已配置" : "待配置" }}</view
      ><view class="muted small spaced"
        >连接与密钥配置由服务端环境文件维护，修改后重启生效。</view
      ></view
    ><button class="primary" :disabled="busy" :loading="busy" @tap="load">
      重新检查
    </button></view
  >
</template>
