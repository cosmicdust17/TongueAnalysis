<script setup lang="ts">
import { ref } from "vue";
import { onLoad, onShow, onHide, onUnload } from "@dcloudio/uni-app";
import { api, toastError } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Analysis, Report } from "@/types";
import PageHero from "@/components/PageHero.vue";
import AppIcon from "@/components/AppIcon.vue";
import AnnotatedPhoto from "@/components/AnnotatedPhoto.vue";
import RoleNav from "@/components/RoleNav.vue";
const task = ref<Analysis | null>(null),
  report = ref<Report | null>(null),
  error = ref(""),
  aid = ref(""),
  busy = ref(false);
let timer: ReturnType<typeof setTimeout> | undefined,
  visible = false;
onLoad((opts) => {
  aid.value = opts?.id || "";
});
onShow(() => {
  if (requireAuth("user")) {
    visible = true;
    poll();
  }
});
function stop() {
  visible = false;
  if (timer) clearTimeout(timer);
}
onHide(stop);
onUnload(stop);
async function poll() {
  if (!aid.value) {
    error.value = "缺少分析任务编号";
    return;
  }
  error.value = "";
  try {
    const next = await api<Analysis>("/analyses/" + aid.value);
    task.value = next;
    if (next.status === "completed" && next.report_id) {
      report.value = await api<Report>("/reports/" + next.report_id);
      uni.removeStorageSync("active_analysis");
    } else if (next.status !== "failed" && visible) {
      timer = setTimeout(poll, 1500);
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : "查询失败";
  }
}
async function retry() {
  busy.value = true;
  try {
    await api("/analyses/" + aid.value + "/retry", "POST");
    await poll();
  } catch (e) {
    toastError(e);
  } finally {
    busy.value = false;
  }
}
function openReport() {
  if (report.value)
    uni.navigateTo({ url: "/pages/report/index?id=" + report.value.id });
}
</script>
<template>
  <view class="page with-nav"
    ><PageHero
      :title="
        task?.status === 'completed'
          ? '本次分析已完成'
          : task?.status === 'failed'
            ? '分析暂未完成'
            : '正在整理分析报告'
      "
      :subtitle="
        task?.status === 'completed'
          ? '报告已自动归档'
          : '可离开本页，稍后继续查看'
      " />
    <view v-if="error" class="error"
      >{{ error
      }}<button class="outline spaced" @tap="poll">重新查询</button></view
    >
    <view
      v-if="task && ['queued', 'running'].includes(task.status)"
      class="panel center"
      ><view class="progress-number">{{ task.progress }}%</view
      ><progress :percent="task.progress" activeColor="#09835b" /><view
        class="subtitle spaced"
        >{{ task.status === "queued" ? "等待处理" : "分析与检索处理中" }}</view
      ><view class="muted small"
        >正在读取舌象与症状、检索知识并保存报告</view
      ></view
    >
    <view v-if="task?.status === 'failed'" class="panel"
      ><view class="error">分析暂时无法完成，请稍后重试。</view
      ><button class="primary" :disabled="busy" @tap="retry">
        重新尝试
      </button></view
    >
    <template v-if="report">
      <view class="center success-mark"><AppIcon name="check" :size="112"/></view>
      <AnnotatedPhoto :file-id="report.image_id" :annotations="report.content.annotations" compact/>
      <view class="panel"><view class="spaced">{{report.content.presentation?.brief}}</view><button class="primary spaced" @tap="openReport">查看分析报告 ›</button></view>
    </template
    ><RoleNav active="analysis"
  /></view>
</template>
<style scoped>
.progress-number {
  font-size: 64rpx;
  color: #07845a;
  padding: 25rpx;
}
.success-mark {
  display: flex;
  justify-content: center;
  margin-bottom: 25rpx;
}
</style>
