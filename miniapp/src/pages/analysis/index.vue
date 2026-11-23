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
  if (busy.value) return;
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
  <view class="page with-nav analysis-home">
    <PageHero class="home-hero" title="从舌象，了解身体" subtitle="记录舌象与症状，获取综合分析" />
    <button v-if="active" class="resume row between" hover-class="resume-pressed" @tap="resume">
      <text>上次分析</text>
      <view class="resume-action">
        <text>继续查看</text><text class="resume-arrow" aria-hidden="true">›</text>
      </view>
    </button>

    <view class="panel">
      <view class="card-title form-heading">上传舌象</view>
      <view class="upload-zone" @tap="choose(['camera', 'album'])">
        <image v-if="image" :src="image" mode="aspectFit" class="preview" aria-label="已选舌象" />
        <template v-else>
          <AppIcon name="camera" :size="52" />
          <view class="upload-title">拍照或选择照片</view>
          <view class="tiny helper">使用自然光，保持舌面清晰</view>
        </template>
      </view>
      <view class="actions photo-actions">
        <button class="secondary" @tap="choose(['camera'])">
          <AppIcon name="camera" :size="32" />{{ image ? "重新拍摄" : "拍照" }}
        </button>
        <button class="secondary" @tap="choose(['album'])">
          <AppIcon name="image" :size="32" />{{ image ? "重新选择" : "相册" }}
        </button>
      </view>
    </view>

    <view class="panel">
      <view class="card-title form-heading">描述症状</view>
      <view class="chips">
        <button v-for="tag in tags" :key="tag" class="chip symptom-chip"
          :class="{ active: selected.includes(tag) }" :aria-pressed="selected.includes(tag)" @tap="toggle(tag)">
          <AppIcon v-if="selected.includes(tag)" name="check" :size="22" />{{ tag }}
        </button>
      </view>
      <view class="field-area symptom-field">
        <textarea v-model="symptoms" :maxlength="200" aria-label="近期症状"
          placeholder="例如最近容易疲倦、夜里睡得浅" placeholder-style="color:#576B60" />
        <view class="counter tiny" :class="{ danger: description.length > 200 }">{{ description.length }}/200</view>
        <view v-if="description.length > 200" class="tiny danger">症状标签与文字合计最多 200 字</view>
      </view>
      <picker :range="durations" :value="duration" @change="duration = Number($event.detail.value)">
        <view class="field select-field duration">
          <text class="duration-label">持续时间</text>
          <view class="select-value">{{ durations[duration] }}<view class="disclosure-icon" aria-hidden="true" /></view>
        </view>
      </picker>
    </view>

    <button class="primary" :loading="busy" :disabled="busy" @tap="submit">
      {{ busy ? "正在提交" : "开始分析" }}
    </button>
    <view class="center tiny helper save-note">报告生成后自动保存</view>
    <RoleNav active="analysis" />
  </view>
</template>

<style scoped>
.analysis-home { padding-top: 8rpx; }
.home-hero :deep(.hero-title) { font-size: 44rpx; }
.home-hero :deep(.hero-branch) { width: 148rpx; height: 162rpx; }
.form-heading { margin-bottom: 20rpx; }
.resume {
  width: 100%;
  min-height: 80rpx;
  margin: 0 0 16rpx;
  padding: 14rpx 22rpx;
  border: 0;
  border-radius: 18rpx;
  background: #f7f1dd;
  color: #655635;
  font-size: var(--font-secondary);
  text-align: left;
}
.resume::after { border: 0; }
.resume.resume-pressed { background: #efe6ca; }
.resume-action { display: flex; align-items: center; gap: 10rpx; font-weight: 600; }
.resume-arrow { font-size: 34rpx; line-height: 1; }
.upload-zone {
  height: 260rpx;
  border: 1rpx dashed #9ab4a3;
  border-radius: 16rpx;
  background: #f3f8f4;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.preview { height: 100%; width: 100%; }
.upload-title { margin-top: 10rpx; }
.helper, .counter { color: var(--secondary-ink); }
.photo-actions { margin-top: 12rpx; }
.photo-actions .secondary { background: #eef3ee; }
.photo-actions button { min-height: 76rpx; border-radius: 16rpx; font-size: var(--font-secondary); }
.symptom-chip { display: flex; align-items: center; gap: 6rpx; min-height: 60rpx; margin: 0; background: var(--soft); color: var(--primary); font-size: 24rpx; }
.symptom-chip.active { background: var(--primary); color: #fff; }
.symptom-chip.active .app-icon { filter: brightness(0) invert(1); }
.symptom-field { margin-top: 20rpx; padding: 0 20rpx 12rpx; }
.symptom-field textarea { height: 228rpx; font-size: var(--font-body); line-height: 1.65; }
.counter { text-align: right; }
.counter.danger { color: #a94237; }
.duration { margin-top: 20rpx; }
.duration-label { font-weight: 600; }
.save-note { margin-top: 14rpx; }
</style>
