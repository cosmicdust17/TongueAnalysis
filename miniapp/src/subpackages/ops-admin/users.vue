<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { api, query, toastError, confirmAction } from "@/utils/request";
import { requireAuth } from "@/stores/auth";
import type { User } from "@/types";
const rows = ref<User[]>([]),
  q = ref(""),
  page = ref(1),
  total = ref(0),
  busy = ref(false),
  error = ref("");
onShow(() => {
  if (requireAuth("ops_admin")) load(true);
});
async function load(reset = false) {
  if (busy.value) return;
  if (reset) page.value = 1;
  busy.value = true;
  error.value = "";
  try {
    const data = await api<{ items: User[]; total: number }>(
      "/operations/users" + query({ q: q.value, page: page.value }),
    );
    rows.value = reset ? data.items : [...rows.value, ...data.items];
    total.value = data.total;
    page.value++;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "读取失败";
  } finally {
    busy.value = false;
  }
}
async function toggle(user: User) {
  if (
    !(await confirmAction(
      (user.active ? "停用" : "启用") + "该用户账号？已有会话会失效。",
    ))
  )
    return;
  try {
    await api("/operations/users/" + user.id + "/status", "PUT", {
      active: !user.active,
    });
    load(true);
  } catch (e) {
    toastError(e);
  }
}
</script>
<template>
  <view class="page"
    ><view class="title section">用户管理</view
    ><view class="row search"
      ><input
        v-model="q"
        placeholder="搜索普通用户昵称或账号"
        @confirm="load(true)"
      /><text class="link" @tap="load(true)">搜索</text></view
    ><view v-if="error" class="error">{{ error }}</view
    ><view v-for="user in rows" :key="user.id" class="panel"
      ><view class="row between"
        ><text class="title">{{ user.nickname }}</text
        ><text class="pill" :class="user.active ? '' : 'pending'">{{
          user.active ? "正常" : "已停用"
        }}</text></view
      ><view class="muted small">{{ user.username }}</view
      ><button class="outline button-small spaced" @tap="toggle(user)">
        {{ user.active ? "停用账号" : "启用账号" }}
      </button></view
    ><view v-if="!rows.length && !error" class="empty"
      >暂无符合条件的普通用户</view
    ><button
      v-if="rows.length < total"
      class="outline"
      :disabled="busy"
      @tap="load(false)"
    >
      加载更多
    </button></view
  >
</template>
