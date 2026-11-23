<script setup lang="ts">
import { ref } from "vue";
import { onLoad, onShow } from "@dcloudio/uni-app";
import { api, toastError, confirmAction } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Entity, Source } from "@/types";
const id = ref(""),
  name = ref(""),
  kind = ref(0),
  text = ref(""),
  aliases = ref(""),
  sourceIndex = ref(0),
  sources = ref<Source[]>([]),
  busy = ref(false),
  error = ref(""),
  status = ref("draft");
const kinds = ["舌象特征", "症状", "证候"];
onLoad(async (opts) => {
  if (!requireAuth("knowledge_admin")) return;
  id.value = opts?.id || "";
  try {
    sources.value = (
      await api<{ items: Source[] }>("/knowledge/sources")
    ).items;
    if (id.value) {
      const rows = (await api<{ items: Entity[] }>("/knowledge/entities"))
        .items;
      const item = rows.find((x) => x.id === id.value);
      if (!item) throw new Error("实体不存在");
      name.value = item.name;
      kind.value = kinds.indexOf(item.kind);
      text.value = item.text;
      aliases.value = item.aliases.join("，");
      sourceIndex.value = Math.max(
        0,
        sources.value.findIndex((s) => s.id === item.source_id),
      );
      status.value = item.status;
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载失败";
  }
});
onShow(async () => {
  if (!requireAuth("knowledge_admin")) return;
  try {
    const previous = sources.value[sourceIndex.value]?.id;
    sources.value = (
      await api<{ items: Source[] }>("/knowledge/sources")
    ).items;
    if (previous)
      sourceIndex.value = Math.max(
        0,
        sources.value.findIndex((s) => s.id === previous),
      );
  } catch (e) {
    toastError(e);
  }
});
function addSource() {
  uni.navigateTo({ url: "/subpackages/knowledge-admin/source-edit" });
}
async function save(next: "draft" | "pending") {
  if (!sources.value.length) {
    uni.showToast({ title: "请先添加知识来源", icon: "none" });
    return;
  }
  busy.value = true;
  try {
    await api(
      "/knowledge/entities" + (id.value ? "/" + id.value : ""),
      id.value ? "PUT" : "POST",
      {
        name: name.value,
        kind: kinds[kind.value],
        text: text.value,
        source_id: sources.value[sourceIndex.value].id,
        aliases: aliases.value
          .split(/[,，]/)
          .map((x) => x.trim())
          .filter(Boolean),
        status: next,
      },
    );
    uni.showToast({ title: "已保存", icon: "success" });
    uni.navigateBack();
  } catch (e) {
    toastError(e);
  } finally {
    busy.value = false;
  }
}
async function remove() {
  if (!(await confirmAction("删除这个实体？存在关联关系时需先删除关系。")))
    return;
  try {
    await api("/knowledge/entities/" + id.value, "DELETE");
    uni.navigateBack();
  } catch (e) {
    toastError(e);
  }
}
</script>
<template>
  <view class="page"
    ><view v-if="error" class="error">{{ error }}</view
    ><view class="panel"
      ><view class="title">{{ id ? "编辑实体" : "新增知识条目" }}</view
      ><view v-if="status === 'published'" class="notice spaced"
        >修改已发布条目后需要重新审核。</view
      ><text class="label">名称</text
      ><view class="field"
        ><input v-model="name" maxlength="100" placeholder="实体名称" /></view
      ><text class="label">实体类型</text
      ><picker
        :range="kinds"
        :value="kind"
        @change="kind = Number($event.detail.value)"
        ><view class="field pick">{{ kinds[kind] }} ⌄</view></picker
      ><text class="label">知识内容</text
      ><view class="field-area">
        <textarea
          v-model="text"
          maxlength="5000"
          placeholder="填写可引用的知识内容"
        /></view
      ><text class="label">别名（逗号分隔，可选）</text
      ><view class="field"
        ><input
          v-model="aliases"
          maxlength="3000"
          placeholder="例如：疲乏，疲倦" /></view
      ><text class="label">知识来源</text
      ><picker
        v-if="sources.length"
        :range="sources"
        range-key="title"
        :value="sourceIndex"
        @change="sourceIndex = Number($event.detail.value)"
        ><view class="field pick"
          >{{ sources[sourceIndex]?.title }} ⌄</view
        ></picker
      ><view v-else class="notice spaced" @tap="addSource"
        >还没有来源，点击新增来源文档 ›</view
      ><view v-if="sources[sourceIndex]" class="muted small spaced">{{
        sources[sourceIndex].citation
      }}</view
      ><view class="actions spaced"
        ><button
          class="outline"
          :disabled="busy || !!error"
          @tap="save('draft')"
        >
          保存草稿</button
        ><button
          class="primary"
          :disabled="busy || !!error"
          @tap="save('pending')"
        >
          提交审核
        </button></view
      ><button
        v-if="id"
        class="secondary danger spaced"
        :disabled="!!error"
        @tap="remove"
      >
        删除实体
      </button></view
    ></view
  >
</template>
<style scoped>
.pick {
  padding: 22rpx;
}
textarea {
  min-height: 240rpx;
}
</style>
