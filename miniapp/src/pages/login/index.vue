<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { api, toastError } from "@/utils/request";
import { useAuth, homeFor } from "@/stores/auth";
import type { Role, Session } from "@/types";
import PageHero from "@/components/PageHero.vue";
import AppIcon from "@/components/AppIcon.vue";
const auth = useAuth(),
  username = ref(""),
  password = ref(""),
  busy = ref(false);
const dev = import.meta.env.VITE_ENABLE_DEV_LOGIN === "true";
onShow(() => {
  if (uni.getStorageSync("token") && auth.user)
    uni.reLaunch({ url: homeFor(auth.user.role) });
});
function accept(s: Session) {
  auth.accept(s);
  uni.reLaunch({ url: homeFor(s.user.role) });
}
async function accountLogin() {
  if (!username.value || !password.value) {
    uni.showToast({ title: "请填写账号和密码", icon: "none" });
    return;
  }
  busy.value = true;
  try {
    accept(
      await api<Session>("/auth/login", "POST", {
        username: username.value,
        password: password.value,
      }),
    );
  } catch (e) {
    toastError(e);
  } finally {
    busy.value = false;
  }
}
async function developerLogin(role: Role) {
  busy.value = true;
  try {
    accept(await api<Session>("/auth/dev-login", "POST", { role }));
  } catch (e) {
    toastError(e);
  } finally {
    busy.value = false;
  }
}
async function wechatLogin() {
  if (busy.value) return;
  busy.value = true;
  try {
    const login = await new Promise<UniApp.LoginRes>((resolve, reject) =>
      uni.login({ provider: "weixin", success: resolve,
        fail: () => reject(new Error("未能获取微信登录凭证，请确认使用正确的小程序项目后重试")) }),
    );
    if (!login.code) throw new Error("未获取到微信登录凭证，请重新点击微信登录");
    accept(await api<Session>("/auth/wechat", "POST", { code: login.code }));
  } catch (e) {
    toastError(e);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <view class="page"
    ><PageHero
      title="舌象智能分析"
      subtitle="记录舌象与症状，查看知识依据"
    /><view class="panel login-brand"
      ><view class="avatar"><AppIcon name="leaf" :size="80" /></view
      ><view class="title spaced">从舌象，了解身体</view
      ><view class="muted small">每次记录，都有据可查</view></view
    >
    <view class="panel stack"
      ><button class="primary" :disabled="busy" @tap="wechatLogin">
        微信登录</button
      ><view class="divider" /><view class="subtitle">管理员账号登录</view
      ><view class="field"
        ><input v-model="username" placeholder="账号" maxlength="80" /></view
      ><view class="field"
        ><input
          v-model="password"
          :password="true"
          placeholder="密码"
          maxlength="128"
          @confirm="accountLogin" /></view
      ><button
        class="outline"
        :loading="busy"
        :disabled="busy"
        @tap="accountLogin"
      >
        登录
      </button></view
    >
    <view v-if="dev" class="panel"
      ><view class="subtitle">开发联调入口</view
      ><view class="muted small"
        >需后端同时开启开发登录。仅用于内部联调，请以报告中的模型标记为准。</view
      ><view class="dev-grid spaced"
        ><button
          class="secondary button-small"
          :disabled="busy"
          @tap="developerLogin('user')"
        >
          用户端</button
        ><button
          class="secondary button-small"
          :disabled="busy"
          @tap="developerLogin('knowledge_admin')"
        >
          知识管理</button
        ><button
          class="secondary button-small"
          :disabled="busy"
          @tap="developerLogin('ops_admin')"
        >
          系统运维
        </button></view
      ></view
    ><view class="footer-mark small"
      >用于健康信息参考，不替代专业诊断</view
    ></view
  >
</template>
<style scoped>
.login-brand {
  text-align: center;
  padding: 45rpx 20rpx;
}
.avatar {
  margin: auto;
}
.dev-grid {
  display: flex;
  gap: 12rpx;
}
.dev-grid button {
  flex: 1;
  font-size: 24rpx;
  padding: 12rpx;
}
</style>
