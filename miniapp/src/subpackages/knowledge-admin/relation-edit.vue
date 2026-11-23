<script setup lang="ts">
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import { api, toastError, confirmAction } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Entity, Relation, Source } from "@/types";
const id = ref(""),
  entities = ref<Entity[]>([]),
  sources = ref<Source[]>([]),
  from = ref(0),
  to = ref(0),
  source = ref(0),
  kind = ref(0),
  busy = ref(false),
  error = ref(""),
  kinds = ["相关", "伴随", "支持"];
onLoad(async (opts) => {
  if (!requireAuth("knowledge_admin")) return;
  id.value = opts?.id || "";
  try {
    const [a, b] = await Promise.all([
      api<{ items: Entity[] }>("/knowledge/entities"),
      api<{ items: Source[] }>("/knowledge/sources"),
    ]);
    entities.value = a.items;
    sources.value = b.items;
    if (id.value) {
      const r = (
        await api<{ items: Relation[] }>("/knowledge/relations")
      ).items.find((x) => x.id === id.value);
      if (!r) throw new Error("关系不存在");
      from.value = entities.value.findIndex((x) => x.id === r.source);
      to.value = entities.value.findIndex((x) => x.id === r.target);
      source.value = sources.value.findIndex((x) => x.id === r.source_id);
      kind.value = kinds.indexOf(r.kind);
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载失败";
  }
});
async function save(status: "draft" | "pending") {
  if (
    !entities.value[from.value] ||
    !entities.value[to.value] ||
    !sources.value[source.value]
  ) {
    uni.showToast({ title: "请先维护实体和来源", icon: "none" });
    return;
  }
  busy.value = true;
  try {
    await api(
      "/knowledge/relations" + (id.value ? "/" + id.value : ""),
      id.value ? "PUT" : "POST",
      {
        source: entities.value[from.value].id,
        target: entities.value[to.value].id,
        kind: kinds[kind.value],
        source_id: sources.value[source.value].id,
        status,
      },
    );
    uni.navigateBack();
  } catch (e) {
    toastError(e);
  } finally {
    busy.value = false;
  }
}
async function remove() {
  if (!(await confirmAction("删除这个关联关系？"))) return;
  try {
    await api("/knowledge/relations/" + id.value, "DELETE");
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
      ><view class="title">{{ id ? "编辑关系" : "新增关系" }}</view
      ><text class="label">起点实体</text
      ><picker
        :range="entities"
        range-key="name"
        :value="from"
        @change="from = Number($event.detail.value)"
        ><view class="field pick"
          >{{ entities[from]?.name || "请选择" }} ⌄</view
        ></picker
      ><text class="label">关系类型</text
      ><picker
        :range="kinds"
        :value="kind"
        @change="kind = Number($event.detail.value)"
        ><view class="field pick">{{ kinds[kind] }} ⌄</view></picker
      ><text class="label">终点实体</text
      ><picker
        :range="entities"
        range-key="name"
        :value="to"
        @change="to = Number($event.detail.value)"
        ><view class="field pick"
          >{{ entities[to]?.name || "请选择" }} ⌄</view
        ></picker
      ><text class="label">关系依据来源</text
      ><picker
        :range="sources"
        range-key="title"
        :value="source"
        @change="source = Number($event.detail.value)"
        ><view class="field pick"
          >{{ sources[source]?.title || "请选择" }} ⌄</view
        ></picker
      ><view class="muted small spaced">关系发布前，两端实体均需已发布。</view
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
      ><button v-if="id" class="secondary danger spaced" @tap="remove">
        删除关系
      </button></view
    ></view
  >
</template>
<style scoped>
.pick {
  padding: 22rpx;
}
</style>
