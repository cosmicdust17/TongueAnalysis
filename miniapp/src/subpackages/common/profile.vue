<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { useAuth, requireAuth } from "@/stores/auth";
import { api, toastError } from "@/utils/request";
import type { User } from "@/types";
const auth = useAuth(),
  nickname = ref(""),
  age = ref(""),
  gender = ref(0),
  busy = ref(false),
  genders = ["未填写", "男", "女"];
onShow(async () => {
  if (!requireAuth()) return;
  try {
    await auth.refresh();
    nickname.value = auth.user!.nickname;
    age.value = auth.user!.profile.age ? String(auth.user!.profile.age) : "";
    gender.value = Math.max(
      0,
      genders.indexOf(auth.user!.profile.gender || "未填写"),
    );
  } catch (e) {
    toastError(e);
  }
});
async function save() {
  const n = Number(age.value);
  if (age.value && (!Number.isInteger(n) || n < 1 || n > 120)) {
    uni.showToast({ title: "请填写1至120之间的整数年龄", icon: "none" });
    return;
  }
  busy.value = true;
  try {
    await api<User>("/users/me", "PUT", {
      nickname: nickname.value,
      gender: genders[gender.value],
      age: age.value ? n : null,
    });
    await auth.refresh();
    uni.showToast({ title: "已保存", icon: "success" });
  } catch (e) {
    toastError(e);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <view class="page"
    ><view class="panel"
      ><view class="title">个人资料</view><text class="label">昵称</text
      ><view class="field"
        ><input
          v-model="nickname"
          maxlength="80"
          placeholder="请输入昵称" /></view
      ><text class="label">年龄（可选）</text
      ><view class="field"
        ><input
          v-model="age"
          type="number"
          maxlength="3"
          placeholder="未填写" /></view
      ><text class="label">性别（可选）</text
      ><picker
        :range="genders"
        :value="gender"
        @change="gender = Number($event.detail.value)"
        ><view class="field picker">{{ genders[gender] }} ⌄</view></picker
      ><view class="muted small spaced">用户 ID：{{ auth.user?.id }}</view
      ><button
        class="primary spaced"
        :disabled="busy"
        :loading="busy"
        @tap="save"
      >
        保存信息
      </button></view
    ></view
  >
</template>
<style scoped>
.picker {
  padding: 22rpx;
}
</style>
