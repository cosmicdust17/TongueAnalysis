<script setup lang="ts">
import { ref, computed, watch, nextTick, getCurrentInstance, onMounted, onUnmounted } from 'vue';
import { download } from '@/utils/request';
import type { AnnotationSnapshot, DetectionBox } from '@/types';
import { containRect, labelPositions } from '@/utils/annotations';
const props = defineProps<{ fileId: string; annotations?: AnnotationSnapshot; compact?: boolean; monochrome?: boolean }>();
const instance = getCurrentInstance();
const src = ref(''), failed = ref(false), marked = ref(false), expanded = ref(false), zoom = ref(1);
const selected = ref<DetectionBox | null>(null);
const stage = ref({width: 1, height: 1});
const boxes = computed(() => props.annotations?.detections || []);
const groups = computed(() => boxes.value.filter((b,i,a) => a.findIndex(x => x.class_name === b.class_name) === i));
const rect = computed(() => {
  const w = props.annotations?.image_width || 1, h = props.annotations?.image_height || 1;
  return containRect(stage.value.width, stage.value.height, w, h);
});
function measure() {
  nextTick(() => uni.createSelectorQuery().in(instance!.proxy).select('.annotation-stage').boundingClientRect((r: any) => {
    if (r?.width && r?.height) stage.value = {width:r.width,height:r.height};
  }).exec());
}
function boxStyle(b: DetectionBox) {
  const [x1,y1,x2,y2] = b.xyxy, r=rect.value;
  return {left:r.x+x1*r.w+'px',top:r.y+y1*r.h+'px',width:(x2-x1)*r.w+'px',height:(y2-y1)*r.h+'px',borderColor:props.monochrome?'#222':b.color};
}
const labels = computed(() => labelPositions(rect.value, boxes.value));
function labelStyle(b: DetectionBox) {
  const p = labels.value[boxes.value.indexOf(b)];
  return {left:p.x+'px',top:p.y+'px',background:props.monochrome?'#fff':b.color};
}
function expand() { expanded.value=!expanded.value; zoom.value=1; measure(); }
watch(() => props.fileId, async (id) => {
  src.value='';failed.value=false;selected.value=null;
  try { const path=await download('/uploads/'+id+'/content'); if(props.fileId===id) src.value=path; }
  catch { failed.value=true; }
}, {immediate:true});
onMounted(() => { measure(); uni.onWindowResize(measure); });
onUnmounted(() => uni.offWindowResize(measure));
</script>
<template>
  <view class="photo-panel" :class="{expanded, monochrome}">
    <view class="row between photo-controls">
      <text class="subtitle">本次舌照</text>
      <button class="outline button-small" @tap="marked=!marked">{{marked?'查看原图':'查看标注'}}</button>
      <button class="secondary button-small" @tap="expand">{{expanded?'关闭放大':'放大查看'}}</button>
    </view>
    <movable-area class="annotation-stage" :class="{'stage-expanded':expanded, 'stage-compact':compact && !expanded}">
      <movable-view class="photo-plane" :direction="expanded?'all':'none'" :scale="expanded" :scale-min="1" :scale-max="4" :scale-value="zoom">
        <image v-if="src" :src="src" mode="aspectFit" class="photo-original" @load="measure"/>
        <view v-else class="loading">{{failed?'图片暂不可用':'加载图片…'}}</view>
        <template v-if="marked && src">
          <view v-for="(box,i) in boxes" :key="'box'+i" class="detection-box" :style="boxStyle(box)" @tap.stop="selected=box"/>
          <view v-for="(box,i) in boxes" :key="'label'+i" class="box-label" :style="labelStyle(box)" @tap.stop="selected=box">{{box.name}}</view>
        </template>
      </movable-view>
    </movable-area>
    <button v-if="expanded" class="secondary button-small" @tap="zoom=zoom===1?2:1">{{zoom===1?'放大至2倍':'还原大小'}}</button>
    <view v-if="marked && !annotations?.available" class="muted small">本报告暂无标注信息。</view>
    <view v-else-if="marked && !boxes.length" class="muted small">本次未检出可标注的舌象特征</view>
    <view v-if="marked" class="chips spaced">
      <view v-for="box in groups" :key="box.class_name" class="chip" @tap="selected=box">{{box.name}}</view>
    </view>
    <view v-if="selected && marked" class="feature-detail spaced">
      <view class="subtitle">{{selected.name}}</view><view>{{selected.description.replace(/模型标注的/g,'标注的')}}</view>
      <view class="muted small">标注说明用于帮助阅读舌照。</view>
    </view>
  </view>
</template>
<style scoped>
.photo-panel{margin:24rpx 0;padding:20rpx;background:#fff;border-radius:20rpx}
.photo-controls{gap:8rpx;margin-bottom:16rpx}.photo-controls button{font-size:24rpx}
.annotation-stage{position:relative;width:100%;height:620rpx;background:#edf3ef;overflow:hidden}
.photo-plane,.photo-original{position:absolute;width:100%;height:100%}
.detection-box{position:absolute;box-sizing:border-box;border:2px solid}
.box-label{position:absolute;color:white;font-size:12px;line-height:22px;padding:0 4px;z-index:2}
.expanded{position:fixed;inset:0;z-index:99;margin:0;border-radius:0;padding:20px;overflow:auto;padding-top:env(safe-area-inset-top)}
.stage-expanded{height:65vh}.stage-compact{height:460rpx}.feature-detail{padding:16rpx;background:#edf7f0;border-radius:12rpx}
.monochrome { color: #272727; border: 1rpx solid #e2e2e2; }
.monochrome .annotation-stage, .monochrome .feature-detail { background: #f4f4f4; }
.monochrome .outline, .monochrome .secondary, .monochrome .chip {
  background: #fff; color: #272727; border: 1rpx solid #cfcfcf;
}
.monochrome .muted, .monochrome .loading { color: #666; }
.monochrome .detection-box { box-shadow: 0 0 0 1px #fff; }
.monochrome .box-label { color: #161616; box-shadow: 0 0 0 1px #333; }
</style>
