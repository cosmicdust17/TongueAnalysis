<script setup lang="ts">
import { ref } from "vue";
import { onShow, onLoad } from "@dcloudio/uni-app";
import { api, upload, toastError } from "@/utils/request";
import type { Source } from "@/types";
import { requireAuth } from "@/stores/auth";
const id = ref(""),
  title = ref(""),
  citation = ref(""),
  isDemo = ref(false),
  fileId = ref(""),
  fileName = ref(""),
  busy = ref(false);
onShow(() => requireAuth("knowledge_admin"));
onLoad(async (opts) => {
  id.value = opts?.id || "";
  if (!id.value || !requireAuth("knowledge_admin")) return;
  try {
    const s = (await api<{ items: Source[] }>("/knowledge/sources")).items.find(
      (x) => x.id === id.value,
    );
    if (!s) throw new Error("来源不存在");
    title.value = s.title;
    citation.value = s.citation;
    isDemo.value = s.is_demo;
    fileId.value = s.file_id || "";
    fileName.value = s.file_name || "";
  } catch (e) {
    toastError(e);
  }
});
function choose() {
  uni.chooseMessageFile({
    count: 1,
    type: "file",
    extension: ["pdf", "txt"],
    success: async (r) => {
      busy.value = true;
      try {
        const file = r.tempFiles[0];
        const out = await upload(file.path, "document");
        fileId.value = out.id;
        fileName.value = out.name;
        if (!title.value) title.value = out.name;
      } catch (e) {
        toastError(e);
      } finally {
        busy.value = false;
      }
    },
    fail: () => {},
  });
}
function demoChange(event: unknown) {
  isDemo.value = (event as { detail: { value: boolean } }).detail.value;
}
async function save() {
  busy.value = true;
  try {
    await api(
      "/knowledge/sources" + (id.value ? "/" + id.value : ""),
      id.value ? "PUT" : "POST",
      {
        title: title.value,
        citation: citation.value,
        file_id: fileId.value || null,
        is_demo: isDemo.value,
      },
    );
    uni.showToast({ title: "来源已保存", icon: "success" });
    uni.navigateBack();
  } catch (e) {
    toastError(e);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <view class="page"
    ><view class="panel"
      ><view class="title">{{ id ? "编辑知识来源" : "新增知识来源" }}</view
      ><view class="muted small spaced"
        >保存原始文档与出处，实体和关系需另行整理维护。</view
      ><text class="label">来源标题</text
      ><view class="field"
        ><input
          v-model="title"
          maxlength="200"
          placeholder="文献、教材或资料名称" /></view
      ><text class="label">可追溯出处</text
      ><view class="field-area">
        <textarea
          v-model="citation"
          maxlength="3000"
          placeholder="作者、年份、章节或页码、URL等实际来源信息"
        /></view
      ><text class="label">原始文档（可选）</text
      ><button class="outline spaced" :disabled="busy" @tap="choose">
        {{ fileName || "从微信会话选择 PDF / TXT" }}</button
      ><view class="form-hint"
        >支持UTF-8 TXT与PDF，最大10MB。仅保存原文，不自动抽取图谱。</view
      ><view class="row between spaced"
        ><text>标记为联调示例资料</text
        ><switch :checked="isDemo" color="#087f56" @change="demoChange" /></view
      ><button
        class="primary spaced"
        :loading="busy"
        :disabled="busy"
        @tap="save"
      >
        保存来源
      </button></view
    ></view
  >
</template>
