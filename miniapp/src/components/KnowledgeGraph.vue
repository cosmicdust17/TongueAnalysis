<script setup lang="ts">
import { computed, ref } from "vue";
import type { Graph } from "@/types";
const props = defineProps<{ data: Graph; selected: string; neighborPage?: number }>();
const emit = defineEmits<{ select: [id: string]; source: [id: string]; relation: [id: string] }>();
const zoom = ref(1),
  dx = ref(0),
  dy = ref(0);
let gesture: { x: number; y: number; distance: number } | undefined;
const scene = computed(() => {
  const root =
    props.data.nodes.find((x) => x.id === props.selected) ||
    props.data.nodes[0];
  if (!root) return { nodes: [], edges: [] };
  const connected = props.data.relations.filter(
    (x) => x.source === root.id || x.target === root.id,
  );
  const ids = new Set(connected.flatMap((x) => [x.source, x.target]));
  const offset = (props.neighborPage || 0) * 6;
  const neighbors = props.data.nodes
    .filter((x) => x.id !== root.id && ids.has(x.id))
    .slice(offset, offset + 6);
  const sourceIds = new Set([
    root.source_id,
    ...neighbors.map((x) => x.source_id),
  ]);
  const sourceNodes = props.data.sources
    .filter((s) => sourceIds.has(s.id))
    .slice(0, 2)
    .map((s) => ({ id: s.id, name: s.title, kind: "来源" }));
  const outer = [...neighbors, ...sourceNodes];
  const nodes = [
    { ...root, x: 320, y: 285, center: true },
    ...outer.map((n, i) => ({
      ...n,
      x: 320 + 220 * Math.cos(-Math.PI / 2 + (i * 2 * Math.PI) / outer.length),
      y: 285 + 220 * Math.sin(-Math.PI / 2 + (i * 2 * Math.PI) / outer.length),
      center: false,
    })),
  ];
  const edges = nodes.slice(1).map((n) => {
    const related = connected.find(
      (r) => r.source === n.id || r.target === n.id,
    );
    const vx = n.x - 320,
      vy = n.y - 285,
      len = Math.sqrt(vx * vx + vy * vy);
    const arrowAtRoot = related?.source === n.id;
    return {
      id: n.id,
      relationId: related?.id,
      x: 320 + (vx / len) * 57,
      y: 285 + (vy / len) * 57,
      length: len - 112,
      angle: (Math.atan2(vy, vx) * 180) / Math.PI,
      label: n.kind === "来源" ? "来源" : related?.kind || "相关",
      arrowAtRoot,
    };
  });
  return { nodes, edges };
});
const colors: Record<string, string> = {
  舌象特征: "#e0f4e7",
  症状: "#dfedff",
  证候: "#fff0d2",
  来源: "#e8e6f3",
  教材实体: "#e0f4e7",
};
function touchPosition(e: TouchEvent) {
  const [first, second] = Array.from(e.touches);
  if (!first) return undefined;
  if (!second) return { x: first.clientX, y: first.clientY, distance: 0 };
  return {
    x: (first.clientX + second.clientX) / 2,
    y: (first.clientY + second.clientY) / 2,
    distance: Math.hypot(first.clientX - second.clientX, first.clientY - second.clientY),
  };
}
function start(e: TouchEvent) { gesture = touchPosition(e); }
function move(e: TouchEvent) {
  const next = touchPosition(e);
  if (gesture && next && Boolean(gesture.distance) === Boolean(next.distance)) {
    dx.value += next.x - gesture.x;
    dy.value += next.y - gesture.y;
    if (gesture.distance && next.distance) scale(zoom.value * next.distance / gesture.distance);
  }
  gesture = next;
}
function scale(value: number) { zoom.value = Math.min(2.2, Math.max(0.55, value)); }
function reset() {
  zoom.value = 1;
  dx.value = dy.value = 0;
}
function select(id: string, kind: string) {
  if (kind === "来源") emit("source", id);
  else emit("select", id);
}
</script>
<template>
  <view
    class="graph-container"
    @touchstart="start"
    @touchmove.stop.prevent="move"
    @touchend="start"
    @touchcancel="start"
    ><view
      class="graph-scene"
      :style="{
        transform: 'translate(' + dx + 'px,' + dy + 'px) scale(' + zoom + ')',
      }"
      ><view
        v-for="edge in scene.edges"
        :key="edge.id"
        class="graph-edge"
        :style="{
          left: edge.x + 'rpx',
          top: edge.y - 19 + 'rpx',
          width: edge.length + 'rpx',
          transform: 'rotate(' + edge.angle + 'deg)',
        }"
        @tap.stop="edge.relationId && emit('relation', edge.relationId)"
        ><view class="arrow" :class="{ reverse: edge.arrowAtRoot }" /><view
          class="edge-label"
          :class="{ 'edge-action': edge.relationId }"
          :style="{ transform: 'rotate(' + -edge.angle + 'deg)' }"
          >{{ edge.label }}</view
        ></view
      ><view
        v-for="n in scene.nodes"
        :key="n.id"
        class="graph-node"
        :class="{ central: n.center }"
        :style="{
          left: n.x - 53 + 'rpx',
          top: n.y - 53 + 'rpx',
          background: colors[n.kind],
        }"
        @tap.stop="select(n.id, n.kind)"
        ><text class="node-kind">{{ n.kind }}</text
        ><text class="node-label">{{ n.name }}</text></view
      ></view
    ><view v-if="!scene.nodes.length" class="empty">暂无匹配实体</view
    ><view class="graph-controls"
      ><view @tap.stop="scale(zoom + 0.15)">＋</view
      ><view @tap.stop="scale(zoom - 0.15)">−</view
      ><view @tap.stop="reset">⤢</view></view
    ></view
  >
</template>
<style scoped>
.graph-container {
  position: relative;
  height: 600rpx;
  overflow: hidden;
  background: #fff;
  border-radius: 20rpx;
  touch-action: none;
}
.graph-scene {
  position: relative;
  width: 640rpx;
  height: 570rpx;
  transform-origin: 320rpx 285rpx;
  transition: transform 0.1s;
}
.graph-node {
  position: absolute;
  width: 106rpx;
  height: 106rpx;
  border-radius: 50%;
  border: 2rpx solid rgba(35, 92, 63, 0.1);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 9rpx;
  text-align: center;
  z-index: 2;
}
.graph-node.central {
  box-shadow: 0 0 0 13rpx #edf6fc;
  border-color: #9bc6e9;
}
.node-kind {
  font-size: 18rpx;
  color: #6e7d76;
}
.node-label {
  font-size: 25rpx;
  font-weight: 650;
  line-height: 1.3;
  max-height: 65rpx;
  overflow: hidden;
}
.graph-edge {
  height: 38rpx;
  position: absolute;
  transform-origin: left center;
  z-index: 1;
}
.graph-edge::before { content: ''; position: absolute; inset: 18rpx 0 auto; height: 2rpx; background: #88a799; }
.edge-label {
  position: absolute;
  top: 4rpx;
  left: 24%;
  font-size: 20rpx;
  white-space: nowrap;
  background: #fff;
  color: #77877e;
}
.edge-action {
  padding: 4rpx 8rpx;
  color: #087f56;
  cursor: pointer;
}
.arrow {
  position: absolute;
  right: -2rpx;
  top: 13rpx;
  width: 0;
  height: 0;
  border-top: 6rpx solid transparent;
  border-bottom: 6rpx solid transparent;
  border-left: 10rpx solid #94b0a3;
}
.arrow.reverse {
  left: -2rpx;
  right: auto;
  transform: rotate(180deg);
}
.graph-controls {
  position: absolute;
  right: 4rpx;
  bottom: 15rpx;
  border: 1rpx solid #dae6df;
  border-radius: 14rpx;
  background: white;
  overflow: hidden;
  z-index: 5;
}
.graph-controls view {
  font-size: 33rpx;
  text-align: center;
  width: 55rpx;
  height: 55rpx;
  line-height: 55rpx;
  border-bottom: 1rpx solid #edf2ee;
}
</style>
