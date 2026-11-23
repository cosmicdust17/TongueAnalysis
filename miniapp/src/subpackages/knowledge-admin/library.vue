<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { api, query, dateText } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { Entity, KnowledgeOverview } from "@/types";
import PageHero from "@/components/PageHero.vue";
import AppIcon from "@/components/AppIcon.vue";
import RoleNav from "@/components/RoleNav.vue";
const rows = ref<Entity[]>([]),
  stats = ref<KnowledgeOverview | null>(null),
  q = ref(""),
  kind = ref(""),
  error = ref(""),
  busy = ref(false);
const kinds = ["全部", "舌象特征", "症状", "证候"];
onShow(() => {
  if (requireAuth("knowledge_admin")) load();
});
async function load() {
  busy.value = true;
  error.value = "";
  try {
    const [a, b] = await Promise.all([
      api<{ items: Entity[] }>(
        "/knowledge/entities" + query({ q: q.value, kind: kind.value }),
      ),
      api<KnowledgeOverview>("/knowledge/overview"),
    ]);
    rows.value = a.items;
    stats.value = b;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "读取失败";
  } finally {
    busy.value = false;
  }
}
function filter(value: string) {
  kind.value = value === "全部" ? "" : value;
  load();
}
function go(url: string) {
  uni.navigateTo({ url: "/subpackages/knowledge-admin/" + url });
}
const label = (s: string) =>
  ({ draft: "草稿", pending: "待审核", published: "已发布" })[s] || s;
</script>
<template>
  <view class="page with-nav"
    ><PageHero
      title="专业知识管理"
      subtitle="统一管理知识内容与来源"
      badge="知识库管理员" /><view class="row search"
      ><AppIcon name="search" :size="36" /><input
        v-model="q"
        placeholder="搜索知识条目"
        @confirm="load"
      /><text class="link" @tap="load">搜索</text></view
    ><view v-if="error" class="error"
      >{{ error }}<text class="link" @tap="load"> 重试</text></view
    ><view v-if="stats" class="panel row between"
      ><view
        >知识条目 <text class="number">{{ stats.entity_count }}</text></view
      ><view @tap="go('review')"
        >待审核 <text class="number">{{ stats.pending_count }}</text> ›</view
      ></view
    ><view class="actions section"
      ><button class="outline" @tap="go('source-edit')">
        <AppIcon name="upload" :size="34" />导入文档</button
      ><button class="primary" @tap="go('entity-edit')">
        <AppIcon name="plus" :size="34" />新增条目
      </button></view
    ><view class="chips section"
      ><view
        v-for="item in kinds"
        :key="item"
        class="chip"
        :class="{ active: kind === (item === '全部' ? '' : item) }"
        @tap="filter(item)"
        >{{ item }}</view
      ></view
    ><view class="row between section"
      ><view class="title">知识条目</view
      ><text class="muted small">最近更新</text></view
    ><view v-if="busy" class="loading">正在读取图谱…</view
    ><view
      v-for="item in rows"
      :key="item.id"
      class="panel row"
      @tap="go('entity-edit?id=' + item.id)"
      ><view class="icon-box"><AppIcon name="document" /></view
      ><view class="grow"
        ><view class="row between"
          ><text class="subtitle">{{ item.name }}</text
          ><text class="pill" :class="item.status">{{
            label(item.status)
          }}</text></view
        ><view class="tag">{{ item.kind }}</view
        ><view class="muted tiny">来源：{{ item.source_title }}</view
        ><view class="row between"
          ><text class="muted tiny">{{ dateText(item.updated_at, true) }}</text
          ><text v-if="item.is_demo" class="tiny green">示例资料</text></view
        ></view
      ><text class="chevron">›</text></view
    ><view v-if="!busy && !rows.length && !error" class="empty"
      >暂无知识条目，请先维护来源，再新增条目。</view
    ><view class="actions spaced"
      ><button class="secondary button-small" @tap="go('sources')">
        查看全部文档 ›</button
      ><button class="secondary button-small" @tap="go('relations')">
        关系管理 ›
      </button></view
    ><RoleNav active="library"
  /></view>
</template>
<style scoped>
.number {
  font-size: 43rpx;
  font-weight: 700;
  color: #087f56;
  margin-left: 8rpx;
}
</style>
