<script setup lang="ts">
import { ref, computed } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { api, upload, toastError } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Analysis } from "@/types";
import PageHero from "@/components/PageHero.vue";
import AppIcon from "@/components/AppIcon.vue";
import RoleNav from "@/components/RoleNav.vue";
const image = ref(""),
  symptoms = ref(""),
  selected = ref<string[]>([]),
  duration = ref(1),
  busy = ref(false),
  active = ref("");
const tags = ["口干", "乏力", "睡眠不佳"],
  durations = ["近三天", "近一周", "近一个月", "一个月以上"];
const description = computed(() =>
  [...selected.value, symptoms.value].filter(value => value.trim()).join("，"),
);
onShow(() => {
  if (requireAuth("user"))
    active.value = uni.getStorageSync("active_analysis") || "";
});
function toggle(tag: string) {
  selected.value = selected.value.includes(tag)
    ? selected.value.filter((x) => x !== tag)
    : [...selected.value, tag];
}
function choose(sourceType: ("camera" | "album")[]) {
  uni.chooseImage({
    count: 1,
    sizeType: ["compressed"],
    sourceType,
    success: (r) => {
      image.value = r.tempFilePaths[0];
    },
    fail: () => {},
  });
}
function resume() {
  uni.navigateTo({ url: "/pages/analysis/result?id=" + active.value });
}
async function submit() {
  if (!image.value || !description.value) {
    uni.showToast({ title: "请上传舌象并描述症状", icon: "none" });
    return;
  }
  if (description.value.length > 200) {
    uni.showToast({ title: "症状描述合计不能超过200字", icon: "none" });
    return;
  }
  busy.value = true;
  try {
    const file = await upload(image.value);
    const task = await api<Analysis>("/analyses", "POST", {
      image_id: file.id,
      symptoms: description.value,
      duration: durations[duration.value],
    });
    uni.setStorageSync("active_analysis", task.id);
    active.value = task.id;
    uni.navigateTo({ url: "/pages/analysis/result?id=" + task.id });
  } catch (e) {
    toastError(e);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <view class="page with-nav"
    ><PageHero
      title="从舌象，了解身体"
      subtitle="记录舌象与症状，获取综合分析" />
    <view v-if="active" class="notice row between"
      ><text>有一条分析记录可继续查看</text
      ><text class="link" @tap="resume">查看 ›</text></view
    >
    <view class="panel"
      ><view class="row section"
        ><view class="icon-box"><AppIcon name="camera" /></view
        ><text class="title">上传舌象</text></view
      ><view class="upload-zone" @tap="choose(['camera', 'album'])"
        ><image
          v-if="image"
          :src="image"
          mode="aspectFill"
          class="preview"
        /><template v-else
          ><AppIcon name="camera" :size="86" /><view class="subtitle spaced"
            >拍照或选择照片</view
          ><view class="muted small">自然光拍摄，舌面清晰</view></template
        ></view
      ><view class="actions spaced"
        ><button class="secondary" @tap="choose(['camera'])">
          <AppIcon name="camera" :size="34" />拍照</button
        ><button class="secondary" @tap="choose(['album'])">
          <AppIcon name="image" :size="34" />相册
        </button></view
      ></view
    >
    <view class="panel"
      ><view class="row section"
        ><view class="icon-box"><AppIcon name="document" /></view
        ><text class="title">描述症状</text></view
      ><view class="chips"
        ><view
          v-for="tag in tags"
          :key="tag"
          class="chip"
          :class="{ active: selected.includes(tag) }"
          @tap="toggle(tag)"
          >{{ selected.includes(tag) ? "✓ " : "" }}{{ tag }}</view
        ></view
      ><view class="field-area spaced">
        <textarea
          v-model="symptoms"
          maxlength="200"
          placeholder="描述近期身体感受，例如容易疲倦、睡眠较浅"
        /><view class="muted small counter"
          >{{ description.length }}/200</view
        ></view
      ><view class="row between spaced"
        ><view class="row"
          ><AppIcon name="clock" :size="34" /><text class="subtitle"
            >持续时间</text
          ></view
        ><picker
          :range="durations"
          :value="duration"
          @change="duration = Number($event.detail.value)"
          ><view class="picker-value">{{ durations[duration] }}⌄</view></picker
        ></view
      ><button
        class="primary spaced"
        :loading="busy"
        :disabled="busy"
        @tap="submit"
      >
        {{ busy ? "正在提交" : "开始分析" }} ›</button
      ><view class="center muted small spaced">报告生成后自动保存</view></view
    ><RoleNav active="analysis"
  /></view>
</template>
<style scoped>
.upload-zone {
  height: 300rpx;
  border: 2rpx dashed #a1d1bb;
  border-radius: 18rpx;
  background: #f3fbf7;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.preview {
  height: 100%;
  width: 100%;
}
.counter {
  text-align: right;
  padding-bottom: 12rpx;
}
.picker-value {
  padding: 8rpx 25rpx;
  border: 1rpx solid #d9e5dc;
  border-radius: 14rpx;
  background: white;
  min-width: 240rpx;
}
.section {
  margin-top: 0;
}
</style>
