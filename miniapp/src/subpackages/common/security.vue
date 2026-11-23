<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { useAuth, requireAuth } from "@/stores/auth";
import { api, toastError } from "@/utils/request";
const auth = useAuth(),
  oldPassword = ref(""),
  newPassword = ref(""),
  confirmation = ref(""),
  busy = ref(false);
onShow(() => requireAuth());
async function save() {
  if (newPassword.value !== confirmation.value) {
    uni.showToast({ title: "两次新密码不一致", icon: "none" });
    return;
  }
  busy.value = true;
  try {
    await api("/users/me/password", "POST", {
      old_password: oldPassword.value,
      new_password: newPassword.value,
    });
    auth.clear();
    uni.showToast({ title: "密码已更新，请重新登录", icon: "none" });
    uni.reLaunch({ url: "/pages/login/index" });
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
      ><view class="title">登录安全</view
      ><view v-if="!auth.user?.has_password" class="muted spaced"
        >当前使用微信或开发联调账号登录，无本地密码。退出登录会使已有会话失效。</view
      ><template v-else
        ><view class="muted small">修改密码后，需要重新登录。</view
        ><text class="label">原密码</text
        ><view class="field"
          ><input
            v-model="oldPassword"
            :password="true"
            maxlength="128" /></view
        ><text class="label">新密码（至少10位）</text
        ><view class="field"
          ><input
            v-model="newPassword"
            :password="true"
            maxlength="128" /></view
        ><text class="label">确认新密码</text
        ><view class="field"
          ><input
            v-model="confirmation"
            :password="true"
            maxlength="128" /></view
        ><button class="primary spaced" :disabled="busy" @tap="save">
          更新密码
        </button></template
      ></view
    ></view
  >
</template>
