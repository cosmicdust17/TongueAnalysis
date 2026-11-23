<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { api } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Entity, Relation } from "@/types";
const rows = ref<Relation[]>([]),
  names = ref<Record<string, string>>({}),
  error = ref("");
onShow(async () => {
  if (!requireAuth("knowledge_admin")) return;
  try {
    const [r, n] = await Promise.all([
      api<{ items: Relation[] }>("/knowledge/relations"),
      api<{ items: Entity[] }>("/knowledge/entities"),
    ]);
    rows.value = r.items;
    names.value = Object.fromEntries(n.items.map((x) => [x.id, x.name]));
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载失败";
  }
});
function edit(id = "") {
  uni.navigateTo({
    url: "/subpackages/knowledge-admin/relation-edit" + (id ? "?id=" + id : ""),
  });
}
const label = (s: string) =>
  ({ draft: "草稿", pending: "待审核", published: "已发布" })[s] || s;
</script>
<template>
  <view class="page"
    ><view class="row between section"
      ><view class="title">关系管理</view
      ><button class="primary button-small" @tap="edit()">
        新增关系
      </button></view
    ><view v-if="error" class="error">{{ error }}</view
    ><view v-for="r in rows" :key="r.id" class="panel" @tap="edit(r.id)"
      ><view class="row between"
        ><text class="subtitle"
          >{{ names[r.source] }} → {{ names[r.target] }}</text
        ><text class="chevron">›</text></view
      ><view class="row between spaced"
        ><text class="tag">{{ r.kind }}</text
        ><text class="pill" :class="r.status">{{ label(r.status) }}</text></view
      ></view
    ><view v-if="!rows.length && !error" class="empty"
      >暂无关系，先维护实体，再关联实体与来源。</view
    ></view
  >
</template>
