<script setup lang="ts">
import { computed, ref } from "vue";
import { api } from "@/utils/request";
import type { Graph } from "@/types";
import KnowledgeGraph from "@/components/KnowledgeGraph.vue";

type TextbookEdge = {
  source: { entity_id: string; name: string };
  target: { entity_id: string; name: string };
  relation: { candidate_id: string; kind: string; statement: string; condition?: string; quote: string; object_qualifier?: string; supporting_quotes?: string[] };
  evidence: {
    chunk_id: string;
    text: string;
    source_title: string;
    edition?: string;
    location: { chapter?: string; pdf_page?: number };
    verified_location?: { printed_page?: number; paragraph?: string | number };
  };
};

const edges = ref<TextbookEdge[]>([]);
const selected = ref("");
const relation = ref<TextbookEdge>();
const loading = ref(true);
const error = ref("");
const nodeQuery = ref("");
const nodeSearchError = ref(false);
const neighborPage = ref(0);
const limitReached = ref(false);
let requestId = 0;

async function load() {
  const id = ++requestId;
  loading.value = true;
  error.value = "";
  relation.value = undefined;
  try {
    const result = await api<{ relations: TextbookEdge[]; limit_reached: boolean }>("/knowledge/textbook-graph");
    if (id !== requestId) return;
    edges.value = result.relations;
    limitReached.value = result.limit_reached;
    neighborPage.value = 0;
    if (!edges.value.some((edge) => edge.source.entity_id === selected.value || edge.target.entity_id === selected.value)) {
      selected.value = edges.value[0]?.source.entity_id || "";
    }
  } catch (e) {
    if (id === requestId) error.value = e instanceof Error ? e.message : "教材图谱读取失败";
  } finally {
    if (id === requestId) loading.value = false;
  }
}
defineExpose({ load });

const data = computed<Graph>(() => ({
  nodes: [...new Map(edges.value.flatMap(({ source, target }) => [source, target]).map((node) => [node.entity_id, node])).values()]
    .map((node) => ({ id: node.entity_id, name: node.name, kind: "教材实体", text: "", source_id: "", aliases: [],
      status: "published", is_demo: false, updated_at: "" })),
  relations: edges.value.map((edge) => ({ id: edge.relation.candidate_id, source: edge.source.entity_id,
    target: edge.target.entity_id, kind: edge.relation.kind, source_id: edge.evidence.chunk_id,
    status: "published", is_demo: false, updated_at: "" })),
  sources: [],
  truncated: false,
}));

const connected = computed(() => edges.value.filter((edge) => edge.source.entity_id === selected.value || edge.target.entity_id === selected.value));
const focus = computed(() => data.value.nodes.find((node) => node.id === selected.value));
const neighborPages = computed(() => {
  const neighbors = new Set(connected.value.flatMap((edge) => [edge.source.entity_id, edge.target.entity_id]));
  neighbors.delete(selected.value);
  return Math.max(1, Math.ceil(neighbors.size / 6));
});
function selectNode(id: string) {
  selected.value = id;
  neighborPage.value = 0;
  relation.value = undefined;
  nodeSearchError.value = false;
}
function locateNode() {
  const name = nodeQuery.value.trim();
  if (!name) return;
  const node = data.value.nodes.find((item) => item.name === name) ||
    data.value.nodes.find((item) => item.name.includes(name));
  if (node) selectNode(node.id);
  else {
    const edge = edges.value.find((item) => relationText(item).includes(name));
    if (edge) selectNode(edge.source.entity_id);
    else nodeSearchError.value = true;
  }
}
function selectRelation(id: string) {
  relation.value = edges.value.find((edge) => edge.relation.candidate_id === id);
}
function relationText(edge: TextbookEdge) {
  return edge.relation.statement || `${edge.source.name}${edge.relation.kind}${edge.relation.object_qualifier || ''}${edge.target.name}`;
}
function locationText(edge: TextbookEdge) {
  const { printed_page, paragraph } = edge.evidence.verified_location || {};
  const { chapter, pdf_page } = edge.evidence.location;
  return [chapter, printed_page != null ? `印刷第 ${printed_page} 页` : pdf_page != null ? `PDF 第 ${pdf_page} 页` : '',
    paragraph != null ? `第 ${paragraph} 段` : ''].filter(Boolean).join(' · ');
}
</script>

<template>
  <view class="panel">
    <view class="row between">
      <view class="title">教材知识图谱</view>
      <text class="link" @tap="load">刷新</text>
    </view>
    <view v-if="loading" class="muted spaced">正在加载已发布的教材关系…</view>
    <view v-else-if="error" class="error spaced" @tap="load">{{ error }} · 重试</view>
    <view v-else-if="!edges.length" class="empty spaced">暂无已发布的教材关系。人工审核并发布后，关系及教材出处会显示在这里。</view>
    <template v-else>
      <view class="muted small spaced graph-count">{{ data.nodes.length }} 个实体 · {{ edges.length }} 条已发布关系</view>
      <view v-if="limitReached" class="muted small">当前最多显示 500 条已发布关系。</view>
      <view class="row search spaced">
        <input v-model="nodeQuery" placeholder="搜索教材实体或关系" @confirm="locateNode" />
        <text class="link" @tap="locateNode">定位</text>
      </view>
      <view v-if="nodeSearchError" class="muted small">暂无匹配的教材实体</view>
      <picker :range="data.nodes" range-key="name" @change="selectNode(data.nodes[Number($event.detail.value)].id)">
        <view class="focus-picker">当前实体：{{ focus?.name }} · 选择实体 ⌄</view>
      </picker>
      <KnowledgeGraph :data="data" :selected="selected" :neighbor-page="neighborPage" @select="selectNode" @relation="selectRelation" />
      <view class="muted tiny center">拖动平移，双指或＋/−缩放，点击连线查看出处。</view>
      <view v-if="neighborPages > 1" class="row between spaced">
        <button class="outline button-small" :disabled="neighborPage === 0" @tap="neighborPage--">上一组</button>
        <text class="muted small">{{ neighborPage + 1 }} / {{ neighborPages }}</text>
        <button class="outline button-small" :disabled="neighborPage + 1 >= neighborPages" @tap="neighborPage++">下一组</button>
      </view>
      <view class="subtitle spaced">{{ focus?.name }}的关联关系 · {{ connected.length }} 条</view>
      <view v-for="edge in connected" :key="edge.relation.candidate_id" class="relation-row spaced" @tap="selectRelation(edge.relation.candidate_id)">
        <view>{{ relationText(edge) }}</view>
        <text class="muted small">{{ edge.evidence.source_title }} · {{ locationText(edge) }}</text>
      </view>
    </template>
    <view v-if="relation" class="overlay" @tap="relation = undefined">
      <view class="sheet" @tap.stop>
        <view class="row between">
          <text class="title">教材关系与出处</text>
          <text class="link" @tap="relation = undefined">关闭</text>
        </view>
        <scroll-view scroll-y class="reference-scroll">
          <view class="subtitle spaced">{{ relationText(relation) }}</view>
          <view class="muted small spaced">适用条件：{{ relation.relation.condition || '原文未单列条件' }}</view>
          <view class="spaced">《{{ relation.evidence.source_title }}》 {{ relation.evidence.edition }}</view>
          <view class="muted small">{{ locationText(relation) }}</view>
          <view class="subtitle spaced">教材原文</view>
          <text selectable class="reference-quote">{{ relation.relation.quote }}</text>
          <view v-for="quote in relation.relation.supporting_quotes" :key="quote" class="spaced">
            <text selectable class="reference-quote">{{ quote }}</text>
          </view>
          <view class="subtitle spaced">原文上下文（OCR）</view>
          <text selectable class="reference-quote">{{ relation.evidence.text }}</text>
        </scroll-view>
      </view>
    </view>
  </view>
</template>

<style scoped>
.relation-row { padding: 15rpx; border: 1rpx solid #dbe9e1; border-radius: 12rpx; }
.reference-scroll { max-height: 68vh; }
.reference-quote { white-space: pre-wrap; }
.focus-picker { color: #087f56; padding: 10rpx 4rpx; }
</style>
