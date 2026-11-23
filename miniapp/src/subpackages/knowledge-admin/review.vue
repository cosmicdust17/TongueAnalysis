<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { api, toastError, confirmAction } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Entity, Relation, Source } from "@/types";
const nodes = ref<Entity[]>([]),
  edges = ref<Relation[]>([]),
  names = ref<Record<string, string>>({}),
  sources = ref<Record<string, Source>>({}),
  busy = ref(false),
  error = ref("");
onShow(() => {
  if (requireAuth("knowledge_admin")) load();
});
async function load() {
  error.value = "";
  try {
    const [a, b, c] = await Promise.all([
      api<{ items: Entity[] }>("/knowledge/entities"),
      api<{ items: Relation[] }>("/knowledge/relations"),
      api<{ items: Source[] }>("/knowledge/sources"),
    ]);
    nodes.value = a.items.filter((x) => x.status === "pending");
    edges.value = b.items.filter((x) => x.status === "pending");
    names.value = Object.fromEntries(a.items.map((x) => [x.id, x.name]));
    sources.value = Object.fromEntries(c.items.map((x) => [x.id, x]));
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载失败";
  }
}
async function publish(type: "entities" | "relations", id: string) {
  if (!(await confirmAction("确认依据和来源无误，发布这条知识？"))) return;
  busy.value = true;
  try {
    await api("/knowledge/" + type + "/" + id + "/publish", "POST");
    load();
  } catch (e) {
    toastError(e);
  } finally {
    busy.value = false;
  }
}
function edit(type: string, id: string) {
  uni.navigateTo({
    url:
      "/subpackages/knowledge-admin/" +
      (type === "entities" ? "entity-edit" : "relation-edit") +
      "?id=" +
      id,
  });
}
</script>
<template>
  <view class="page"
    ><view class="title section">审核与发布</view
    ><view class="muted small section"
      >仅已发布知识进入分析检索。修改已发布内容后需重新审核。</view
    ><view v-if="error" class="error">{{ error }}</view
    ><view v-for="n in nodes" :key="n.id" class="panel"
      ><view class="row between"
        ><text class="subtitle">{{ n.name }}</text
        ><text class="pill pending">实体 · 待审核</text></view
      ><view class="spaced">{{ n.text }}</view
      ><view class="muted small spaced"
        >来源：{{ sources[n.source_id]?.title }} ·
        {{ sources[n.source_id]?.citation }}</view
      ><view class="actions spaced"
        ><button class="outline button-small" @tap="edit('entities', n.id)">
          编辑</button
        ><button
          class="primary button-small"
          :disabled="busy"
          @tap="publish('entities', n.id)"
        >
          审核发布
        </button></view
      ></view
    ><view v-for="r in edges" :key="r.id" class="panel"
      ><view class="subtitle"
        >{{ names[r.source] }} — {{ r.kind }} → {{ names[r.target] }}</view
      ><text class="pill pending">关系 · 待审核</text
      ><view class="muted small spaced"
        >来源：{{ sources[r.source_id]?.title }} ·
        {{ sources[r.source_id]?.citation }}</view
      ><view class="actions spaced"
        ><button class="outline button-small" @tap="edit('relations', r.id)">
          编辑</button
        ><button
          class="primary button-small"
          :disabled="busy"
          @tap="publish('relations', r.id)"
        >
          审核发布
        </button></view
      ></view
    ><view v-if="!nodes.length && !edges.length && !error" class="empty"
      >暂无待审核知识</view
    ></view
  >
</template>
