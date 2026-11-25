<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { EdgeEvent, Graph as G6Graph, NodeEvent, type IPointerEvent } from "@antv/g6";
import type { Graph } from "@/types";

const props = defineProps<{ data: Graph; selected: string; neighborPage: number }>();
const emit = defineEmits<{ select: [id: string]; relation: [id: string]; unavailable: [] }>();
const host = ref<HTMLDivElement>();
let graph: G6Graph | undefined;
let redraw = Promise.resolve();

async function render(instance: G6Graph) {
  const root = props.selected;
  const connections = props.data.relations.filter((edge) => edge.source === root || edge.target === root);
  const neighbors = [...new Set(connections.map((edge) => edge.source === root ? edge.target : edge.source))]
    .filter((id) => id !== root);
  const offset = props.neighborPage * 6;
  const visible = new Set([root, ...neighbors.slice(offset, offset + 6)]);
  const nodes = props.data.nodes.filter((node) => visible.has(node.id)).map((node) => ({
    id: node.id,
    style: { labelText: node.name, fill: node.id === root ? "#d8ebdc" : "#f3f6e9" },
  }));
  const edges = connections.filter((edge) => visible.has(edge.source) && visible.has(edge.target)).map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    style: { labelText: edge.kind },
  }));
  instance.setData({ nodes, edges });
  instance.setLayout({ type: "radial", focusNode: root, preventOverlap: true, strictRadial: false,
    nodeSize: 110, nodeSpacing: 18, unitRadius: 150 });
  await instance.render();
}

function scheduleRender() {
  redraw = redraw.then(async () => {
    const instance = graph;
    if (!instance) return;
    try {
      await render(instance);
    } catch {
      if (graph === instance) emit("unavailable");
    }
  });
}

onMounted(() => {
  if (!host.value) return;
  try {
    graph = new G6Graph({
      container: host.value,
      autoResize: true,
      autoFit: "view",
      padding: 22,
      animation: false,
      behaviors: ["drag-canvas", "zoom-canvas"],
      transforms: [{ type: "process-parallel-edges", mode: "bundle" }],
      node: { type: "rect", style: { size: [98, 48], radius: 12, stroke: "#678a70", cursor: "pointer",
        labelPlacement: "center", labelFill: "#25453b", labelFontSize: 12, labelWordWrap: true, labelMaxLines: 2, labelMaxWidth: 86 } },
      edge: { style: { stroke: "#608274", endArrow: true, cursor: "pointer", lineWidth: 1.5,
        increasedLineWidthForHitTesting: 12, labelFill: "#345b4b", labelFontSize: 11,
        labelAutoRotate: false, labelBackground: true, labelBackgroundFill: "#f7fbf7" } },
    });
    graph.on(NodeEvent.CLICK, ({ target }: IPointerEvent) => {
      if ("id" in target) emit("select", target.id);
    });
    graph.on(EdgeEvent.CLICK, ({ target }: IPointerEvent) => {
      if ("id" in target) emit("relation", target.id);
    });
    scheduleRender();
  } catch {
    emit("unavailable");
  }
});

watch(() => [props.data, props.selected, props.neighborPage], scheduleRender, { flush: "post" });

onBeforeUnmount(() => {
  const instance = graph;
  graph = undefined;
  void redraw.finally(() => instance?.destroy());
});

function zoom(ratio: number) {
  void graph?.zoomBy(ratio, false);
}
</script>

<template>
  <div class="g6-view" aria-label="教材关系图谱">
    <div ref="host" class="g6-canvas"></div>
    <div class="g6-controls">
      <button aria-label="放大图谱" @click="zoom(1.2)">＋</button>
      <button aria-label="缩小图谱" @click="zoom(1 / 1.2)">−</button>
    </div>
  </div>
</template>

<style scoped>
.g6-view { position: relative; overflow: hidden; border: 1px solid #e0ebe3; border-radius: 12px; }
.g6-canvas { width: 100%; height: 325px; background: #f8fbf8; touch-action: none; }
.g6-controls { position: absolute; right: 8px; bottom: 8px; display: flex; gap: 4px; }
.g6-controls > * { min-width: 36px; min-height: 36px; margin: 0; padding: 0; background: #fff; color: #25453b; }
</style>
