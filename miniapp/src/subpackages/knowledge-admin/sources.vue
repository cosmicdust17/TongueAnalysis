<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import {
  api,
  download,
  query,
  toastError,
  confirmAction,
} from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Source } from "@/types";
const rows = ref<Source[]>([]),
  q = ref(""),
  error = ref(""),
  preview = ref("");
onShow(() => {
  if (requireAuth("knowledge_admin")) load();
});
async function load() {
  error.value = "";
  try {
    rows.value = (
      await api<{ items: Source[] }>(
        "/knowledge/sources" + query({ q: q.value }),
      )
    ).items;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载失败";
  }
}
function edit(id: string) {
  uni.navigateTo({ url: "/subpackages/knowledge-admin/source-edit?id=" + id });
}
function add() {
  uni.navigateTo({ url: "/subpackages/knowledge-admin/source-edit" });
}
async function open(s: Source) {
  if (!s.file_id) return;
  try {
    if (s.file_type === "text/plain; charset=utf-8") {
      preview.value = await api<string>("/uploads/" + s.file_id + "/content");
      return;
    }
    const path = await download("/uploads/" + s.file_id + "/content");
    await new Promise<void>((resolve, reject) =>
      uni.openDocument({
        filePath: path,
        fileType: "pdf",
        showMenu: true,
        success: () => resolve(),
        fail: reject,
      }),
    );
  } catch (e) {
    toastError(e);
  }
}
async function remove(id: string) {
  if (!(await confirmAction("删除该来源？仍被实体或关系引用时不能删除。")))
    return;
  try {
    await api("/knowledge/sources/" + id, "DELETE");
    load();
  } catch (e) {
    toastError(e);
  }
}
</script>
<template>
  <view class="page"
    ><view class="row between section"
      ><view class="title">知识来源与文档</view
      ><button class="primary button-small" @tap="add">新增来源</button></view
    ><view class="row search"
      ><input
        v-model="q"
        placeholder="搜索来源标题或出处"
        @confirm="load"
      /><text class="link" @tap="load">搜索</text></view
    ><view v-if="error" class="error">{{ error }}</view
    ><view v-for="s in rows" :key="s.id" class="panel"
      ><view class="row between"
        ><text class="subtitle">{{ s.title }}</text
        ><text v-if="s.is_demo" class="pill demo">示例资料</text></view
      ><view class="muted small spaced">{{ s.citation }}</view
      ><view class="actions spaced"
        ><button class="secondary button-small" @tap="edit(s.id)">
          编辑来源</button
        ><button v-if="s.file_id" class="outline button-small" @tap="open(s)">
          查看原始文档</button
        ><button class="secondary button-small danger" @tap="remove(s.id)">
          删除来源
        </button></view
      ></view
    ><view v-if="!rows.length && !error" class="empty"
      >暂无来源文档，先新增来源再维护知识条目。</view
    ><view v-if="preview" class="overlay" @tap="preview = ''"
      ><view class="sheet" @tap.stop
        ><view class="row between"
          ><text class="title">来源原文</text
          ><text class="chevron" @tap="preview = ''">×</text></view
        ><scroll-view scroll-y class="sheet-scroll"
          ><text selectable class="raw-text">{{ preview }}</text></scroll-view
        ></view
      ></view
    ></view
  >
</template>
<style scoped>
.raw-text {
  white-space: pre-wrap;
  font-size: 26rpx;
  display: block;
  padding: 20rpx 0;
}
</style>
