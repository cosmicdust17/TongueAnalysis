<script setup lang="ts">
import { ref } from "vue";
import { onReady, onShow } from "@dcloudio/uni-app";
import { requireAuth } from "@/stores/auth";
import PageHero from "@/components/PageHero.vue";
import TextbookGraph from "@/components/TextbookGraph.vue";
import RoleNav from "@/components/RoleNav.vue";

const textbook = ref<InstanceType<typeof TextbookGraph> | null>(null);
let ready = false;
function loadGraph() {
  if (!requireAuth("knowledge_admin")) return;
  void textbook.value?.load();
}
onReady(() => {
  ready = true;
  loadGraph();
});
onShow(() => {
  if (ready) loadGraph();
});
function go(path: string) {
  uni.navigateTo({ url: "/subpackages/knowledge-admin/" + path });
}
</script>

<template>
  <view class="page with-nav">
    <PageHero title="专业知识库" subtitle="浏览已发布的教材关系与出处" badge="知识库管理员" />
    <TextbookGraph ref="textbook" />
    <view class="actions spaced">
      <button class="outline button-small" @tap="go('sources')">文档管理</button>
      <button class="outline button-small" @tap="go('relations')">关系管理</button>
      <button class="outline button-small" @tap="go('review')">审核发布</button>
    </view>
    <RoleNav active="graph" />
  </view>
</template>
